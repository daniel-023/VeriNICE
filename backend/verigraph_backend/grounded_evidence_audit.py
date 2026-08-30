"""Provenance-constrained claim-position auditing with Ollama.

The model chooses an evidence position and supplied span IDs. It never emits a
published four-way verdict; deterministic aggregation maps the validated
position to the rule-derived demo status.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Sequence

import httpx
from pydantic import ValidationError

from .schemas import (
    AtomSupportClassification,
    EvidenceRelation,
    GroundedClaimAudit,
    GroundedClaimPosition,
    GroundedEvidenceAuditResult,
    GroundedObligationAudit,
    MaterialOmissionCertificate,
    NLIAtomEvidence,
    NLIRelation,
    PipelineAtom,
    SupportClassificationResponse,
)
from .settings import settings


AUDIT_INSTRUCTIONS = """You audit the overall position established by
supplied evidence for a fact-checking claim. Use only supplied evidence IDs. Do
not use outside knowledge. The output is an evidence position, not a published
verdict.

Choose exactly one position:
- SUPPORT_ONLY: the cited evidence establishes every material part of the full
  claim and there is no material counterevidence.
- ATTACK_ONLY: the cited evidence directly falsifies any required part of the
  claim. A counterexample attacks an absolute or universal claim. Other true,
  undisputed background or obligations do not turn a refuted conjunction into
  mixed evidence.
- MIXED_OR_MISLEADING: credible evidence supports and attacks the same disputed
  required proposition, or the literal facts are selectively true while an
  omitted scope, cost, exception, comparison period, eligibility condition,
  jurisdiction, or conflated program materially reverses the overall
  impression. Do not choose mixed merely because one conjunct is true and a
  different required conjunct is false; choose ATTACK_ONLY.
- INSUFFICIENT: the supplied evidence cannot establish or falsify the full
  claim. Topical discussion, possibility, a preliminary study, or a missing
  comparison is insufficient.

Calibration rules:
- Support requires the exact entities, relationship, comparison, time,
  quantity, and scope asserted. If a claim compares X with Y and evidence lacks
  facts about Y, choose INSUFFICIENT; general theory about X cannot fill the
  missing side.
- A preliminary study, possible use, ongoing review, unpredictable result, or
  call for more research does not support an unqualified claim of established
  status. Apparent preliminary support plus uncertainty is still INSUFFICIENT,
  not mixed. Uncertainty alone is not an attack.
- Evidence that identifies a different actor or entity, gives a counterexample
  to a universal, denies an asserted inclusion, or states that an authoritative
  plan contains no asserted provision is an attack, not merely insufficient.
- Judge the literal proposition. Do not add an unstated qualifier such as
  "natural," "legal," or "intentional" and then attack that stronger claim.
- An explanation for an observed event does not attack the observation. For
  example, scattering can explain a red-looking sky without contradicting that
  the sky was described as red.
- Choose MIXED_OR_MISLEADING when evidence establishes a narrower underlying
  policy, event, or concern but the claim turns it into a materially stronger
  accusation by omitting scope or qualifications. Its support IDs may establish
  that narrower basis rather than the exaggerated full claim.

Select at most six IDs in each list. Every selected ID must be supplied.
SUPPORT_ONLY requires support IDs. ATTACK_ONLY requires attack IDs.
MIXED_OR_MISLEADING requires support IDs and attack or context IDs.
INSUFFICIENT has no support or attack IDs. Keep the reason concrete and under
55 words. Return JSON only."""

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


def _audit_schema(all_codes: list[str]) -> dict[str, Any]:
    evidence_items: dict[str, Any] = {"type": "string"}
    if all_codes:
        evidence_items["enum"] = all_codes
    return {
        "type": "object",
        "properties": {
            "position": {
                "type": "string",
                "enum": [
                    "SUPPORT_ONLY",
                    "ATTACK_ONLY",
                    "MIXED_OR_MISLEADING",
                    "INSUFFICIENT",
                ],
            },
            "supportIds": {"type": "array", "items": evidence_items, "maxItems": 6},
            "attackIds": {"type": "array", "items": evidence_items, "maxItems": 6},
            "contextIds": {"type": "array", "items": evidence_items, "maxItems": 6},
            "reason": {"type": "string"},
        },
        "required": ["position", "supportIds", "attackIds", "contextIds", "reason"],
    }


def _audit_input(
    claim: str,
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[NLIAtomEvidence],
    document_titles: Dict[str, str],
) -> tuple[str, Dict[str, tuple[PipelineAtom, Dict[str, Any]]], dict[str, Any]]:
    evidence_by_atom = {item.atom_id: item for item in evidence}
    mapped: Dict[str, tuple[PipelineAtom, Dict[str, Any]]] = {}
    lines = [f"CLAIM: {claim}"]
    all_codes: list[str] = []
    for atom_index, atom in enumerate(atoms, start=1):
        atom_code = f"O{atom_index}"
        lines.append(f"\nOBLIGATION {atom_code}: {atom.text}")
        candidates: Dict[str, Any] = {}
        for evidence_index, span in enumerate(evidence_by_atom[atom.id].spans, start=1):
            code = f"{atom_code}-E{evidence_index}"
            candidates[code] = span
            all_codes.append(code)
            title = _compact(document_titles.get(span.document_id, "Untitled source"), 180)
            lines.append(f"{code} | {title} | {_compact(span.context or span.text)}")
        mapped[atom_code] = (atom, candidates)
    return "\n".join(lines), mapped, _audit_schema(all_codes)


def _response_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise GroundedEvidenceAuditOutputError("Ollama returned an invalid response envelope.")
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise GroundedEvidenceAuditOutputError("Ollama returned no grounded audit JSON.")
    if not payload.get("done", True):
        raise GroundedEvidenceAuditProviderError("Ollama stopped before completing the evidence audit.")
    return message["content"]


async def _request_audit(prompt: str, schema: dict[str, Any]) -> Any:
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": AUDIT_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        # Disable optional reasoning-channel generation. The typed evidence
        # audit needs only the schema-constrained answer, and Qwen3 otherwise
        # spends the entire local request budget on hidden thinking tokens.
        "think": False,
        "format": schema,
        "options": {
            "temperature": 0,
            "seed": 0,
            "num_ctx": settings.evidence_audit_context_size,
            "num_predict": 600,
        },
        "keep_alive": settings.ollama_keep_alive,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{settings.ollama_url.rstrip('/')}/api/chat", json=payload
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as error:
        raise GroundedEvidenceAuditProviderError(
            "The Ollama evidence audit timed out. Check that Ollama is running and retry."
        ) from error
    except httpx.HTTPStatusError as error:
        raise GroundedEvidenceAuditProviderError(
            "Ollama rejected the grounded evidence audit request."
        ) from error
    except (httpx.HTTPError, ValueError) as error:
        raise GroundedEvidenceAuditProviderError(
            "Ollama could not complete the grounded evidence audit."
        ) from error


def _unique_valid_codes(raw: Any, candidates: Dict[str, Any]) -> list[str]:
    if not isinstance(raw, list):
        return []
    codes = list(dict.fromkeys(str(code) for code in raw))[:6]
    if any(code not in candidates for code in codes):
        raise GroundedEvidenceAuditOutputError("The model selected an unknown evidence ID.")
    return codes


def _parse_audit(
    payload: Any,
    mapped: Dict[str, tuple[PipelineAtom, Dict[str, Any]]],
) -> GroundedEvidenceAuditResult:
    try:
        raw = json.loads(_response_content(payload))
    except (ValueError, json.JSONDecodeError) as error:
        raise GroundedEvidenceAuditOutputError("The model returned malformed audit JSON.") from error
    if not isinstance(raw, dict):
        raise GroundedEvidenceAuditOutputError("The model omitted the grounded claim position.")

    all_candidates = {
        code: span
        for _atom, candidates in mapped.values()
        for code, span in candidates.items()
    }
    try:
        position = GroundedClaimPosition(str(raw.get("position", "")))
    except ValueError as error:
        raise GroundedEvidenceAuditOutputError("The model returned an unknown claim position.") from error
    support_codes = _unique_valid_codes(raw.get("supportIds"), all_candidates)
    attack_codes = _unique_valid_codes(raw.get("attackIds"), all_candidates)
    context_codes = _unique_valid_codes(raw.get("contextIds"), all_candidates)
    if position == GroundedClaimPosition.support_only:
        selected_support_span_ids = {
            all_candidates[code].id for code in support_codes
        }
        support_atoms = {
            atom_code
            for atom_code, (_atom, candidates) in mapped.items()
            if any(
                span.id in selected_support_span_ids
                for span in candidates.values()
            )
        }
        if support_atoms != set(mapped):
            position = GroundedClaimPosition.insufficient
            reason_prefix = (
                "The claimed support-only position did not cite support for every obligation. "
            )
        else:
            reason_prefix = ""
    else:
        reason_prefix = ""
    if position == GroundedClaimPosition.support_only:
        attack_codes = []
    elif position == GroundedClaimPosition.attack_only:
        support_codes = []
    elif position == GroundedClaimPosition.insufficient:
        support_codes, attack_codes = [], []
    reason = reason_prefix + (
        str(raw.get("reason", "")).strip()
        or "The model did not provide a concrete audit reason."
    )

    try:
        claim_position = GroundedClaimAudit(
            position=position,
            support_span_ids=[all_candidates[code].id for code in support_codes],
            attack_span_ids=[all_candidates[code].id for code in attack_codes],
            context_span_ids=[all_candidates[code].id for code in context_codes],
            reason=reason[:500],
        )
    except ValidationError as error:
        raise GroundedEvidenceAuditOutputError(
            "The model returned an ungrounded decisive claim position."
        ) from error

    obligations: list[GroundedObligationAudit] = []
    selected_support_span_ids = {
        all_candidates[code].id for code in support_codes
    }
    selected_attack_span_ids = {
        all_candidates[code].id for code in attack_codes
    }
    for _atom_code, (atom, candidates) in mapped.items():
        atom_support = list(
            dict.fromkeys(
                span.id
                for span in candidates.values()
                if span.id in selected_support_span_ids
            )
        )[:3]
        atom_attack = list(
            dict.fromkeys(
                span.id
                for span in candidates.values()
                if span.id in selected_attack_span_ids
            )
        )[:3]
        state = (
            "BOTH" if atom_support and atom_attack
            else "SUPPORTED" if atom_support
            else "REFUTED" if atom_attack
            else "UNRESOLVED"
        )
        obligations.append(
            GroundedObligationAudit(
                atom_id=atom.id,
                state=state,
                support_span_ids=atom_support,
                attack_span_ids=atom_attack,
                reason=reason[:500],
            )
        )

    return GroundedEvidenceAuditResult(
        claim_position=claim_position,
        obligations=obligations,
        material_omission=MaterialOmissionCertificate(),
        model=settings.ollama_model,
    )


async def audit_grounded_evidence(
    claim: str,
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[NLIAtomEvidence],
    document_titles: Dict[str, str],
) -> GroundedEvidenceAuditResult:
    if not settings.ollama_url.strip() or not settings.ollama_model.strip():
        raise GroundedEvidenceAuditConfigurationError(
            "Grounded evidence auditing requires a configured local Ollama model."
        )
    prompt, mapped, schema = _audit_input(claim, atoms, evidence, document_titles)
    return _parse_audit(await _request_audit(prompt, schema), mapped)


def classifications_from_grounded_audit(
    evidence: Sequence[NLIAtomEvidence],
    audit: GroundedEvidenceAuditResult,
) -> SupportClassificationResponse:
    """Turn validated claim-level evidence selections into graph relations."""
    support_ids = set(audit.claim_position.support_span_ids)
    attack_ids = set(audit.claim_position.attack_span_ids)
    classifications = []
    for group in evidence:
        relations = []
        for span in group.spans:
            relation = (
                NLIRelation.entailment if span.id in support_ids
                else NLIRelation.contradiction if span.id in attack_ids
                else NLIRelation.neutral
            )
            relations.append(
                EvidenceRelation(
                    span_id=span.id,
                    document_id=span.document_id,
                    relation=relation,
                )
            )
        classifications.append(
            AtomSupportClassification(atom_id=group.atom_id, relations=relations)
        )
    return SupportClassificationResponse(
        classifications=classifications,
        evidence_audit=audit,
        provider="ollama",
        model=audit.model,
    )
