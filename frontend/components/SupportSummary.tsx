import type {
  AtomSupportClassification,
  GroundedObligationAudit,
  GroundedClaimAudit,
  MaterialOmissionCertificate,
  NLIRelation,
  StageState,
} from "@/lib/types";

const RELATION_LABELS: Record<NLIRelation, string> = {
  ENTAILMENT: "support",
  CONTRADICTION: "contradict",
  NEUTRAL: "neither",
};

function stateLabel(state: StageState): string {
  if (state === "running") return "Classifying";
  if (state === "complete") return "Ready";
  if (state === "error") return "Unavailable";
  return "Waiting";
}

export function SupportSummary({
  classification,
  audit,
  materialOmission,
  claimAudit,
  state,
}: {
  classification: AtomSupportClassification | null;
  audit?: GroundedObligationAudit | null;
  materialOmission?: MaterialOmissionCertificate | null;
  claimAudit?: GroundedClaimAudit | null;
  state: StageState;
}) {
  const counts: Record<NLIRelation, number> = {
    ENTAILMENT: 0,
    CONTRADICTION: 0,
    NEUTRAL: 0,
  };
  classification?.relations.forEach(({ relation }) => {
    counts[relation] += 1;
  });
  const relevanceFiltered = classification?.relations.filter((item) => item.relevanceFiltered).length ?? 0;

  return (
    <section className="support-summary" aria-labelledby={`support-summary-${classification?.atomId ?? "pending"}`}>
      <div className="support-summary-heading">
        <h3 id={`support-summary-${classification?.atomId ?? "pending"}`}>
          Grounded evidence relations
        </h3>
        <span aria-live="polite">{stateLabel(state)}</span>
      </div>
      <p>
        Provenance-constrained selections behind the draft evidence position; the reference label is never an input.
      </p>
      {state === "complete" ? (
        <>
          <ul className="support-counts" aria-label="Selected atom relation counts">
            {(Object.keys(RELATION_LABELS) as NLIRelation[]).map((relation) => (
              <li className={`relation-${relation.toLowerCase()}`} key={relation}>
                <strong>{counts[relation]}</strong> {RELATION_LABELS[relation]}
              </li>
            ))}
          </ul>
          {relevanceFiltered ? (
            <p className="support-summary-state">
              {relevanceFiltered} unrelated candidate{relevanceFiltered === 1 ? " was" : "s were"} kept neutral by the relevance gate.
            </p>
          ) : null}
          {audit ? (
            <p className="support-summary-state">
              Support audit: {audit.reason}
            </p>
          ) : null}
          {claimAudit ? (
            <p className="support-summary-state">
              Overall position: {claimAudit.position.replace(/_/g, " ").toLowerCase()}. {claimAudit.reason}
            </p>
          ) : null}
          {materialOmission?.detected ? (
            <p className="support-summary-state">
              Material omission detected: {materialOmission.reason}
            </p>
          ) : null}
        </>
      ) : (
        <p className="support-summary-state">
          {state === "running"
              ? "Auditing candidate evidence…"
              : state === "error"
              ? "Relations are unavailable. Retry the evidence audit in the pipeline."
              : "Relations appear after candidate retrieval."}
        </p>
      )}
    </section>
  );
}
