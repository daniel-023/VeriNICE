import { Check, Minus, TriangleAlert, X } from "lucide-react";
import type {
  DecomposedAtom,
  ObligationEvidenceState,
  ReferenceLabel,
  VerdictAggregationResult,
} from "@/lib/types";

function display(value: string): string {
  return value.replaceAll("_", " ");
}

function verdictClass(verdict: ReferenceLabel): string {
  return `verdict-${verdict.toLowerCase().replaceAll("_", "-")}`;
}

const STATE_ICON: Record<ObligationEvidenceState, typeof Check> = {
  SUPPORTED: Check,
  REFUTED: X,
  CONFLICTING: TriangleAlert,
  UNRESOLVED: Minus,
};

const COMPOSITION_RULE: Record<string, string> = {
  SINGLE: "One obligation decides the case.",
  AND: "Every obligation must be supported; an attack on any obligation refutes the claim.",
  OR: "Any supported obligation supports the claim; every obligation must be attacked to refute it.",
};

export function VerdictPanel({
  result,
  atoms,
  referenceLabel,
}: {
  result: VerdictAggregationResult;
  atoms: DecomposedAtom[];
  referenceLabel?: ReferenceLabel;
}) {
  const match = referenceLabel === undefined ? null : result.verdict === referenceLabel;
  const textByAtomId = new Map(atoms.map((atom) => [atom.id, atom.text]));

  return (
    <section className="verdict-panel" id="case-verdict" aria-labelledby="verdict-heading">
      <div className="verdict-headline">
        <div>
          <p className="eyebrow">Stage 05 · Deterministic aggregation</p>
          <h2 id="verdict-heading">
            Rule-derived evidence status
            <span className={`verdict-chip ${verdictClass(result.verdict)}`}>
              {display(result.verdict)}
            </span>
          </h2>
          <p className="verdict-rule">
            {result.positions.groundedClaimPosition
              ? "A provenance-constrained claim audit supplies the overall position; rules map it to this draft status."
              : COMPOSITION_RULE[result.composition] ?? COMPOSITION_RULE.SINGLE}
          </p>
        </div>
        {match !== null ? (
          <p className={`verdict-match ${match ? "match" : "mismatch"}`}>
            <span>Dataset reference</span>
            <strong>{display(referenceLabel!)}</strong>
            <em>{match ? "matches" : "differs"}</em>
          </p>
        ) : null}
      </div>

      <div className="verdict-positions" aria-label="Claim-level evidence positions">
        {result.positions.groundedClaimPosition ? (
          <span className="position-held">
            Audit: {display(result.positions.groundedClaimPosition)}
          </span>
        ) : null}
        <span className={result.positions.supportPosition ? "position-held" : "position-absent"}>
          {result.positions.supportPosition ? "Support position held" : "No support position"}
        </span>
        <span className={result.positions.attackPosition ? "position-held" : "position-absent"}>
          {result.positions.attackPosition ? "Attack position held" : "No attack position"}
        </span>
        {result.positions.materialOmissionPosition ? (
          <span className="position-held">Material-omission position held</span>
        ) : null}
      </div>

      <ul className="verdict-obligations" aria-label="Obligation evidence states">
        {result.obligations.map((item, index) => {
          const Icon = STATE_ICON[item.state];
          return (
            <li key={item.obligationId} className={`obligation-${item.state.toLowerCase()}`}>
              <span className="verdict-obligation-index" aria-hidden="true">O{index + 1}</span>
              <span className="verdict-obligation-text">
                {textByAtomId.get(item.obligationId) ?? item.obligationId}
              </span>
              <span className="verdict-obligation-state">
                <Icon size={13} aria-hidden="true" />
                {display(item.state)}
              </span>
              <span className="verdict-obligation-counts">
                {item.supportEdgeIds.length} support · {item.attackEdgeIds.length} attack ·{" "}
                {item.neutralCandidateCount} neutral
              </span>
            </li>
          );
        })}
      </ul>

      <details className="verdict-trace-details">
        <summary>Decision trace</summary>
        <ol className="verdict-trace">
          {result.ruleTrace.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        {result.warnings.length ? (
          <p className="verdict-warnings">
            Inspection notes (verdict-neutral):{" "}
            {result.warnings.map((item) => display(item.code.toLowerCase())).join(", ")}
          </p>
        ) : null}
      </details>
    </section>
  );
}
