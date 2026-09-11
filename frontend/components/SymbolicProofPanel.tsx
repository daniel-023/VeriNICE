import type { DemoDocument, StageState, SymbolicExecution, SymbolicPremise } from "@/lib/types";

const OPERATOR_LABELS: Record<SymbolicExecution["operator"], string> = {
  SET_MEMBERSHIP: "Set membership",
  NUMERIC_COMPARE: "Numeric comparison",
  TEMPORAL_COMPARE: "Temporal comparison",
  ATTRIBUTE_COMPARE: "Attribute comparison",
  COUNT_DISTINCT: "Distinct-value count",
  EXTREMUM_COMPARE: "Extremum check",
};

const PROGRAM_STEP_DESCRIPTIONS: Record<string, string> = {
  LOOKUP: "Read a grounded source fact.",
  EQUAL: "Compare aligned values.",
  MEMBER: "Check membership in the grounded set.",
  NUMERIC_COMPARE: "Compare aligned numeric values.",
  TEMPORAL_COMPARE: "Compare aligned dates.",
  COUNT_DISTINCT: "Count distinct grounded values.",
  EXTREMUM_COUNTEREXAMPLE: "Check for a grounded counterexample.",
};

function statusLabel(status: SymbolicExecution["status"]): string {
  return status === "NOT_APPLICABLE" ? "Not applicable" : status[0] + status.slice(1).toLowerCase();
}

function executionLabel(proof: SymbolicExecution): string {
  return statusLabel(proof.status);
}

function contributionLabel(proof: SymbolicExecution): string | null {
  if (proof.relation === "SUPPORTS") return "Supports this atomic claim";
  if (proof.relation === "REFUTES") return "Refutes this atomic claim";
  return null;
}

function ProofCard({
  proof,
  documents,
  onSelectPremise,
}: {
  proof: SymbolicExecution;
  documents: DemoDocument[];
  onSelectPremise: (premise: SymbolicPremise) => void;
}) {
  const titles = new Map(documents.map((document) => [document.id, document.title]));
  return (
    <article className={`symbolic-proof proof-${proof.status.toLowerCase()}`}>
      <div><strong>{OPERATOR_LABELS[proof.operator]}</strong><span>{statusLabel(proof.status)}</span></div>
      {contributionLabel(proof) ? (
        <p className={`symbolic-contribution contribution-${proof.relation?.toLowerCase()}`}>
          <strong>Effect on this atom</strong>
          <span>{contributionLabel(proof)}</span>
        </p>
      ) : null}
      <code>{proof.expression}</code>
      <p>{proof.conclusion}</p>
      {proof.premises.length ? (
        <div className="symbolic-premises">
          <strong>Decisive premises</strong>
          {proof.premises.map((premise) => (
            <button type="button" key={premise.id} onClick={() => onSelectPremise(premise)}>
              <span>{titles.get(premise.documentId) ?? premise.documentId}</span>
              <small>{premise.kind === "LIST_CERTIFICATE" && premise.itemCount != null
                ? `Complete list · ${premise.itemCount} items${premise.listItems?.length
                  ? `: ${premise.listItems.map((item) => item.text).join(", ")}`
                  : ""}`
                : premise.text}</small>
            </button>
          ))}
        </div>
      ) : null}
      <details>
        <summary>Rule details</summary>
        <ol className="symbolic-execution-summary" aria-label="Symbolic processing steps">
          <li><span>Rule selected</span><small>Grounded inputs mapped</small></li>
          <li><span>Premises checked</span><small>{executionLabel(proof)}</small></li>
        </ol>
        <ol className="symbolic-program-steps">
          {(proof.program?.steps ?? []).map((step) => (
            <li key={step.id}>
              <code>{step.operation.replaceAll("_", " ").toLowerCase()}</code>
              <span>{PROGRAM_STEP_DESCRIPTIONS[step.operation] ?? "Apply the grounded operation."}</span>
            </li>
          ))}
          {!proof.program?.steps?.length ? <li>Program trace unavailable.</li> : null}
        </ol>
        {proof.validationWarnings.length ? (
          <ul>{proof.validationWarnings.map((item) => <li key={item}>{item.replaceAll("_", " ").toLowerCase()}</li>)}</ul>
        ) : <p>No validation warnings.</p>}
      </details>
    </article>
  );
}

export function SymbolicProofPanel({
  atomId,
  proofs,
  state,
  documents,
  onSelectPremise,
}: {
  atomId: string;
  proofs: SymbolicExecution[];
  state: StageState;
  documents: DemoDocument[];
  onSelectPremise: (premise: SymbolicPremise) => void;
}) {
  const resolved = proofs.filter((proof) => proof.status === "PROVED" || proof.status === "DISPROVED");
  const unresolved = proofs.filter((proof) => proof.status === "UNRESOLVED" || proof.status === "NOT_APPLICABLE");
  const summary = state === "running"
    ? "Mapping"
    : state === "error"
      ? "Unavailable"
      : resolved.length
        ? statusLabel(resolved[0].status)
        : state === "complete"
          ? (unresolved.length ? "Unresolved" : "Not applicable")
          : "Waiting";

  return (
    <section className="symbolic-proof-panel" id={`symbolic-checks-${atomId}`} aria-labelledby={`symbolic-proof-heading-${atomId}`}>
      <div className="support-summary-heading">
        <h3 id={`symbolic-proof-heading-${atomId}`}>Symbolic Checks</h3>
        <span aria-live="polite">{summary}</span>
      </div>
      {state === "complete" && proofs.length === 0 ? <p className="support-summary-state">No symbolic rule applies.</p> : null}
      {resolved.map((proof) => (
        <ProofCard key={proof.id} proof={proof} documents={documents} onSelectPremise={onSelectPremise} />
      ))}
      {unresolved.length ? (
        <details className="symbolic-unresolved">
          <summary>{unresolved.length} check{unresolved.length === 1 ? "" : "s"} with no result</summary>
          {unresolved.map((proof) => (
            <ProofCard key={proof.id} proof={proof} documents={documents} onSelectPremise={onSelectPremise} />
          ))}
        </details>
      ) : null}
    </section>
  );
}
