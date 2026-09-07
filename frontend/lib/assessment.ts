import type {
  AtomEvidence,
  AtomEvidenceAssessment,
  CandidateRelation,
  GroundedEvidenceAssessment,
  GroundedObligationAudit,
} from "./types";

export function candidateAssessments(
  evidence: AtomEvidence[],
  assessment: GroundedEvidenceAssessment | null,
): AtomEvidenceAssessment[] {
  const byAtom = new Map(assessment?.obligations.map((item) => [item.atomId, item]) ?? []);
  return evidence.map((group) => {
    const item = byAtom.get(group.atomId);
    const support = new Set(item?.supportSpanIds ?? []);
    const refute = new Set(item?.refuteSpanIds ?? []);
    const context = new Set(item?.contextSpanIds ?? []);
    const scopeBySpan = new Map(item?.scopeChecks?.map((check) => [check.spanId, check]) ?? []);
    const sufficient = item?.sufficiency === "SUFFICIENT";
    return {
      atomId: group.atomId,
      relations: group.spans.map((span) => {
        const scopeCheck = scopeBySpan.get(span.id);
        const relation = support.has(span.id)
          ? "SUPPORTS"
          : refute.has(span.id)
            ? "REFUTES"
            : context.has(span.id)
              ? "CONTEXT"
              : "NOT_SELECTED" as CandidateRelation;
        return {
        spanId: span.id,
        documentId: span.documentId,
        relation,
        decisive: sufficient && (relation === "SUPPORTS" || relation === "REFUTES"),
        scopeCheck,
      }}),
    };
  });
}

export function reviseAssessment(
  assessment: GroundedEvidenceAssessment,
  atomId: string,
  spanId: string,
  relation: CandidateRelation,
): GroundedEvidenceAssessment {
  const obligations = assessment.obligations.map((item) => {
    if (item.atomId !== atomId) return item;
    const scope = item.scopeChecks.find((check) => check.spanId === spanId);
    if (scope?.status === "MISMATCH" && (relation === "SUPPORTS" || relation === "REFUTES")) {
      return item;
    }
    const without = (values: string[] | undefined) => (values ?? []).filter((id) => id !== spanId);
    const supportSpanIds = relation === "SUPPORTS" ? [...without(item.supportSpanIds), spanId] : without(item.supportSpanIds);
    const refuteSpanIds = relation === "REFUTES" ? [...without(item.refuteSpanIds), spanId] : without(item.refuteSpanIds);
    const contextSpanIds = relation === "CONTEXT" ? [...without(item.contextSpanIds), spanId] : without(item.contextSpanIds);
    return {
      ...item,
      supportSpanIds,
      refuteSpanIds,
      contextSpanIds,
      reason: "Reviewer-adjusted evidence relation.",
    };
  });
  const activeSupport = new Set(obligations.flatMap((item) => item.supportSpanIds));
  const activeContext = new Set(obligations.flatMap((item) => item.contextSpanIds ?? []));
  const omissionStillGrounded = assessment.materialOmission.detected
    && assessment.materialOmission.supportSpanIds.every((id) => activeSupport.has(id))
    && assessment.materialOmission.contextSpanIds.every((id) => activeContext.has(id));
  return {
    ...assessment,
    obligations,
    materialOmission: omissionStillGrounded
      ? assessment.materialOmission
      : {
          detected: false,
          supportSpanIds: [],
          contextSpanIds: [],
          reason: "Reviewer changes invalidated the recorded material-omission certificate.",
        },
  };
}
