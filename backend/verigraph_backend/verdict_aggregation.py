"""Composition-first aggregation of grounded neural and symbolic relations."""

from .schemas import (
    AggregationWarning, ClaimComposition, ClaimEvidencePositions,
    ObligationEvidenceState, ObligationEvidenceSummary, ReferenceLabel,
    SymbolicStatus, VerdictAggregationRequest, VerdictAggregationResult,
)


def _evidence_edge(kind: str, claim_id: str, atom_id: str, document_id: str, span_id: str) -> str:
    return f"edge:{kind}:evidence:{document_id}:{span_id}:obligation:{claim_id}:{atom_id}"


def _proof_edge(kind: str, claim_id: str, atom_id: str, execution_id: str) -> str:
    return f"edge:{kind}:inference:{execution_id}:obligation:{claim_id}:{atom_id}"


def _assessed_edges(
    kind: str, claim_id: str, atom_id: str, span_ids: list[str], span_by_id: dict
) -> list[str]:
    if len(span_ids) >= 2:
        inference_id = f"inference:bundle:{atom_id}:{kind.lower()}"
        return [f"edge:{kind}:{inference_id}:obligation:{claim_id}:{atom_id}"]
    return [
        _evidence_edge(kind, claim_id, atom_id, span_by_id[item].document_id, item)
        for item in span_ids
    ]


def aggregate_verdict(request: VerdictAggregationRequest) -> VerdictAggregationResult:
    """Aggregate validated relations without consulting the reference label."""
    atoms = request.atoms
    if request.composition == ClaimComposition.single and len(atoms) != 1:
        raise ValueError("SINGLE composition requires exactly one verification obligation")
    evidence_by_atom = {item.atom_id: item for item in request.evidence}
    audits_by_atom = {item.atom_id: item for item in request.assessment.obligations}
    proofs_by_atom: dict[str, list] = {atom.id: [] for atom in atoms}
    for proof in request.reasoning:
        proofs_by_atom[proof.atom_id].append(proof)

    warnings: list[AggregationWarning] = []
    obligations: list[ObligationEvidenceSummary] = []
    accepted_support_ids: set[str] = set()
    all_span_ids = {span.id for group in request.evidence for span in group.spans}
    for atom in atoms:
        group = evidence_by_atom[atom.id]
        audit = audits_by_atom[atom.id]
        span_by_id = {span.id: span for span in group.spans}
        provisional_support_ids = list(dict.fromkeys(audit.support_span_ids))
        provisional_refute_ids = list(dict.fromkeys(audit.refute_span_ids))
        if not set(provisional_support_ids + provisional_refute_ids + audit.context_span_ids).issubset(span_by_id):
            raise ValueError(f"Assessment references missing evidence for obligation {atom.id}")
        decisive = audit.sufficiency == "SUFFICIENT"
        support_ids = provisional_support_ids if decisive else []
        refute_ids = provisional_refute_ids if decisive else []
        accepted_support_ids.update(support_ids)
        support_edges = _assessed_edges("SUPPORTS", request.claim_id, atom.id, support_ids, span_by_id)
        refute_edges = _assessed_edges("REFUTES", request.claim_id, atom.id, refute_ids, span_by_id)
        for proof in proofs_by_atom[atom.id]:
            if proof.status not in {SymbolicStatus.proved, SymbolicStatus.disproved}:
                continue
            if proof.relation == "SUPPORTS":
                support_edges.append(_proof_edge("SUPPORTS", request.claim_id, atom.id, proof.id))
            elif proof.relation == "REFUTES":
                refute_edges.append(_proof_edge("REFUTES", request.claim_id, atom.id, proof.id))
        state = (
            ObligationEvidenceState.conflicting if support_edges and refute_edges
            else ObligationEvidenceState.supported if support_edges
            else ObligationEvidenceState.refuted if refute_edges
            else ObligationEvidenceState.unresolved
        )
        if state == ObligationEvidenceState.unresolved:
            warnings.append(AggregationWarning(code="OBLIGATION_WITHOUT_ARGUMENT_EDGES", message=f"Obligation {atom.id} has no validated supporting or refuting relation."))
        provisional_count = len(set(provisional_support_ids + provisional_refute_ids)) if not decisive else 0
        if provisional_count:
            warnings.append(AggregationWarning(
                code="PROVISIONAL_EVIDENCE_EXCLUDED",
                message=f"{provisional_count} assessed relation(s) for obligation {atom.id} are provisional because the evidence is not sufficient.",
            ))
        obligations.append(ObligationEvidenceSummary(
            obligation_id=atom.id, state=state,
            support_edge_ids=support_edges, refute_edge_ids=refute_edges,
            unselected_candidate_count=max(0, len(group.spans) - len(set(provisional_support_ids + provisional_refute_ids + audit.context_span_ids))),
            provisional_relation_count=provisional_count,
        ))

    supported_only = [item.obligation_id for item in obligations if item.state == ObligationEvidenceState.supported]
    refuted_only = [item.obligation_id for item in obligations if item.state == ObligationEvidenceState.refuted]
    conflicting = [item.obligation_id for item in obligations if item.state == ObligationEvidenceState.conflicting]
    unresolved = [item.obligation_id for item in obligations if item.state == ObligationEvidenceState.unresolved]
    omission = request.assessment.material_omission
    if omission.detected:
        referenced = set(omission.support_span_ids + omission.context_span_ids)
        if not referenced.issubset(all_span_ids):
            raise ValueError("Material-omission certificate references missing evidence spans")
        if not set(omission.support_span_ids).issubset(accepted_support_ids):
            raise ValueError("Material-omission support spans must be grounded support relations")

    if request.composition == ClaimComposition.and_:
        if refuted_only:
            support_position, refute_position, rule = False, True, "AND is refuted when any obligation is refuted-only."
        elif conflicting:
            support_position, refute_position, rule = True, True, "AND is conflicting when no obligation is refuted-only and an obligation has both relations."
        elif len(supported_only) == len(atoms):
            support_position, refute_position, rule = True, False, "AND is supported only when every obligation is support-only."
        else:
            support_position, refute_position, rule = False, False, "AND is insufficient while any obligation remains unresolved."
    elif request.composition == ClaimComposition.or_:
        if supported_only:
            support_position, refute_position, rule = True, False, "OR is supported when any obligation is support-only."
        elif conflicting:
            support_position, refute_position, rule = True, True, "OR is conflicting when none is support-only and an obligation has both relations."
        elif len(refuted_only) == len(atoms):
            support_position, refute_position, rule = False, True, "OR is refuted only when every obligation is refuted-only."
        else:
            support_position, refute_position, rule = False, False, "OR is insufficient while no disjunct is support-only and some remain unresolved."
    else:
        state = obligations[0].state
        support_position = state in {ObligationEvidenceState.supported, ObligationEvidenceState.conflicting}
        refute_position = state in {ObligationEvidenceState.refuted, ObligationEvidenceState.conflicting}
        rule = "SINGLE maps its one obligation's validated relations directly."

    verdict = (
        ReferenceLabel.conflicting_evidence if omission.detected or (support_position and refute_position)
        else ReferenceLabel.supported if support_position
        else ReferenceLabel.refuted if refute_position
        else ReferenceLabel.not_enough_evidence
    )
    positions = ClaimEvidencePositions(
        support_position=support_position, refute_position=refute_position,
        material_omission_position=omission.detected,
        support_obligation_ids=[item.obligation_id for item in obligations if item.support_edge_ids],
        refute_obligation_ids=[item.obligation_id for item in obligations if item.refute_edge_ids],
        unresolved_obligation_ids=unresolved,
    )
    trace = [
        rule,
        f"Validated positions — support: {'yes' if support_position else 'no'}; refute: {'yes' if refute_position else 'no'}.",
    ]
    if omission.detected:
        trace.append("A separately grounded material-omission certificate establishes a misleading conflict.")
    trace.append(f"Verdict: {verdict.value}.")
    return VerdictAggregationResult(
        claim_id=request.claim_id, composition=request.composition, verdict=verdict,
        positions=positions, obligations=obligations, warnings=warnings, rule_trace=trace,
    )
