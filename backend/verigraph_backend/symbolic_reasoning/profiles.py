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
EXPLICIT_NEGATION = "EXPLICIT_NEGATION"
COUNTRY_LOCATION = "COUNTRY_LOCATION"
EXCLUSIVE_PURPOSE = "EXCLUSIVE_PURPOSE"
NOBEL_RECIPIENT = "NOBEL_RECIPIENT"
NOBEL_MOTIVATION = "NOBEL_MOTIVATION"
NOBEL_FIELD_COUNT = "NOBEL_FIELD_COUNT"


NOBEL_FIELDS = ("physics", "chemistry", "medicine", "literature", "peace", "economics")


def nobel_recipient_claim(text: str) -> tuple[str, str] | None:
    """Extract a recipient and prize year without treating ``for 1921`` as a reason."""
    prize_first = re.match(
        r"(?i)^the nobel prize in .+? for (?P<year>\d{4}) was awarded to "
        r"(?P<recipient>.+?)[.!?]?$",
        text.strip(),
    )
    if prize_first:
        return prize_first.group("recipient"), prize_first.group("year")
    recipient_first = re.match(
        r"(?i)^(?P<recipient>.+?) (?:received|was awarded) (?:the )?"
        r"(?P<year>\d{4}) nobel prize(?: in .+?)?[.!?]?$",
        text.strip(),
    )
    if recipient_first:
        return recipient_first.group("recipient"), recipient_first.group("year")
    return None


def nobel_reason(text: str) -> str | None:
    """Extract an award motivation only from ``awarded/received ... for``."""
    if not re.search(r"(?i)\b(?:nobel|prize|award|citation)\b", text):
        return None
    match = re.search(
        r"(?i)\b(?:awarded|received|won|citation)\b[^.!?]{0,100}?\bfor\s+"
        r"(?:his|her|their|its|the)?\s*(?P<reason>[^.!?]+)",
        text,
    )
    return match.group("reason") if match else None


def attribute_profile(atom: PipelineAtom) -> str:
    text = normalize(atom.text)
    if nobel_recipient_claim(atom.text):
        return NOBEL_RECIPIENT
    if nobel_reason(atom.text):
        return NOBEL_MOTIVATION
    if re.search(r"\b(?:located|location)\b", text):
        return COUNTRY_LOCATION
    if "exclusively" in text:
        return EXCLUSIVE_PURPOSE
    return EXPLICIT_NEGATION


def distinct_profile(atom: PipelineAtom) -> str | None:
    text = normalize(atom.text)
    if "nobel" in text and re.search(r"\b(?:field|fields|prize|prizes)\b", text):
        return NOBEL_FIELD_COUNT
    return None


def extract_distinct_values(profile: str, premises: Sequence[SymbolicPremise]) -> set[str]:
    if profile != NOBEL_FIELD_COUNT:
        return set()
    return {
        value
        for premise in premises
        for value in NOBEL_FIELDS
        if re.search(rf"\b{value}\b", normalize(premise.text))
    }


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
