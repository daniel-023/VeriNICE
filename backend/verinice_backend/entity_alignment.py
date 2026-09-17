"""Deterministic identity alignment over spaCy-proposed entity mentions.

spaCy is deliberately limited to locating likely names.  Whether two names
refer to the same identity is decided here with exact normalization and aliases
that are explicitly established inside one source document.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Mapping, Sequence

from .settings import settings


class EntityAlignmentConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EntityMention:
    text: str
    normalized: str
    start: int
    end: int
    label: str


@dataclass(frozen=True)
class AlignmentResult:
    status: str
    required_entities: tuple[str, ...]
    matched_entities: tuple[str, ...]
    reason: str


_IDENTITY_LABELS = {
    "PERSON", "ORG", "GPE", "LOC", "FAC", "PRODUCT", "EVENT", "WORK_OF_ART",
}
_HONORIFICS = {
    "dr", "doctor", "mr", "mrs", "ms", "miss", "prof", "professor", "sir",
    "dame", "saint", "st", "president", "prime minister", "king", "queen",
}
_ARTICLES = {"a", "an", "the"}
_ACRONYM_RE = re.compile(
    r"(?<![\w])(?:[A-Z]{2,}(?:[.-][A-Z0-9]{1,})*|[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?![\w])"
)
_PAREN_ALIAS_RE = re.compile(
    r"\b(?P<name>[A-Z][A-Za-z0-9&'’ .-]{2,100}?)\s*\((?P<alias>[A-Z][A-Z0-9.-]{1,20})\)"
)
_KNOWN_AS_RE = re.compile(
    r"(?i)\b(?P<name>[A-Za-z][A-Za-z0-9&'’ .-]{2,100}?),?\s+"
    r"(?:also\s+known\s+as|known\s+as|abbreviated\s+as|shortened\s+to)\s+"
    r"(?P<alias>[A-Za-z][A-Za-z0-9&'’ .-]{1,60})"
)
_STANDS_FOR_RE = re.compile(
    r"(?i)\b(?P<alias>[A-Z][A-Z0-9.-]{1,20})\s+stands\s+for\s+"
    r"(?P<name>[A-Za-z][A-Za-z0-9&'’ .-]{2,100})"
)
_NLP = None
_NLP_ERROR: Exception | None = None
_NLP_LOCK = threading.Lock()


def normalize_entity(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[’']s\b", "", value)
    value = re.sub(r"[^\w\s-]", " ", value, flags=re.UNICODE)
    value = re.sub(r"[-_]", " ", value)
    tokens = value.split()
    while tokens and tokens[0] in _ARTICLES | _HONORIFICS:
        tokens.pop(0)
    # NER sometimes attaches an award edition year to the following title.
    # Years are temporal qualifiers, not part of the identity key.
    if len(tokens) > 1 and re.fullmatch(r"(?:19|20)\d{2}", tokens[0]):
        tokens.pop(0)
    normalized = " ".join(tokens)
    return {
        "us": "united states",
        "u s": "united states",
        "usa": "united states",
        "uk": "united kingdom",
        "u k": "united kingdom",
        "covid": "covid 19",
    }.get(normalized, normalized)


def _load_nlp():
    global _NLP, _NLP_ERROR
    if _NLP is not None:
        return _NLP
    if _NLP_ERROR is not None:
        raise EntityAlignmentConfigurationError(
            f"Entity alignment requires the configured spaCy model '{settings.entity_model}'. "
            "Run ./run-verinice --prepare."
        ) from _NLP_ERROR
    with _NLP_LOCK:
        if _NLP is not None:
            return _NLP
        try:
            import spacy

            _NLP = spacy.load(settings.entity_model, disable=["parser", "lemmatizer"])
        except (ImportError, OSError) as error:
            _NLP_ERROR = error
            raise EntityAlignmentConfigurationError(
                f"Entity alignment requires the configured spaCy model '{settings.entity_model}'. "
                "Run ./run-verinice --prepare."
            ) from error
    return _NLP


def entity_model_ready() -> bool:
    try:
        _load_nlp()
        return True
    except EntityAlignmentConfigurationError:
        return False


@lru_cache(maxsize=2048)
def extract_identity_mentions(text: str) -> tuple[EntityMention, ...]:
    doc = _load_nlp()(text)
    candidates = [
        EntityMention(ent.text, normalize_entity(ent.text), ent.start_char, ent.end_char, ent.label_)
        for ent in doc.ents
        if ent.label_ in _IDENTITY_LABELS and normalize_entity(ent.text)
    ]
    for match in _ACRONYM_RE.finditer(text):
        candidates.append(EntityMention(
            match.group(0), normalize_entity(match.group(0)), match.start(), match.end(), "IDENTIFIER"
        ))
    # Country names are deterministic high-value recovery for NER misses.
    try:
        import pycountry

        country_names = {
            country.name for country in pycountry.countries
        } | {
            getattr(country, "official_name", "") for country in pycountry.countries
        }
        for name in sorted(filter(None, country_names), key=len, reverse=True):
            for match in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
                candidates.append(EntityMention(
                    match.group(0), normalize_entity(match.group(0)), match.start(), match.end(), "GPE"
                ))
    except ImportError:
        pass
    # Prefer the longest span when detectors overlap and preserve source order.
    candidates.sort(key=lambda item: (item.start, -(item.end - item.start), item.label))
    selected: list[EntityMention] = []
    for item in candidates:
        if any(item.start < other.end and item.end > other.start for other in selected):
            continue
        selected.append(item)
    return tuple(sorted(selected, key=lambda item: (item.start, item.end)))


def _connect(graph: dict[str, set[str]], left: str, right: str) -> None:
    if not left or not right or left == right:
        return
    graph.setdefault(left, {left}).add(right)
    graph.setdefault(right, {right}).add(left)


def build_document_aliases(text: str) -> dict[str, frozenset[str]]:
    """Return alias equivalence classes proven inside one document."""
    graph: dict[str, set[str]] = {}
    mentions = extract_identity_mentions(text)
    for mention in mentions:
        graph.setdefault(mention.normalized, {mention.normalized})
    for pattern in (_PAREN_ALIAS_RE, _KNOWN_AS_RE, _STANDS_FOR_RE):
        for match in pattern.finditer(text):
            _connect(
                graph,
                normalize_entity(match.group("name")),
                normalize_entity(match.group("alias")),
            )
    # A one-token person form is safe only when that component identifies one
    # full person in this document and the model detected the full person.
    people = {
        mention.normalized for mention in mentions
        if mention.label == "PERSON" and len(mention.normalized.split()) >= 2
    }
    by_component: dict[str, set[str]] = {}
    for person in people:
        for component in person.split():
            by_component.setdefault(component, set()).add(person)
    for component, full_names in by_component.items():
        if len(full_names) == 1 and re.search(
            rf"(?<!\w){re.escape(component)}(?!\w)", normalize_entity(text)
        ):
            _connect(graph, next(iter(full_names)), component)

    # Compute small transitive closures so chained explicit aliases work.
    result: dict[str, frozenset[str]] = {}
    for node in graph:
        seen, pending = set(), [node]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(graph.get(current, ()) - seen)
        result[node] = frozenset(seen)
    return result


def _accepted_names(required: str, aliases: Mapping[str, frozenset[str]]) -> set[str]:
    accepted = {required}
    accepted.update(aliases.get(required, ()))
    # The claim can use the full form while selected evidence uses a short form
    # whose equivalence class is established elsewhere in this same document.
    for name, equivalents in aliases.items():
        if required in equivalents:
            accepted.add(name)
            accepted.update(equivalents)
    return accepted


def align_identities(
    atom_text: str,
    selected_by_document: Mapping[str, Sequence[str]],
    document_texts: Mapping[str, str],
    *,
    relation: str = "SUPPORTS",
    strict_refutation: bool = False,
) -> AlignmentResult:
    required_mentions = extract_identity_mentions(atom_text)
    required = tuple(dict.fromkeys(item.normalized for item in required_mentions))
    display = {item.normalized: item.text for item in required_mentions}
    if not required:
        return AlignmentResult(
            "NOT_APPLICABLE", (), (), "The atomic claim has no identity-bearing named mention."
        )
    matched: list[str] = []
    conflicting: list[str] = []
    for required_mention in required_mentions:
        required_name = required_mention.normalized
        if required_name in matched:
            continue
        found = False
        competing = False
        for document_id, selected_texts in selected_by_document.items():
            aliases = build_document_aliases(document_texts.get(document_id, ""))
            accepted = _accepted_names(required_name, aliases)
            evidence_mentions = [
                mention
                for text in selected_texts
                for mention in extract_identity_mentions(text)
            ]
            evidence_names = {mention.normalized for mention in evidence_mentions}
            if accepted & evidence_names:
                found = True
                break
            same_type = {
                mention.normalized for mention in evidence_mentions
                if mention.label == required_mention.label
                and required_mention.label in {"PERSON", "ORG"}
            }
            competing = competing or bool(same_type - accepted)
        if found:
            matched.append(required_name)
        elif competing:
            conflicting.append(required_name)
    required_display = tuple(display[item] for item in required)
    matched_display = tuple(display[item] for item in matched)
    decisive_conflict = bool(conflicting) and (
        relation == "SUPPORTS" or strict_refutation
    )
    if not decisive_conflict:
        return AlignmentResult(
            "ALIGNED", required_display, matched_display,
            "No conflicting subject identity appears in the selected evidence; exact document-local matches were retained.",
        )
    missing = [display[item] for item in conflicting]
    return AlignmentResult(
        "UNRESOLVED", required_display, matched_display,
        "Selected evidence does not establish the claimed identity: " + ", ".join(missing) + ".",
    )


def grouped_selected_texts(items: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for document_id, text in items:
        grouped.setdefault(document_id, []).append(text)
    return grouped
