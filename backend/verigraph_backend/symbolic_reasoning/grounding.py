from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..schemas import AssessmentAtomEvidence, PipelineAtom, RetrievalDocument, SymbolicPremise


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def utf16_offset(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le")) // 2


def lexical_tokens(text: str) -> set[str]:
    # Separate symbols before NFKC expansion so marks such as the trademark in
    # “iPhone™” do not become a glued token such as “iphonetm”.
    text = "".join(" " if unicodedata.category(character).startswith("S") else character for character in text)
    return {
        token for token in re.findall(r"[a-z][a-z0-9'-]*", normalize(text))
        if token not in {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "is", "it", "of", "on", "or", "that", "the", "to", "was", "were", "with"}
    }


def identity_tokens(text: str) -> set[str]:
    generic = {
        "complete", "designated", "designation", "entities", "entity", "financial",
        "group", "groups", "included", "index", "list", "membership", "official",
        "sanctions", "target", "targets", "terrorist",
    }
    tokens = lexical_tokens(text) - generic
    tokens.update(
        re.sub(r"[^A-Za-z0-9]", "", match.group(0)).casefold()
        for match in re.finditer(r"\b(?:[A-Za-z]\.){2,}|\b[A-Z]{2,}\b", text)
    )
    return {token for token in tokens if token and token not in generic}


@dataclass(frozen=True)
class Candidate:
    id: str
    atom_id: str
    operator: str
    premise_ids: tuple[str, ...]
    summary: str
    premise_texts: tuple[tuple[str, str], ...]


def evidence_premises(evidence: Sequence[AssessmentAtomEvidence]) -> dict[str, SymbolicPremise]:
    premises: dict[str, SymbolicPremise] = {}
    for group in evidence:
        for span in group.spans:
            key = f"evidence:{group.atom_id}:{span.document_id}:{span.id}"
            premises[key] = SymbolicPremise(
                id=key,
                document_id=span.document_id,
                text=span.text,
                start=span.start,
                end=span.end,
                kind="EVIDENCE",
            )
            for context in span.context_spans:
                context_key = f"context:{group.atom_id}:{context.document_id}:{context.id}"
                premises[context_key] = SymbolicPremise(
                    id=context_key, document_id=context.document_id,
                    text=context.text, start=context.start, end=context.end,
                    kind="OPERAND",
                )
    return premises


_EXHAUSTIVE = re.compile(
    r"(?i)\b(?:complete|exhaustive|entire|full|all)\b.{0,100}\b(?:list|index|entities|items|members|targets|consists|comprises|include)\b"
)
_LIST_LINE = re.compile(r"(?m)^[ \t]*(?:[-*•]|\d+[.)])[ \t]+(?P<item>[^\n]{1,240})$")
_INLINE_LIST = re.compile(r"(?i)\b(?:consists of|comprises|includes?)\s+(?P<items>[^.\n]{3,1200})")
_PLAIN_LIST_HEADING = re.compile(r"(?im)^[ \t]*(?:targets|items|members|entities|persons|groups)(?:\s*\(\d+\))?[ \t]*:?\s*$")
_COUNTED_LIST = re.compile(
    r"(?im)\b(?P<count>one|two|three|four|five|six|seven|eight|nine|ten|\d+)[ \t]+"
    r"(?P<label>(?:[a-z-]+[ \t]+){0,3}(?:members|items|entities|countries|states))[ \t]*:[ \t]*"
    r"(?P<items>.+?)(?=,\s+and\s+(?:[a-z-]+|\d+)\s+non-|\n|$)"
)
_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _split_inline(raw: str) -> list[str]:
    return [
        item.strip(" \t,;:.()[]")
        for item in re.split(r"\s*(?:,|;|\band\b|\bor\b)\s*", raw)
        if item.strip(" \t,;:.()[]")
    ]


def list_premises(documents: Sequence[RetrievalDocument]) -> dict[str, SymbolicPremise]:
    """Extract source-owned exhaustive-list certificates and their exact items."""
    premises: dict[str, SymbolicPremise] = {}
    for document in documents:
        text = document.text
        # A source-owned counted category such as "Five permanent members: ..."
        # is exhaustive only when the number of parsed items matches the stated
        # count. This is a generic completeness certificate, not a case rule.
        for counted_index, counted in enumerate(_COUNTED_LIST.finditer(text), start=1):
            expected = _COUNT_WORDS.get(counted.group("count").casefold())
            if expected is None:
                expected = int(counted.group("count"))
            raw_items = _split_inline(counted.group("items"))
            if len(raw_items) != expected:
                continue
            digest = hashlib.sha256("\n".join(normalize(item) for item in raw_items).encode()).hexdigest()
            certificate_id = f"list:{document.id}:counted-{counted_index}:certificate"
            certificate_end = counted.start("items")
            premises[certificate_id] = SymbolicPremise(
                id=certificate_id, document_id=document.id,
                text=text[counted.start():certificate_end],
                start=utf16_offset(text, counted.start()),
                end=utf16_offset(text, certificate_end), kind="LIST_CERTIFICATE",
                content_hash=digest, item_count=expected,
            )
            search_start = counted.start("items")
            for item_index, item in enumerate(raw_items, start=1):
                start = text.find(item, search_start, counted.end("items"))
                if start < 0:
                    continue
                search_start = start + len(item)
                premises[f"list:{document.id}:counted-{counted_index}:item:{item_index}"] = SymbolicPremise(
                    id=f"list:{document.id}:counted-{counted_index}:item:{item_index}",
                    document_id=document.id, text=item,
                    start=utf16_offset(text, start), end=utf16_offset(text, start + len(item)),
                    kind="LIST_ITEM", content_hash=digest,
                )
        certificates = list(_EXHAUSTIVE.finditer(text))
        for certificate_index, certificate in enumerate(certificates, start=1):
            # A completeness certificate is useful only if every following
            # list item is scanned; truncating the window would turn a partial
            # prefix into a false proof of absence.
            window_end = len(text)
            window = text[certificate.start():window_end]
            raw_items: list[tuple[str, int, int]] = []
            for match in _LIST_LINE.finditer(window):
                item = match.group("item").strip(" \t|.;")
                if not any(character.isalnum() for character in item):
                    continue
                start = certificate.start() + match.start("item") + len(match.group("item")) - len(match.group("item").lstrip())
                raw_items.append((item, start, start + len(item)))
            if not raw_items:
                inline = _INLINE_LIST.search(window)
                if inline:
                    for item in _split_inline(inline.group("items")):
                        relative = window.find(item, inline.start("items"))
                        if relative >= 0:
                            raw_items.append((item, certificate.start() + relative, certificate.start() + relative + len(item)))
            # Compact extracted sources often encode a certified index as
            # "TARGETS (N): item; item; ..." on one line.
            if not raw_items:
                targets = re.search(r"(?i)\b(?:targets|items|members|entities)\s*\(\d+\)\s*:\s*(?P<items>.+)", window, re.S)
                if targets:
                    for item in _split_inline(targets.group("items")):
                        relative = window.find(item, targets.start("items"))
                        if relative >= 0:
                            raw_items.append((item, certificate.start() + relative, certificate.start() + relative + len(item)))
            if not raw_items:
                heading = _PLAIN_LIST_HEADING.search(window)
                if heading:
                    after = heading.end()
                    for line in re.finditer(r"(?m)^(?P<item>[^\n]{2,240})$", window[after:]):
                        item = line.group("item").strip(" \t|.;")
                        letters = [character for character in item if character.isalpha()]
                        if not letters or sum(character.isupper() for character in letters) / len(letters) < 0.8:
                            continue
                        start = certificate.start() + after + line.start("item") + len(line.group("item")) - len(line.group("item").lstrip())
                        raw_items.append((item, start, start + len(item)))
            if not raw_items:
                continue
            normalized_items = [normalize(item) for item, _start, _end in raw_items]
            digest = hashlib.sha256("\n".join(normalized_items).encode()).hexdigest()
            certificate_id = f"list:{document.id}:{certificate_index}:certificate"
            current_line_start = text.rfind("\n", 0, certificate.start()) + 1
            previous_line_start = text.rfind("\n", 0, max(0, current_line_start - 1)) + 1
            certificate_start = (
                previous_line_start
                if certificate.start() - previous_line_start <= 300
                and text[previous_line_start:certificate.start()].strip()
                else certificate.start()
            )
            premises[certificate_id] = SymbolicPremise(
                id=certificate_id,
                document_id=document.id,
                text=text[certificate_start:certificate.end()],
                start=utf16_offset(text, certificate_start),
                end=utf16_offset(text, certificate.end()),
                kind="LIST_CERTIFICATE",
                content_hash=digest,
                item_count=len(raw_items),
            )
            for item_index, (item, start, end) in enumerate(raw_items, start=1):
                item_id = f"list:{document.id}:{certificate_index}:item:{item_index}"
                premises[item_id] = SymbolicPremise(
                    id=item_id,
                    document_id=document.id,
                    text=item,
                    start=utf16_offset(text, start),
                    end=utf16_offset(text, end),
                    kind="LIST_ITEM",
                    content_hash=digest,
                )
    return premises


def line_operands(documents: Sequence[RetrievalDocument]) -> dict[str, SymbolicPremise]:
    """Expose compact, exact source rows as typed operand candidates."""
    premises: dict[str, SymbolicPremise] = {}
    for document in documents:
        for index, match in enumerate(re.finditer(r"(?m)^[^\n]{1,500}$", document.text), start=1):
            value = match.group(0).strip()
            if not value or not re.search(r"\d", value) or not re.search(r"[A-Za-z]", value):
                continue
            start = match.start() + len(match.group(0)) - len(match.group(0).lstrip())
            end = start + len(value)
            premise_id = f"operand:{document.id}:line:{index}"
            premises[premise_id] = SymbolicPremise(
                id=premise_id, document_id=document.id, text=value,
                start=utf16_offset(document.text, start), end=utf16_offset(document.text, end),
                kind="OPERAND",
            )
    return premises


def _extremum_operands(atom: PipelineAtom, premises: dict[str, SymbolicPremise]) -> tuple[str, ...]:
    candidates = [item for item in premises.values() if item.kind == "OPERAND"]
    atom_terms = lexical_tokens(atom.text)
    wants_max = bool(re.search(r"\b(?:largest|highest|tallest|most)\b", normalize(atom.text)))

    def values(item: SymbolicPremise) -> list[float]:
        found = []
        for raw in re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", item.text):
            number = float(raw.replace(",", ""))
            if not (1900 <= number <= 2100):
                found.append(number)
        return found

    rows = [
        item for item in candidates
        if "|" in item.text
        and not re.search(r"(?i)^(?:capital city|total|all capitals|regional|---)", item.text.strip())
        and values(item)
    ]
    relevant = rows or [item for item in candidates if values(item)]
    relevant.sort(key=lambda item: (
        0 if lexical_tokens(item.text) & atom_terms else 1,
        -(max(values(item)) if wants_max else -min(values(item))),
        item.id,
    ))
    return tuple(item.id for item in relevant[:8])


def build_candidates(
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[AssessmentAtomEvidence],
    documents: Sequence[RetrievalDocument],
) -> tuple[list[Candidate], dict[str, SymbolicPremise]]:
    documents_by_id = {document.id: document for document in documents}
    premises = evidence_premises(evidence)
    premises.update(list_premises(documents))
    premises.update(line_operands(documents))
    by_atom = {group.atom_id: group for group in evidence}
    candidates: list[Candidate] = []
    for atom in atoms:
        atom_evidence = by_atom[atom.id].spans
        evidence_ids = tuple(
            f"evidence:{atom.id}:{span.document_id}:{span.id}" for span in atom_evidence
        )
        context_ids = tuple(
            f"context:{atom.id}:{context.document_id}:{context.id}"
            for span in atom_evidence for context in span.context_spans
        )
        atom_text = normalize(atom.text)
        # "Among" commonly introduces a study population (for example,
        # "Among US adults") and is not evidence that the claim asks whether
        # an entity belongs to a bounded set. Restrict set-membership
        # candidates to explicit membership/list language.
        if re.search(r"\b(?:list|listed|member|included|designated)\b", atom_text):
            atom_tokens = lexical_tokens(atom.text)
            atom_identities = identity_tokens(atom.text)
            certificates = [
                key for key, premise in premises.items()
                if premise.kind == "LIST_CERTIFICATE"
                and atom_identities & identity_tokens(premise.text)
            ]
            likely_items = [
                key for key, premise in premises.items()
                if premise.kind == "LIST_ITEM"
                and (normalize(premise.text) in atom_text or len(lexical_tokens(premise.text) & atom_tokens) >= 1)
            ][:4]
            list_ids = tuple(certificates + likely_items)
            # Set execution accepts structured list operands only. Direct
            # answer sentences remain part of neural evidence assessment; they
            # are not silently promoted into an exhaustive-list proof.
            allowed = list_ids
            candidates.append(Candidate(
                f"candidate:{atom.id}:set", atom.id, "SET_MEMBERSHIP", allowed, atom.text,
                tuple((premise_id, f"[{premises[premise_id].kind}] {' '.join(premises[premise_id].text.split())[:240]}") for premise_id in allowed),
            ))
        if re.search(r"\b(?:both|two different|two distinct|in .+ and .+)\b", atom_text):
            field_terms = {"physics", "chemistry", "medicine", "literature", "peace", "economics"}
            subject_terms = lexical_tokens(atom.text)
            distinct_operands = tuple(
                key for key, premise in premises.items()
                if premise.kind == "OPERAND"
                and lexical_tokens(premise.text) & field_terms
                and (
                    lexical_tokens(premise.text) & subject_terms
                    or lexical_tokens(documents_by_id[premise.document_id].text[:200]) & subject_terms
                )
            )
            allowed = tuple(dict.fromkeys((*evidence_ids, *distinct_operands)))
            candidates.append(Candidate(
                f"candidate:{atom.id}:distinct", atom.id, "COUNT_DISTINCT", allowed, atom.text,
                tuple((premise_id, f"[{premises[premise_id].kind}] {' '.join(premises[premise_id].text.split())[:240]}") for premise_id in allowed),
            ))
        if re.search(r"\b(?:largest|smallest|highest|lowest|tallest|shortest|most|least)\b", atom_text):
            operand_ids = _extremum_operands(atom, premises)
            allowed = tuple(dict.fromkeys((*evidence_ids, *operand_ids)))
            candidates.append(Candidate(
                f"candidate:{atom.id}:extremum", atom.id, "EXTREMUM_COMPARE", allowed, atom.text,
                tuple((premise_id, f"[{premises[premise_id].kind}] {' '.join(premises[premise_id].text.split())[:240]}") for premise_id in allowed),
            ))
        if re.search(r"\b(?:for|located|originated|invented|developed|has|have|received|won|makes|make|causes|uses)\b", atom_text):
            allowed = tuple(dict.fromkeys((*evidence_ids, *context_ids)))
            candidates.append(Candidate(
                f"candidate:{atom.id}:attribute", atom.id, "ATTRIBUTE_COMPARE", allowed, atom.text,
                tuple((premise_id, f"[{premises[premise_id].kind}] {' '.join(premises[premise_id].text.split())[:240]}") for premise_id in allowed),
            ))
        if re.search(r"(?:[$£€¥]\s*)?\d", atom.text) and (
            re.search(r"[<>≤≥=]|\b(?:more|less|fewer|over|under|at least|at most|equal|than|percent|%)\b", atom_text)
        ):
            candidates.append(Candidate(
                f"candidate:{atom.id}:numeric", atom.id, "NUMERIC_COMPARE", evidence_ids, atom.text,
                tuple((premise_id, f"[{premises[premise_id].kind}] {' '.join(premises[premise_id].text.split())[:240]}") for premise_id in evidence_ids),
            ))
        if (
            not re.search(r"\b(?:largest|smallest|highest|lowest|tallest|shortest|most|least)\b", atom_text)
            and re.search(r"\b(?:before|after|between|during|on|since|until)\b", atom_text)
        ):
            candidates.append(Candidate(
                f"candidate:{atom.id}:temporal", atom.id, "TEMPORAL_COMPARE", evidence_ids, atom.text,
                tuple((premise_id, f"[{premises[premise_id].kind}] {' '.join(premises[premise_id].text.split())[:240]}") for premise_id in evidence_ids),
            ))
    return candidates, premises


def validate_grounding(premises: Iterable[SymbolicPremise], documents: Sequence[RetrievalDocument]) -> None:
    documents_by_id = {document.id: document.text for document in documents}
    for premise in premises:
        document = documents_by_id.get(premise.document_id)
        if document is None:
            raise ValueError(f"Premise {premise.id} references an unknown document")
        encoded = document.encode("utf-16-le")
        grounded = encoded[premise.start * 2:premise.end * 2].decode("utf-16-le")
        if grounded != premise.text:
            raise ValueError(f"Premise {premise.id} is not grounded in its source")
