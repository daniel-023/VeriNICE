"""Deterministic grounding, normalization, and warnings for decompositions."""

from __future__ import annotations

import re

from .claim_decomposition_errors import DecompositionOutputError
from .schemas import (
    ClaimComposition,
    ClaimDecompositionDraft,
    DecomposedAtom,
    DecompositionResponse,
    DecompositionWarning,
    ObligationRole,
)
from .segmentation import segment_document
from .text_offsets import utf16_offset


SEMANTIC_REPAIR_CODES = frozenset(
    {"MULTIPLE_NUMERIC_ASSERTIONS", "UNDER_DECOMPOSED"}
)

_WHOLE_CLAIM_COVERAGE = 0.9
_ADDED_EDGE_PUNCTUATION = " \t\n\r.,;:!?\"'’”"
_MIN_LOCATOR_CHARACTERS = 4

_TERM = re.compile(r"[^\W_]+", re.UNICODE)
_NUMBER = re.compile(r"(?<!\w)[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:%|°[CF])?(?!\w)")
_CLAUSE_BOUNDARY = re.compile(
    r"\s*(?:;|(?<!\d),(?!\d)|\b(?:and|but|while|whereas)\b)\s*",
    re.IGNORECASE,
)
_PREDICATE_CUE = re.compile(
    r"\b(?:am|are|is|was|were|be|been|being|can|could|did|do|does|had|has|have|"
    r"may|might|must|shall|should|will|would|added|bought|closed|created|cut|"
    r"decreased|died|dropped|eliminated|earned|fell|fired|gained|grew|hired|"
    r"increased|killed|lost|made|opened|paid|reduced|restored|rose|sold|spent|"
    r"won|became)\b|\b\w+(?:'re|'ve|'s)\b",
    re.IGNORECASE,
)
_INTRODUCED_REFERENCE = re.compile(
    r"\b(?:this|these|those|such)\s+([^\W\d_]+)|\b(?:the\s+)?(?:former|latter)\b",
    re.IGNORECASE,
)
_LEADING_REFERENCE = re.compile(
    r"^\s*(?:he|she|they|it|his|her|their|its)\b", re.IGNORECASE
)
_GENDERED_POSSESSIVE = re.compile(
    r"\b(?:his|her(?=\s+[^\W\d_]))\b", re.IGNORECASE
)
_LEADING_DEFINITE_HEAD = re.compile(
    r"^(?P<prefix>\s*)the\s+(?P<head>[^\W\d_]+)\b", re.IGNORECASE
)
_COPULA = r"(?:is|are|was|were|has|have|had)"
_PROPER_NAME = re.compile(r"\b[A-Z][^\W\d_]*(?:[-'’][A-Z]?[^\W\d_]*)?\b")
_PROPER_NAME_SEQUENCE = re.compile(
    r"\b[A-Z][^\W\d_]*(?:[-'’][A-Z]?[^\W\d_]*)?"
    r"(?:\s+[A-Z][^\W\d_]*(?:[-'’][A-Z]?[^\W\d_]*)?)+\b"
)
_NON_NAME_CAPITALIZED = {
    "a", "an", "his", "her", "the", "this", "that", "these", "those",
}
_ATTRIBUTION_CUE = re.compile(
    r"\b(?:according to|alleged|announced|claimed|concluded|reported|said|stated|"
    r"testified|told|wrote)\b",
    re.IGNORECASE,
)
_ASSOCIATION_CUE = re.compile(
    r"\b(?:associated with|association with|correlated with|correlation with)\b",
    re.IGNORECASE,
)
_AWARD_RELATION = re.compile(r"\bawarded\s+(?:to|for)\b", re.IGNORECASE)
_NUMERIC_CONSTRAINT_CUE = re.compile(
    r"\b(?:at least|at most|fewer than|more than|less than|no fewer than|"
    r"no more than|over|under)\b",
    re.IGNORECASE,
)
_COVERING_STOP_WORDS = {
    "a", "after", "already", "an", "and", "are", "as", "at", "be", "been",
    "by", "for", "from", "going", "had", "has", "have", "in", "is", "it", "of",
    "on", "or", "re", "right", "that", "the", "their", "they", "this", "through",
    "time", "to", "was", "we", "were", "where", "will", "with",
}


def numeric_assertion_clauses(claim: str) -> list[str]:
    """Return high-confidence clause-separated quantified predicates."""
    clauses = [part for part in _CLAUSE_BOUNDARY.split(claim) if part.strip()]
    return [
        clause
        for clause in clauses
        if _NUMBER.search(clause) and _PREDICATE_CUE.search(clause)
    ]


def semantic_repair_errors(result: DecompositionResponse) -> str | None:
    triggering = [
        warning for warning in result.warnings if warning.code in SEMANTIC_REPAIR_CODES
    ]
    if not triggering:
        return None
    return "\n".join(f"{warning.code}: {warning.message}" for warning in triggering)


def validate_and_normalize(
    claim: str, draft: ClaimDecompositionDraft, model: str
) -> DecompositionResponse:
    """Validate model-owned fields and construct server-owned atom metadata."""
    obligations = draft.obligations
    if draft.composition is ClaimComposition.single and len(obligations) != 1:
        raise DecompositionOutputError(
            "SINGLE decompositions must contain exactly one obligation."
        )
    if (
        draft.composition in {ClaimComposition.and_, ClaimComposition.or_}
        and len(obligations) < 2
    ):
        raise DecompositionOutputError(
            "AND and OR decompositions must contain at least two obligations."
        )

    texts = [item.text.strip() for item in obligations]
    if len(texts) != len(set(texts)):
        raise DecompositionOutputError(
            "Decomposition obligations must not be exact duplicates."
        )

    atoms: list[DecomposedAtom] = []
    source_texts: list[str] = []
    for index, obligation in enumerate(obligations, start=1):
        text = obligation.text.strip()
        if (
            draft.composition is ClaimComposition.single
            and len(obligations) == 1
            and len(segment_document(claim)) == 1
        ):
            text = claim.strip()
        source_text = obligation.source_text
        if not text or not source_text.strip():
            raise DecompositionOutputError(
                "Decomposition obligations and sourceText values cannot be blank."
            )
        start, source_text = _locate_source_text(claim, source_text)
        if start < 0:
            raise DecompositionOutputError(
                "Every sourceText value must be an exact, uniquely occurring contiguous "
                f"substring of the claim. This one is missing or ambiguous: {source_text!r}. "
                "Quote a more specific span that appears verbatim exactly once, even if it "
                "is only a fragment."
            )
        text = _resolve_named_definite_reference(claim, text, start, index)
        text = _resolve_named_person_reference(claim, text, source_text, start, index)
        source_texts.append(source_text)
        atoms.append(
            DecomposedAtom(
                id=f"atom-{index}",
                text=text,
                source_text=source_text,
                start=utf16_offset(claim, start),
                end=utf16_offset(claim, start + len(source_text)),
                role=_normalize_role(text, obligation.role),
            )
        )

    warnings = _collect_warnings(claim, draft.composition, atoms, source_texts)
    atoms, covering_warning = _remove_redundant_covering_atom(atoms)
    if covering_warning is not None:
        warnings.append(covering_warning)
    return DecompositionResponse(
        composition=draft.composition,
        atoms=atoms,
        warnings=warnings,
        model=model,
    )


def _collect_warnings(
    claim: str,
    composition: ClaimComposition,
    atoms: list[DecomposedAtom],
    source_texts: list[str],
) -> list[DecompositionWarning]:
    warnings: list[DecompositionWarning] = []
    if len(source_texts) != len(set(source_texts)):
        warnings.append(
            _warning(
                "REUSED_SOURCE_TEXT",
                "One sourceText span grounds more than one obligation.",
            )
        )
    if any(len(source.strip()) < 4 for source in source_texts):
        warnings.append(
            _warning(
                "AMBIGUOUS_SOURCE_TEXT",
                "A very short sourceText span may be ambiguous in the original claim.",
            )
        )
    if _is_under_decomposed(claim, source_texts):
        warnings.append(
            _warning(
                "UNDER_DECOMPOSED",
                "A claim of several sentences produced one obligation covering "
                "almost all of it, so its separate assertions were not separated.",
            )
        )
    if (
        composition is ClaimComposition.single
        and len(atoms) == 1
        and len(segment_document(claim)) == 1
        and len(numeric_assertion_clauses(claim)) >= 2
    ):
        warnings.append(
            _warning(
                "MULTIPLE_NUMERIC_ASSERTIONS",
                "A SINGLE result contains multiple clause-separated numeric "
                "predicates. Return AND with one standalone obligation for each "
                "independently asserted value; do not split comparisons or ranges.",
            )
        )
    if _has_non_standalone_reference(atoms):
        warnings.append(
            _warning(
                "NON_STANDALONE_REFERENCE",
                "A reconstructed obligation introduces a reference whose antecedent "
                "is not present in that obligation.",
            )
        )
    if _has_unresolved_person_reference(claim, atoms):
        warnings.append(
            _warning(
                "UNRESOLVED_PERSON_REFERENCE",
                "A reconstructed obligation uses a gendered possessive without "
                "naming its in-claim antecedent.",
            )
        )
    return warnings


def _warning(code: str, message: str) -> DecompositionWarning:
    return DecompositionWarning(code=code, message=message)


def _is_under_decomposed(claim: str, source_texts: list[str]) -> bool:
    return (
        len(source_texts) == 1
        and len(segment_document(claim)) >= 2
        and len(source_texts[0].strip()) >= _WHOLE_CLAIM_COVERAGE * len(claim.strip())
    )


def _locate_source_text(claim: str, source_text: str) -> tuple[int, str]:
    start = claim.find(source_text)
    if start >= 0 and claim.count(source_text) == 1:
        return start, source_text
    trimmed = source_text.strip().strip(_ADDED_EDGE_PUNCTUATION)
    if not trimmed:
        return -1, source_text
    start = claim.find(trimmed)
    if start >= 0 and claim.count(trimmed) == 1:
        return start, trimmed
    words = trimmed.split()
    for dropped in range(1, len(words)):
        candidate = " ".join(words[dropped:]).strip(_ADDED_EDGE_PUNCTUATION)
        if len(candidate) < _MIN_LOCATOR_CHARACTERS:
            break
        if claim.count(candidate) == 1:
            return claim.find(candidate), candidate
    return -1, source_text


def _has_non_standalone_reference(atoms: list[DecomposedAtom]) -> bool:
    if len(atoms) < 2:
        return False
    for atom_index, atom in enumerate(atoms):
        if atom_index == 0 and atom.start == 0:
            continue
        if _LEADING_REFERENCE.search(atom.text):
            return True
        for match in _INTRODUCED_REFERENCE.finditer(atom.text):
            head = match.group(1)
            if head is None or not re.search(
                rf"\b{re.escape(head)}\b", atom.text[: match.start()], re.IGNORECASE
            ):
                return True
    return False


def _has_unresolved_person_reference(claim: str, atoms: list[DecomposedAtom]) -> bool:
    if len(atoms) < 2:
        return False
    for atom_index, atom in enumerate(atoms):
        if atom_index == 0 and atom.start == 0:
            continue
        for match in _GENDERED_POSSESSIVE.finditer(atom.text):
            reconstructed_names = {
                token.casefold()
                for token in _PROPER_NAME.findall(atom.text[: match.start()])
            } - _NON_NAME_CAPITALIZED
            source_match = _GENDERED_POSSESSIVE.search(atom.source_text)
            if source_match is None:
                if not reconstructed_names:
                    return True
                continue
            source_start = claim.find(atom.source_text)
            absolute_reference = source_start + source_match.start()
            claim_names = [
                token.casefold()
                for token in _PROPER_NAME.findall(claim[:absolute_reference])
                if token.casefold() not in _NON_NAME_CAPITALIZED
            ]
            if claim_names and claim_names[-1] not in reconstructed_names:
                return True
    return False


def _resolve_named_person_reference(
    claim: str, text: str, source_text: str, source_start: int, atom_index: int
) -> str:
    if atom_index == 1 and source_start == 0:
        return text
    text_match = _GENDERED_POSSESSIVE.search(text)
    source_match = _GENDERED_POSSESSIVE.search(source_text)
    if text_match is None or source_match is None:
        return text
    antecedent = _nearest_named_antecedent(claim, source_start + source_match.start())
    if antecedent is None or antecedent.casefold() in text[: text_match.start()].casefold():
        return text
    possessive = antecedent + ("'" if antecedent.endswith("s") else "'s")
    return text[: text_match.start()] + possessive + text[text_match.end() :]


def _resolve_named_definite_reference(
    claim: str, text: str, source_start: int, atom_index: int
) -> str:
    """Expand a short leading definite reference from an earlier named phrase.

    This deliberately handles only a conservative shape: a later atom starts
    with ``the <head>`` and the preceding claim contains a longer, capitalized
    noun phrase with the same head immediately before a copula. It therefore
    resolves references such as ``the prize`` without guessing at ordinary
    descriptions such as ``the result``.
    """
    if atom_index == 1 or source_start <= 0:
        return text
    reference = _LEADING_DEFINITE_HEAD.match(text)
    if reference is None:
        return text
    head = reference.group("head")
    antecedent_pattern = re.compile(
        rf"\b(The\s+[A-Z][^,;.!?]{{0,140}}?\b{re.escape(head)}\b"
        rf"[^,;.!?]{{0,80}}?)\s+{_COPULA}\b",
        re.IGNORECASE,
    )
    candidates = [
        match.group(1).strip()
        for match in antecedent_pattern.finditer(claim[:source_start])
        if len(match.group(1).split()) > 2
    ]
    if not candidates:
        return text
    antecedent = candidates[-1]
    return (
        text[: reference.start()]
        + antecedent
        + text[reference.end() :]
    )


def _nearest_named_antecedent(claim: str, before: int) -> str | None:
    prefix = claim[:before]
    candidates: list[tuple[int, int, str]] = []
    for match in _PROPER_NAME_SEQUENCE.finditer(prefix):
        words = match.group(0).split()
        while words and words[0].casefold() in _NON_NAME_CAPITALIZED:
            words.pop(0)
        if words:
            candidates.append((match.end(), len(words), " ".join(words)))
    for match in _PROPER_NAME.finditer(prefix):
        if match.group(0).casefold() not in _NON_NAME_CAPITALIZED:
            candidates.append((match.end(), 1, match.group(0)))
    return max(candidates, default=(0, 0, ""))[2] or None


def _normalize_role(text: str, role: ObligationRole) -> ObligationRole:
    if role is ObligationRole.causal_relation and _ASSOCIATION_CUE.search(text):
        return ObligationRole.core
    if (
        role in {ObligationRole.attribution, ObligationRole.causal_relation}
        and _AWARD_RELATION.search(text)
    ):
        return ObligationRole.core
    if role is ObligationRole.attribution and not _ATTRIBUTION_CUE.search(text):
        return ObligationRole.core
    if role is ObligationRole.core and _NUMERIC_CONSTRAINT_CUE.search(text):
        return ObligationRole.numeric_constraint
    return role


def _remove_redundant_covering_atom(
    atoms: list[DecomposedAtom],
) -> tuple[list[DecomposedAtom], DecompositionWarning | None]:
    if len(atoms) < 3:
        return atoms, None
    covering = next(
        (
            outer
            for outer in atoms
            if all(
                other.id == outer.id
                or (outer.start <= other.start and outer.end >= other.end)
                for other in atoms
            )
        ),
        None,
    )
    if covering is None:
        return atoms, None
    components = [atom for atom in atoms if atom.id != covering.id]
    component_terms = set().union(*(_semantic_terms(atom.text) for atom in components))
    if _semantic_terms(covering.text) - component_terms:
        return atoms, None
    retained = [atom for atom in atoms if atom.id != covering.id]
    retained = [
        atom.model_copy(update={"id": f"atom-{index}"})
        for index, atom in enumerate(retained, start=1)
    ]
    return retained, _warning(
        "REDUNDANT_COVERING_OBLIGATION_REMOVED",
        "A broad obligation duplicated every component obligation and was removed "
        "before retrieval.",
    )


def _semantic_terms(text: str) -> set[str]:
    return {
        term
        for term in (token.casefold() for token in _TERM.findall(text))
        if term not in _COVERING_STOP_WORDS
    }
