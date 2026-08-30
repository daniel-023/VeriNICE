"""Deterministic, versioned four-way verdict aggregation."""

from .schemas import (
    AggregationWarning,
    ClaimComposition,
    ClaimEvidencePositions,
    GroundedClaimPosition,
    NLIRelation,
    ObligationEvidenceState,
    ObligationEvidenceSummary,
    ReferenceLabel,
    VerdictAggregationRequest,
    VerdictAggregationResult,
)


def _edge_id(kind: str, claim_id: str, atom_id: str, document_id: str, span_id: str) -> str:
    return f"edge:{kind}:evidence:{document_id}:{span_id}:obligation:{claim_id}:{atom_id}"


def aggregate_verdict(request: VerdictAggregationRequest) -> VerdictAggregationResult:
    """Map validated evidence positions; reference labels never enter this function."""
    atoms = request.atoms
    if request.composition == ClaimComposition.single and len(atoms) != 1:
        raise ValueError("SINGLE composition requires exactly one verification obligation")

    evidence_keys = {
        (item.atom_id, span.document_id, span.id)
        for item in request.evidence
        for span in item.spans
    }
    warnings: list[AggregationWarning] = []
    entailed_span_ids: set[str] = set()
    relations_by_atom = {item.atom_id: item.relations for item in request.classifications}
    summaries_by_atom = {item.atom_id: item for item in request.linguistic_summaries}
    obligation_summaries: list[ObligationEvidenceSummary] = []

    for atom in atoms:
        support_ids: list[str] = []
        attack_ids: list[str] = []
        neutral_count = 0
        seen: set[tuple[str, str, str]] = set()
        for relation in relations_by_atom[atom.id]:
            key = (relation.relation.value, relation.document_id, relation.span_id)
            if key in seen:
                warnings.append(AggregationWarning(
                    code="DUPLICATE_ARGUMENT_RELATION",
                    message=f"Duplicate NLI relation for obligation {atom.id} was deduplicated.",
                ))
                continue
            seen.add(key)
            if (atom.id, relation.document_id, relation.span_id) not in evidence_keys:
                raise ValueError(f"NLI relation references missing evidence for obligation {atom.id}")
            if relation.relation == NLIRelation.neutral:
                neutral_count += 1
            elif relation.relation == NLIRelation.entailment:
                entailed_span_ids.add(relation.span_id)
                support_ids.append(_edge_id("SUPPORTS", request.claim_id, atom.id, relation.document_id, relation.span_id))
            elif relation.relation == NLIRelation.contradiction:
                attack_ids.append(_edge_id("ATTACKS", request.claim_id, atom.id, relation.document_id, relation.span_id))

        state = (
            ObligationEvidenceState.conflicting if support_ids and attack_ids
            else ObligationEvidenceState.supported if support_ids
            else ObligationEvidenceState.refuted if attack_ids
            else ObligationEvidenceState.unresolved
        )
        if state == ObligationEvidenceState.unresolved:
            warnings.append(AggregationWarning(
                code="OBLIGATION_WITHOUT_ARGUMENT_EDGES",
                message=f"Obligation {atom.id} has no supporting or attacking evidence.",
            ))
            if neutral_count:
                warnings.append(AggregationWarning(
                    code="ONLY_NEUTRAL_CANDIDATES",
                    message=f"Obligation {atom.id} has only neutral retrieved candidates.",
                ))
        summary = summaries_by_atom.get(atom.id)
        if summary and (summary.analysis_status == "partial" or summary.warnings):
            warnings.append(AggregationWarning(
                code="PARTIAL_LINGUISTIC_ANALYSIS" if summary.analysis_status == "partial" else "LINGUISTIC_AUDIT_WARNING",
                message=f"Linguistic analysis for obligation {atom.id} requires inspection; it does not change the verdict.",
            ))
        obligation_summaries.append(ObligationEvidenceSummary(
            obligation_id=atom.id,
            state=state,
            support_edge_ids=support_ids,
            attack_edge_ids=attack_ids,
            neutral_candidate_count=neutral_count,
        ))

    supported = [item.obligation_id for item in obligation_summaries if item.support_edge_ids]
    attacked = [item.obligation_id for item in obligation_summaries if item.attack_edge_ids]
    unresolved = [item.obligation_id for item in obligation_summaries if item.state == ObligationEvidenceState.unresolved]
    composition = request.composition
    material_omission_position = False
    if request.material_omission is not None and request.material_omission.detected:
        all_span_ids = {span.id for item in request.evidence for span in item.spans}
        missing = (
            set(request.material_omission.support_span_ids)
            | set(request.material_omission.context_span_ids)
        ) - all_span_ids
        if missing:
            raise ValueError("Material-omission certificate references missing evidence spans")
        if not set(request.material_omission.support_span_ids).issubset(entailed_span_ids):
            raise ValueError("Material-omission support spans must be grounded support relations")
        material_omission_position = True
    grounded_position = None
    if request.claim_audit is not None:
        all_span_ids = {span.id for item in request.evidence for span in item.spans}
        referenced = (
            set(request.claim_audit.support_span_ids)
            | set(request.claim_audit.attack_span_ids)
            | set(request.claim_audit.context_span_ids)
        )
        if not referenced.issubset(all_span_ids):
            raise ValueError("Grounded claim audit references missing evidence spans")
        grounded_position = request.claim_audit.position
        support_position = grounded_position in {
            GroundedClaimPosition.support_only,
            GroundedClaimPosition.mixed_or_misleading,
        }
        attack_position = grounded_position in {
            GroundedClaimPosition.attack_only,
            GroundedClaimPosition.mixed_or_misleading,
        }
        rule = (
            "The provenance-constrained claim audit sets the overall evidence "
            "position; deterministic aggregation maps that position to status."
        )
    elif composition == ClaimComposition.and_:
        support_position, attack_position = len(supported) == len(atoms), bool(attacked)
        rule = "AND support requires support for every obligation; AND attack requires an attack on any obligation."
    elif composition == ClaimComposition.or_:
        support_position, attack_position = bool(supported), len(attacked) == len(atoms)
        rule = "OR support requires support for any obligation; OR attack requires attacks on every obligation."
    else:
        support_position, attack_position = bool(supported), bool(attacked)
        rule = "SINGLE uses its only obligation's support and attack positions."
    positions = ClaimEvidencePositions(
        support_position=support_position,
        attack_position=attack_position,
        material_omission_position=material_omission_position,
        support_obligation_ids=supported,
        attack_obligation_ids=attacked,
        unresolved_obligation_ids=unresolved,
        grounded_claim_position=grounded_position,
    )
    verdict = (
        ReferenceLabel.conflicting_evidence if material_omission_position or (support_position and attack_position)
        else ReferenceLabel.supported if support_position
        else ReferenceLabel.refuted if attack_position
        else ReferenceLabel.not_enough_evidence
    )
    trace = [rule]
    if request.claim_audit is not None:
        trace.append(
            f"Grounded claim position: {request.claim_audit.position.value}; "
            f"{request.claim_audit.reason}"
        )
    trace.append(f"Support position: {'yes' if support_position else 'no'}; attack position: {'yes' if attack_position else 'no'}.")
    if material_omission_position:
        trace.append(
            "Material-omission position: yes; selected support and correcting-context spans establish a cherrypicking conflict."
        )
    trace.append(f"Final verdict: {verdict.value}.")
    return VerdictAggregationResult(
        claim_id=request.claim_id,
        composition=composition,
        verdict=verdict,
        positions=positions,
        obligations=obligation_summaries,
        warnings=warnings,
        rule_trace=trace,
    )
