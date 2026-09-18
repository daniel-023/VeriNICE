from __future__ import annotations

import re
import unicodedata
from typing import Sequence

from ..schemas import PipelineAtom, SymbolicPremise


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def lexical_tokens(text: str) -> set[str]:
    text = "".join(
        " " if unicodedata.category(character).startswith("S") else character
        for character in text
    )
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9'-]*", normalize(text))
        if token
        not in {
            "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
            "has", "have", "in", "is", "it", "of", "on", "or", "that", "the",
            "to", "was", "were", "with",
        }
    }


GENERIC_SET_MEMBERSHIP = "GENERIC_SET_MEMBERSHIP"
GENERIC_NUMERIC_THRESHOLD = "GENERIC_NUMERIC_THRESHOLD"
GENERIC_ABSOLUTE_DATE = "GENERIC_ABSOLUTE_DATE"
GENERIC_EVENT_ORDER = "GENERIC_EVENT_ORDER"
GENERIC_EXTREMUM_COUNTEREXAMPLE = "GENERIC_EXTREMUM_COUNTEREXAMPLE"
GENERIC_DISTINCT_VALUES = "GENERIC_DISTINCT_VALUES"
EXPLICIT_NEGATION = "EXPLICIT_NEGATION"
COUNTRY_LOCATION = "COUNTRY_LOCATION"
EXCLUSIVE_PURPOSE = "EXCLUSIVE_PURPOSE"

_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_DISTINCT_COUNT = re.compile(
    r"(?i)\b(?P<bound>at\s+least|no\s+fewer\s+than|exactly)?\s*"
    r"(?P<count>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(?:(?:different|distinct)\s+)?(?P<category>[a-z][a-z -]{0,60}?)(?:[.!?]|$)"
)
_DISTINCT_PREDICATES = {
    "contain": ("contain", "contains", "contained"),
    "include": ("include", "includes", "included"),
    "offer": ("offer", "offers", "offered"),
    "receive": ("receive", "receives", "received", "win", "wins", "won", "earn", "earns", "earned"),
    "support": ("support", "supports", "supported"),
    "use": ("use", "uses", "used"),
}
_EXTREMUM = re.compile(
    r"(?i)(?<!at )\b(largest|smallest|highest|lowest|tallest|shortest|most|least)\b"
)


def extremum_term(text: str) -> str | None:
    """Return a true superlative, excluding numeric bound phrases."""
    match = _EXTREMUM.search(normalize(text))
    return match.group(1).casefold() if match else None


def attribute_profile(atom: PipelineAtom) -> str | None:
    """Return a bounded, domain-neutral attribute profile when one applies.

    Recipient and motivation relations are intentionally not special-cased.
    Direct evidence resolves positive attributions; symbolic attribute checks
    are reserved for the general patterns implemented by the executor.
    """
    text = normalize(atom.text)
    if re.search(r"\b(?:located|location)\b", text):
        return COUNTRY_LOCATION
    if "exclusively" in text:
        return EXCLUSIVE_PURPOSE
    if re.search(
        r"\b(?:is|are|has|have|invented|created|developed|makes|make|causes|uses)\b"
        r"|\bawarded\s+for\b",
        text,
    ):
        return EXPLICIT_NEGATION
    return None


def exclusive_purpose_counterexample(claim_text: str, evidence_text: str) -> bool:
    """Match an explicit military development purpose against civilian-only development."""
    claim = normalize(claim_text)
    if "exclusively" not in claim or not re.search(r"\bcivil(?:ian)?\b", claim):
        return False
    return bool(re.search(
        r"(?is)\b(?:developed|development|designed|conceived)\b.{0,160}?"
        r"\bmilitary\b|\bmilitary\b.{0,160}?"
        r"\b(?:developed|development|designed|conceived)\b",
        evidence_text,
    ))


def distinct_profile(atom: PipelineAtom) -> str | None:
    if not distinct_count_request(atom):
        return None
    return GENERIC_DISTINCT_VALUES


def distinct_count_request(atom: PipelineAtom) -> tuple[int, bool, str] | None:
    """Return the requested count, exactness, and category for a supported claim."""
    text = normalize(atom.text)
    match = _DISTINCT_COUNT.search(text)
    if not match:
        return None
    # A bare number is not a count request merely because it precedes a noun
    # (for example, an edition or year in an award title). The requested count
    # must occur after one of the domain-neutral value-bearing predicates that
    # the extractor knows how to align in both the claim and its premises.
    predicate_positions = [
        predicate.start()
        for forms in _DISTINCT_PREDICATES.values()
        for form in forms
        if (predicate := re.search(rf"\b{re.escape(form)}\b", text))
    ]
    if not predicate_positions or min(predicate_positions) >= match.start():
        return None
    raw_count = match.group("count").casefold()
    expected = _COUNT_WORDS.get(raw_count, int(raw_count) if raw_count.isdigit() else 0)
    if expected < 1:
        return None
    exact = normalize(match.group("bound") or "") not in {"at least", "no fewer than"}
    return expected, exact, normalize(match.group("category")).strip(" .!?")


def _singular(value: str) -> str:
    if value.endswith("ies") and len(value) > 3:
        return f"{value[:-3]}y"
    if value.endswith("s") and not value.endswith("ss") and len(value) > 1:
        return value[:-1]
    return value


def _category_labels(category: str) -> tuple[str, ...]:
    words = category.split()
    singular_words = [*words[:-1], _singular(words[-1])]
    labels = {category, " ".join(singular_words), words[-1], singular_words[-1]}
    return tuple(sorted((label for label in labels if label), key=len, reverse=True))


def _claim_frame(atom: PipelineAtom) -> tuple[set[str], tuple[str, ...]]:
    text = normalize(atom.text)
    matches = [
        (text.find(form), forms)
        for forms in _DISTINCT_PREDICATES.values()
        for form in forms
        if text.find(f" {form} ") >= 0
    ]
    if not matches:
        return set(), ()
    position, forms = min(matches, key=lambda item: item[0])
    subject = text[:position].strip()
    return lexical_tokens(subject), forms


def distinct_subject_terms(atom: PipelineAtom) -> set[str]:
    """Return the explicit subject terms that a distinct-value premise must ground."""
    return _claim_frame(atom)[0]


def _explicit_values(raw: str, category_labels: Sequence[str]) -> set[str]:
    raw = re.split(r"(?i)\b(?:which|that|while|during|because|since)\b", raw, maxsplit=1)[0]
    values: set[str] = set()
    for part in re.split(r"\s*(?:,|;|\band\b|\bor\b)\s*", raw):
        value = normalize(part).strip(" \t,;:.()[]{}\"'“”")
        value = re.sub(r"^(?:a|an|the)\s+", "", value)
        for label in category_labels:
            value = re.sub(rf"^(?:{re.escape(label)})\s+", "", value)
        if not value or len(value.split()) > 8 or re.search(r"\b(?:at least|no fewer than|different|distinct)\b", value):
            continue
        values.add(value)
    return values


def extract_distinct_values(
    profile: str,
    premises: Sequence[SymbolicPremise],
    atom: PipelineAtom | None = None,
) -> set[str]:
    if profile != GENERIC_DISTINCT_VALUES or atom is None:
        return set()
    request = distinct_count_request(atom)
    if not request:
        return set()
    _expected, _exact, category = request
    labels = _category_labels(category)
    subject_terms, predicate_forms = _claim_frame(atom)
    if not subject_terms or not predicate_forms:
        return set()
    values: set[str] = set()
    label_pattern = "|".join(re.escape(label) for label in labels)
    predicate_pattern = "|".join(re.escape(form) for form in predicate_forms)
    for premise in premises:
        text = normalize(premise.text)
        subject_aligned = subject_terms.issubset(lexical_tokens(text))
        if not subject_aligned:
            continue
        labelled = list(re.finditer(
            rf"\b(?:{label_pattern})\b\s*(?::|=|\bis\b|\bare\b|\bwas\b|\bwere\b)\s*(?P<values>[^.;\n]+)",
            text,
        ))
        if labelled:
            for match in labelled:
                values.update(_explicit_values(match.group("values"), labels))
            continue
        award_values = list(re.finditer(
            r"(?i)\b(?:prize|award)\s+in\s+(?P<value>[a-z][a-z -]{0,60}?)(?:\s+(?:19|20)\d{2}\b|[.;\n]|$)",
            text,
        ))
        if award_values:
            for match in award_values:
                values.update(_explicit_values(match.group("value"), labels))
            continue
        predicate = re.search(
            rf"\b(?:{predicate_pattern})\b\s+(?P<values>[^.;\n]+)", text
        )
        if not predicate:
            continue
        tail = predicate.group("values")
        if re.search(r"\bin\s+", tail):
            tail = re.split(r"\bin\s+", tail)[-1]
        values.update(_explicit_values(tail, labels))
    return values


def scoped_negative_clause(
    subject: str,
    property_terms: set[str],
    premise: SymbolicPremise,
) -> bool:
    """Require negation, the subject, and the claimed property in one clause."""
    clauses = re.split(r"(?i)[.;]|\b(?:but|although|however|whereas|while)\b|\band\s+(?=(?:is|was|has|does|did|can|will)\b)", premise.text)
    subject_terms = lexical_tokens(subject)
    for clause in clauses:
        terms = lexical_tokens(clause)
        if not subject_terms & terms or not property_terms & terms:
            continue
        if re.search(
            r"(?i)\b(?:no|not|never|without|did not|does not|will not|won['’]t|cannot|can['’]t|false|myth)\b",
            clause,
        ):
            return True
    return False
