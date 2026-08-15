import type { AtomSupportClassification, NLIRelation, StageState } from "@/lib/types";

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
  state,
}: {
  classification: AtomSupportClassification | null;
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

  return (
    <section className="support-summary" aria-labelledby={`support-summary-${classification?.atomId ?? "pending"}`}>
      <div className="support-summary-heading">
        <h3 id={`support-summary-${classification?.atomId ?? "pending"}`}>
          NLI Sentence Relations
        </h3>
        <span aria-live="polite">{stateLabel(state)}</span>
      </div>
      <p>
        These are model judgments about candidate sentences, not the case verdict.
      </p>
      {state === "complete" ? (
        <ul className="support-counts" aria-label="Selected atom relation counts">
          {(Object.keys(RELATION_LABELS) as NLIRelation[]).map((relation) => (
            <li className={`relation-${relation.toLowerCase()}`} key={relation}>
              <strong>{counts[relation]}</strong> {RELATION_LABELS[relation]}
            </li>
          ))}
        </ul>
      ) : (
        <p className="support-summary-state">
          {state === "running"
            ? "Classifying candidate sentences…"
            : state === "error"
              ? "Relations are unavailable. Retry NLI in the pipeline."
              : "Relations appear after candidate retrieval."}
        </p>
      )}
    </section>
  );
}
