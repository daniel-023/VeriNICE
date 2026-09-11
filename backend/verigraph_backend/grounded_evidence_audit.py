"""Atom-scoped, provenance-constrained evidence assessment with Ollama."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Sequence

import httpx
from pydantic import ValidationError

from .evidence_scope import check_evidence_scope, mismatched_span_ids
from .schemas import (
    AssessmentAtomEvidence,
    DemoDocument,
    EvidenceScopeCheck,
    GroundedEvidenceAssessment,
    GroundedObligationAudit,
    MaterialOmissionCertificate,
    PipelineAtom,
)
from .settings import settings


AUDIT_INSTRUCTIONS = """Assess the supplied candidate evidence for each atomic
claim. Use only supplied evidence IDs and do not use outside knowledge. This is
an evidence assessment, not a case verdict.

For every atomic claim, select zero to three IDs in each field. atomTrueIds are
sentences that make the exact atomic claim true. atomFalseIds are sentences
that make the exact atomic claim false. contextIds provide context but establish
neither truth value. Assess the selected sentences jointly and mark the bundle SUFFICIENT,
PARTIAL, or INSUFFICIENT. Support requires the asserted entity, relationship,
time, quantity, comparison, and scope. Refutation requires a direct conflict;
mere irrelevance, missing evidence, or uncertainty is not refutation. Context
may help interpret evidence but does not itself support or refute the claim.

An authoritative sentence that explicitly calls the proposition false or a
myth is direct refutation; it does not need an opposing exact number. Likewise,
"does not change" directly refutes a claimed increase without a measurement,
and an explicit different location refutes a location claim. Each evidence ID
may appear in at most one of atomTrueIds, atomFalseIds, or contextIds. If the
rationale says a candidate directly supports or refutes the atom, include that
candidate in the corresponding list. Judge sufficiency from whether the bundle
resolves the atom, not from whether it contains a numeric measurement.

Relation examples: for atom "The bridge has cables," a source saying "the
bridge does not have cables" is REFUTES, never SUPPORTS. A source calling the
atom's proposition a "myth" or "false" is REFUTES; a heading that merely quotes
a myth is CONTEXT unless its truth status is explicit. For "A happened before
B," two dated sentences establishing B before A jointly REFUTE the atom. For a
superlative, values measured under different definitions are not opposing
evidence: mark the bundle PARTIAL or INSUFFICIENT and explain the ambiguity.

Each ANCHOR is selectable. READING CONTEXT may resolve a reference in that
anchor but is not an independent candidate. Never move evidence between atomic
claims. Some candidates may be absent because deterministic scope validation
excluded an explicit jurisdiction mismatch.

Keep missingInformation to one short sentence, and keep reason under 40 words.

Return materialOmission.detected only when sufficient selected support evidence
establishes a narrower fact and selected context establishes an omitted scope,
exception, cost, comparison period, or eligibility condition that materially
changes the claim. Otherwise return false and empty ID lists. Return JSON only."""

MAX_CONTEXT_CHARACTERS = 1600


class GroundedEvidenceAuditError(RuntimeError):
    pass


class GroundedEvidenceAuditConfigurationError(GroundedEvidenceAuditError):
    pass


class GroundedEvidenceAuditProviderError(GroundedEvidenceAuditError):
    pass


class GroundedEvidenceAuditOutputError(GroundedEvidenceAuditError):
    pass


def _compact(text: str, limit: int = MAX_CONTEXT_CHARACTERS) -> str:
    return " ".join(text.split())[:limit]


def _audit_schema(codes_by_atom: dict[str, list[str]]) -> dict[str, Any]:
    all_codes = [code for codes in codes_by_atom.values() for code in codes]
    all_evidence_items: dict[str, Any] = {"type": "string"}
    if all_codes:
        all_evidence_items["enum"] = all_codes
    obligation_schemas: dict[str, Any] = {}
    for atom_code, codes in codes_by_atom.items():
        local_items: dict[str, Any] = {"type": "string"}
        if codes:
            local_items["enum"] = codes
        selection = {"type": "array", "items": local_items, "maxItems": min(3, len(codes))}
        obligation_schemas[atom_code] = {
            "type": "object",
            "properties": {
                "atomTrueIds": selection,
                "atomFalseIds": selection,
                "contextIds": selection,
                "sufficiency": {"type": "string", "enum": ["SUFFICIENT", "PARTIAL", "INSUFFICIENT"]},
                "missingInformation": {"type": "string", "maxLength": 180},
                "reason": {"type": "string", "maxLength": 300},
            },
            "required": ["atomTrueIds", "atomFalseIds", "contextIds", "sufficiency", "missingInformation", "reason"],
        }
    return {
        "type": "object",
        "properties": {
            "obligations": {
                "type": "object",
                "properties": obligation_schemas,
                "required": list(codes_by_atom),
            },
            "materialOmission": {
                "type": "object",
                "properties": {
                    "detected": {"type": "boolean"},
                    "supportIds": {"type": "array", "items": all_evidence_items, "maxItems": 3},
                    "contextIds": {"type": "array", "items": all_evidence_items, "maxItems": 3},
                    "reason": {"type": "string", "maxLength": 300},
                },
                "required": ["detected", "supportIds", "contextIds", "reason"],
            },
        },
        "required": ["obligations", "materialOmission"],
    }


def _audit_input(
    claim: str,
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[AssessmentAtomEvidence],
    documents: Sequence[DemoDocument],
    scope_checks: dict[str, list[EvidenceScopeCheck]],
) -> tuple[str, Dict[str, tuple[PipelineAtom, Dict[str, Any]]], dict[str, Any]]:
    evidence_by_atom = {item.atom_id: item for item in evidence}
    documents_by_id = {item.id: item for item in documents}
    mapped: Dict[str, tuple[PipelineAtom, Dict[str, Any]]] = {}
    lines = [f"CLAIM: {claim}"]
    for atom_index, atom in enumerate(atoms, start=1):
        atom_code = f"O{atom_index}"
        lines.append(f"\nATOMIC CLAIM {atom_code}: {atom.text}")
        excluded = mismatched_span_ids(scope_checks[atom.id])
        candidates: Dict[str, Any] = {}
        eligible_index = 0
        for span in evidence_by_atom[atom.id].spans:
            if span.id in excluded:
                continue
            eligible_index += 1
            code = f"{atom_code}-E{eligible_index}"
            candidates[code] = span
            document = documents_by_id[span.document_id]
            lines.append(f"{code} | {_compact(document.title, 180)} | ANCHOR: {_compact(span.text)}")
            if span.context_spans:
                context = " ".join(f"[{item.direction}] {_compact(item.text)}" for item in span.context_spans)
                lines.append(f"  READING CONTEXT (not independent evidence): {context}")
            elif span.context and span.context.strip() != span.text.strip():
                lines.append(f"  READING CONTEXT (not independent evidence): {_compact(span.context)}")
        mapped[atom_code] = (atom, candidates)
    return "\n".join(lines), mapped, _audit_schema({
        atom_code: list(candidates) for atom_code, (_atom, candidates) in mapped.items()
    })


def _response_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise GroundedEvidenceAuditOutputError("Ollama returned an invalid response envelope.")
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise GroundedEvidenceAuditOutputError("Ollama returned no evidence assessment JSON.")
    if not payload.get("done", True):
        raise GroundedEvidenceAuditProviderError("Ollama stopped before completing the evidence assessment.")
    return message["content"]


async def _request_audit(prompt: str, schema: dict[str, Any]) -> Any:
    payload = {
        "model": settings.ollama_model, "stream": False,
        "messages": [{"role": "system", "content": AUDIT_INSTRUCTIONS}, {"role": "user", "content": prompt}],
        "think": False, "format": schema,
        "options": {"temperature": 0, "seed": 0, "num_ctx": settings.evidence_audit_context_size, "num_predict": 1400},
        "keep_alive": settings.ollama_keep_alive,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as error:
        raise GroundedEvidenceAuditProviderError("The Ollama evidence assessment timed out. Check that Ollama is running and retry.") from error
    except httpx.HTTPStatusError as error:
        raise GroundedEvidenceAuditProviderError("Ollama rejected the evidence assessment request.") from error
    except (httpx.HTTPError, ValueError) as error:
        raise GroundedEvidenceAuditProviderError("Ollama could not complete the evidence assessment.") from error


def _unique_valid_codes(raw: Any, candidates: Dict[str, Any]) -> list[str]:
    if not isinstance(raw, list):
        return []
    codes = list(dict.fromkeys(str(code) for code in raw))[:3]
    unknown = [code for code in codes if code not in candidates]
    if unknown:
        raise GroundedEvidenceAuditOutputError(
            "The model selected unavailable evidence IDs: " + ", ".join(unknown)
        )
    return codes


_EMPTY_MODEL_VALUES = {"", "false", "null", "none", "n/a", "not applicable", "no"}


def _clean_model_sentence(value: Any, *, fallback: str = "", limit: int = 300) -> str:
    """Normalize short display copy without exposing JSON-ish model values."""
    if value is None or isinstance(value, bool):
        return fallback
    text = " ".join(str(value).split()).strip()
    if text.casefold() in _EMPTY_MODEL_VALUES:
        return fallback
    complete = re.match(r"^(.+?[.!?])(?:\s|$)", text)
    if complete:
        return complete.group(1)[:limit]
    if len(text) <= limit:
        return text if text.endswith((".", "!", "?")) else f"{text}."
    # A long fragment has no safe sentence boundary. Do not publish a clipped
    # half-sentence as an explanation.
    return fallback or "Additional source information is needed."


def _parse_audit(
    payload: Any,
    mapped: Dict[str, tuple[PipelineAtom, Dict[str, Any]]],
    scope_checks: dict[str, list[EvidenceScopeCheck]],
) -> GroundedEvidenceAssessment:
    try:
        raw = json.loads(_response_content(payload))
    except (ValueError, json.JSONDecodeError) as error:
        raise GroundedEvidenceAuditOutputError("The model returned malformed assessment JSON.") from error
    items = raw.get("obligations") if isinstance(raw, dict) else None
    if isinstance(items, dict):
        items = [dict(value, obligationId=atom_code) for atom_code, value in items.items() if isinstance(value, dict)]
    if not isinstance(items, list) or len(items) != len(mapped):
        raise GroundedEvidenceAuditOutputError("The model returned incomplete atomic-claim assessments.")
    selections: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise GroundedEvidenceAuditOutputError("The model returned an invalid atomic-claim assessment.")
        atom_code = str(item.get("obligationId", ""))
        if atom_code not in mapped or atom_code in selections:
            raise GroundedEvidenceAuditOutputError("The model returned duplicate or unknown atomic-claim assessments.")
        candidates = mapped[atom_code][1]
        sufficiency = str(item.get("sufficiency", ""))
        if sufficiency not in {"SUFFICIENT", "PARTIAL", "INSUFFICIENT"}:
            raise GroundedEvidenceAuditOutputError("The model returned an unknown evidence sufficiency value.")
        selections[atom_code] = {
            "support": _unique_valid_codes(item.get("atomTrueIds"), candidates),
            "refute": _unique_valid_codes(item.get("atomFalseIds"), candidates),
            "context": _unique_valid_codes(item.get("contextIds"), candidates),
            "sufficiency": sufficiency,
            "missing": _clean_model_sentence(item.get("missingInformation"), limit=220),
            "reason": _clean_model_sentence(
                item.get("reason"), fallback="No rationale was returned.", limit=300
            ),
        }
        support = selections[atom_code]["support"]
        refute = selections[atom_code]["refute"]
        context = selections[atom_code]["context"]
        contradictory = set(support) & set(refute)
        # Two sources may reproduce the same sentence under different IDs. The
        # same normalized statement cannot coherently support and refute one
        # atom, so demote both copies to reading context.
        support_by_text = {
            " ".join(candidates[code].text.casefold().split()): code for code in support
        }
        refute_by_text = {
            " ".join(candidates[code].text.casefold().split()): code for code in refute
        }
        duplicated_conflicts = support_by_text.keys() & refute_by_text.keys()
        for text in duplicated_conflicts:
            contradictory.update({support_by_text[text], refute_by_text[text]})
        if contradictory:
            # A single sentence cannot be both decisive support and decisive
            # refutation for one atom. Preserve it conservatively as context
            # instead of turning an invalid model assignment into a verdict.
            support = [code for code in support if code not in contradictory]
            refute = [code for code in refute if code not in contradictory]
            context = list(dict.fromkeys([*context, *sorted(contradictory)]))[:3]
        # A one-sided sentence cannot establish a relation between two named
        # jurisdictions. The model may correctly extract each date yet assign
        # the Sweden-only sentence as support for "Sweden before Finland".
        # Require each decisive bundle for an explicit before/after comparison
        # to cover every compared jurisdiction; incomplete bundles remain
        # available as context and to the grounded symbolic stage.
        atom, _ = mapped[atom_code]
        if re.search(r"\b(?:before|after)\b", atom.text, re.IGNORECASE):
            checks_by_span = {
                check.span_id: check for check in scope_checks[atom.id]
            }
            claim_jurisdictions = {
                jurisdiction
                for check in checks_by_span.values()
                for jurisdiction in check.claim_jurisdictions
            }
            if len(claim_jurisdictions) >= 2:
                for relation_codes in (support, refute):
                    covered = {
                        jurisdiction
                        for code in relation_codes
                        for jurisdiction in checks_by_span[candidates[code].id].evidence_jurisdictions
                    }
                    if not claim_jurisdictions.issubset(covered):
                        context = list(dict.fromkeys([*context, *relation_codes]))[:3]
                        relation_codes.clear()
        decisive = set(support) | set(refute)
        selections[atom_code]["support"] = support
        selections[atom_code]["refute"] = refute
        selections[atom_code]["context"] = [code for code in context if code not in decisive]

    obligations: list[GroundedObligationAudit] = []
    all_candidates: dict[str, Any] = {}
    for atom_code, (atom, candidates) in mapped.items():
        selection = selections[atom_code]
        all_candidates.update(candidates)
        obligations.append(GroundedObligationAudit(
            atom_id=atom.id,
            support_span_ids=[candidates[code].id for code in selection["support"]],
            refute_span_ids=[candidates[code].id for code in selection["refute"]],
            context_span_ids=[candidates[code].id for code in selection["context"]],
            sufficiency=selection["sufficiency"],
            missing_information=selection["missing"],
            reason=selection["reason"],
            scope_checks=scope_checks[atom.id],
        ))

    omission_raw = raw.get("materialOmission")
    if not isinstance(omission_raw, dict):
        raise GroundedEvidenceAuditOutputError("The model omitted the material-omission certificate.")
    detected = bool(omission_raw.get("detected"))
    support_codes = _unique_valid_codes(omission_raw.get("supportIds"), all_candidates)
    context_codes = _unique_valid_codes(omission_raw.get("contextIds"), all_candidates)
    if detected:
        sufficient_codes = {
            code for atom_code, selection in selections.items()
            if selection["sufficiency"] == "SUFFICIENT" for code in selection["support"]
        }
        if not set(support_codes).issubset(sufficient_codes):
            raise GroundedEvidenceAuditOutputError("A material omission must cite sufficient supporting evidence.")
    else:
        support_codes, context_codes = [], []
    try:
        omission = MaterialOmissionCertificate(
            detected=detected,
            support_span_ids=[all_candidates[code].id for code in support_codes],
            context_span_ids=[all_candidates[code].id for code in context_codes],
            reason=_clean_model_sentence(
                omission_raw.get("reason"),
                fallback="No material omission was established.",
                limit=300,
            ),
        )
    except ValidationError as error:
        raise GroundedEvidenceAuditOutputError("The model returned an invalid material-omission certificate.") from error
    return GroundedEvidenceAssessment(obligations=obligations, material_omission=omission)


async def audit_grounded_evidence(
    claim: str,
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[AssessmentAtomEvidence],
    documents: Sequence[DemoDocument],
) -> GroundedEvidenceAssessment:
    if not settings.ollama_url.strip() or not settings.ollama_model.strip():
        raise GroundedEvidenceAuditConfigurationError("Evidence assessment requires a configured local Ollama model.")
    scope_checks = check_evidence_scope(atoms, evidence, documents)
    prompt, mapped, schema = _audit_input(claim, atoms, evidence, documents, scope_checks)
    return _parse_audit(await _request_audit(prompt, schema), mapped, scope_checks)
