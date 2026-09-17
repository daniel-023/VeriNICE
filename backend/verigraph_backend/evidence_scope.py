"""Conservative, deterministic jurisdiction checks for retrieved evidence.

This module filters only explicit geographic mismatches. It never establishes
support or refutation and never treats missing geography as a mismatch.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, Sequence
from urllib.parse import urlparse

import pycountry

from .schemas import (
    AssessmentAtomEvidence,
    DemoDocument,
    EvidenceScopeCheck,
    EvidenceScopeStatus,
    PipelineAtom,
)


_MANUAL_ALIASES: dict[str, str] = {
    "united states": "US",
    "united states of america": "US",
    "america": "US",
    "usa": "US",
    "u s a": "US",
    "u s": "US",
    "united kingdom": "GB",
    "great britain": "GB",
    "britain": "GB",
    "uk": "GB",
    "u k": "GB",
    "new zealand": "NZ",
    "nz": "NZ",
    "n z": "NZ",
    "european union": "EU",
    "eu": "EU",
    "e u": "EU",
    # High-precision, commonly used single-word subdivisions. Other
    # single-word entries from ISO-3166-2 are intentionally excluded.
    "ontario": "CA",
}

_DOMAIN_SCOPES = {
    "state.gov": "US",
    "legislation.gov.au": "AU",
    "europa.eu": "EU",
    "gov.uk": "GB",
    "govt.nz": "NZ",
}


def _normalized(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


@lru_cache(maxsize=1)
def _aliases() -> dict[str, frozenset[str]]:
    aliases: dict[str, set[str]] = {}

    def add(alias: str, code: str, *, allow_short: bool = False) -> None:
        key = _normalized(alias)
        if len(key) >= 3 or allow_short:
            aliases.setdefault(key, set()).add(code)

    for country in pycountry.countries:
        add(country.name, country.alpha_2)
        official = getattr(country, "official_name", "")
        common = getattr(country, "common_name", "")
        if official:
            add(official, country.alpha_2)
        if common:
            add(common, country.alpha_2)
    # Subdivision names are noisy: pycountry contains ordinary English words
    # such as "Most". A bare single word is therefore not safe evidence of a
    # jurisdiction. Multi-word names remain useful and specific; single-word
    # subdivisions require explicit parent-country handling elsewhere.
    for subdivision in pycountry.subdivisions:
        if len(_normalized(subdivision.name).split()) >= 2:
            add(subdivision.name, subdivision.country_code)
    for alias, code in _MANUAL_ALIASES.items():
        add(alias, code, allow_short=True)
    return {alias: frozenset(codes) for alias, codes in aliases.items()}


def jurisdictions(text: str) -> set[str]:
    normalized = f" {_normalized(text)} "
    found: set[str] = set()
    for alias, codes in _aliases().items():
        if f" {alias} " in normalized:
            found.update(codes)
    return found


def _domain_jurisdictions(url: str) -> set[str]:
    host = (urlparse(url).hostname or "").casefold()
    return {
        code for suffix, code in _DOMAIN_SCOPES.items()
        if host == suffix or host.endswith(f".{suffix}")
    }


def _source_jurisdictions(document: DemoDocument) -> set[str]:
    domain_scopes = _domain_jurisdictions(document.url)
    if domain_scopes:
        return domain_scopes
    title_scopes = jurisdictions(document.title)
    return title_scopes or jurisdictions(document.text[:2000])


def _jurisdiction_is_claimed_value(text: str) -> bool:
    """Return true when geography is the fact to compare, not source scope."""
    normalized = _normalized(text)
    return bool(re.search(
        r"\b(?:located|situated|based|born)\s+in\b|"
        r"\b(?:permanent\s+)?member\s+of\b|"
        r"\bcapital\s+of\b",
        normalized,
    ))


def check_evidence_scope(
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[AssessmentAtomEvidence],
    documents: Sequence[DemoDocument],
) -> dict[str, list[EvidenceScopeCheck]]:
    evidence_by_atom = {item.atom_id: item for item in evidence}
    documents_by_id = {document.id: document for document in documents}
    output: dict[str, list[EvidenceScopeCheck]] = {}
    for atom in atoms:
        claim_scopes = jurisdictions(atom.text)
        jurisdiction_is_value = _jurisdiction_is_claimed_value(atom.text)
        checks: list[EvidenceScopeCheck] = []
        for span in evidence_by_atom[atom.id].spans:
            document = documents_by_id.get(span.document_id)
            if document is None:
                raise ValueError(f"Evidence span {span.id} references an unknown document")
            local_text = " ".join(
                [span.text, *(item.text for item in span.context_spans)]
            )
            local_scopes = jurisdictions(local_text)
            # A short passage can name several jurisdictions comparatively.
            # Large country sets usually come from organization/list names and
            # are not a reliable statement of the source's governing scope.
            evidence_scopes = (
                local_scopes if 0 < len(local_scopes) <= 4 else _source_jurisdictions(document)
            )
            if len(evidence_scopes) > 4:
                evidence_scopes = set()
            if jurisdiction_is_value:
                status = EvidenceScopeStatus.not_applicable
                reason = "Jurisdiction is the claimed value being compared, not a source-scope constraint."
            elif not claim_scopes:
                status = EvidenceScopeStatus.not_applicable
                reason = "The atomic claim does not state a recognized jurisdiction."
            elif not evidence_scopes:
                status = EvidenceScopeStatus.unresolved
                reason = "No explicit source jurisdiction could be resolved."
            elif claim_scopes & evidence_scopes:
                status = EvidenceScopeStatus.match
                reason = "The candidate and atomic claim share a recognized jurisdiction."
            else:
                status = EvidenceScopeStatus.mismatch
                reason = "The candidate concerns a different explicit jurisdiction."
            checks.append(EvidenceScopeCheck(
                span_id=span.id,
                document_id=span.document_id,
                status=status,
                claim_jurisdictions=sorted(claim_scopes),
                evidence_jurisdictions=sorted(evidence_scopes),
                reason=reason,
            ))
        output[atom.id] = checks
    return output


def mismatched_span_ids(checks: Iterable[EvidenceScopeCheck]) -> set[str]:
    return {
        check.span_id for check in checks
        if check.status == EvidenceScopeStatus.mismatch
    }
