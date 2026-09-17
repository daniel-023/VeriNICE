import type {
  AtomEvidenceAssessment,
  CandidateRelation,
  GroundedObligationAudit,
  StageState,
} from "@/lib/types";

function stateLabel(state: StageState): string {
  if (state === "running") return "Assessing";
  if (state === "complete") return "Assessed";
  if (state === "error") return "Unavailable";
  return "Waiting";
}

export function SupportSummary({
  classification,
  audit,
  state,
}: {
  classification: AtomEvidenceAssessment | null;
  audit?: GroundedObligationAudit | null;
  state: StageState;
}) {
  const counts: Record<CandidateRelation, number> = {
    SUPPORTS: 0,
    REFUTES: 0,
    CONTEXT: 0,
    NOT_SELECTED: 0,
  };
  classification?.relations.forEach(({ relation }) => { counts[relation] += 1; });
  const mismatchCount = classification?.relations.filter(
    ({ scopeCheck }) => scopeCheck?.status === "MISMATCH",
  ).length ?? 0;
  const unresolvedIdentityChecks = audit?.identityChecks?.filter(
    ({ status }) => status === "UNRESOLVED",
  ) ?? [];
  const sufficient = audit?.sufficiency === "SUFFICIENT";
  const selectedCount = counts.SUPPORTS + counts.REFUTES + counts.CONTEXT;
  const mainRelations = (["SUPPORTS", "REFUTES", "CONTEXT"] as CandidateRelation[]).filter(
    (relation) => sufficient && counts[relation] > 0,
  );
  const exceptionalScopeChecks = audit?.scopeChecks.filter(
    ({ status }) => status === "MISMATCH" || status === "UNRESOLVED",
  ) ?? [];
  const groupedScopeChecks = Array.from(
    exceptionalScopeChecks.reduce((groups, check) => {
      const key = `${check.status}:${check.reason}`;
      const current = groups.get(key);
      groups.set(key, current ? { ...current, count: current.count + 1 } : { ...check, count: 1 });
      return groups;
    }, new Map<string, (typeof exceptionalScopeChecks)[number] & { count: number }>()).values(),
  );
  const relationLabel = (relation: CandidateRelation): string => {
    if (relation === "SUPPORTS") return sufficient ? "support" : "potential support";
    if (relation === "REFUTES") return sufficient ? "refutation" : "potential refutation";
    if (relation === "CONTEXT") return "neutral";
    return "not selected";
  };

  return (
    <section className="support-summary" aria-labelledby={`support-summary-${classification?.atomId ?? "pending"}`}>
      <div className="support-summary-heading">
        <h3 id={`support-summary-${classification?.atomId ?? "pending"}`}>Evidence Assessment</h3>
        <span className={state === "complete" ? "sr-only" : undefined} aria-live="polite">{stateLabel(state)}</span>
      </div>
      {state === "complete" ? (
        <>
          {audit ? (
            <p className={`sufficiency-badge sufficiency-${audit.sufficiency.toLowerCase()}`}>
              {audit.sufficiency.replaceAll("_", " ").toLowerCase()} evidence
            </p>
          ) : null}
          {mainRelations.length || mismatchCount || unresolvedIdentityChecks.length ? <ul className="support-counts" aria-label="Decisive evidence relation counts">
            {mainRelations.map((relation) => (
              <li className={`relation-${relation.toLowerCase()}`} key={relation}>
                <strong>{counts[relation]}</strong> {relationLabel(relation)}
              </li>
            ))}
            {mismatchCount ? <li><strong>{mismatchCount}</strong> excluded by source scope</li> : null}
            {unresolvedIdentityChecks.length ? (
              <li><strong>{unresolvedIdentityChecks.length}</strong> unresolved identity alignment</li>
            ) : null}
          </ul> : null}
          {selectedCount === 0 ? <p className="support-summary-state">No evidence was selected.</p> : null}
          {!sufficient && selectedCount > 0 ? (
            <p className="support-summary-notice">No decisive relation. Provisional selections do not affect the verdict.</p>
          ) : null}
          {audit ? (
            <details className="support-details">
              <summary>Assessment details</summary>
              {!sufficient && selectedCount > 0 ? (
                <p>
                  <strong>Provisional selections</strong><br />
                  {[
                    counts.SUPPORTS ? `${counts.SUPPORTS} support` : "",
                    counts.REFUTES ? `${counts.REFUTES} refute` : "",
                    counts.CONTEXT ? `${counts.CONTEXT} neutral` : "",
                  ].filter(Boolean).join(" · ")}
                </p>
              ) : null}
              {audit.missingInformation ? (
                <p><strong>Missing information</strong><br />{audit.missingInformation}</p>
              ) : null}
              <p><strong>Rationale</strong><br />{audit.reason}</p>
              {groupedScopeChecks.length ? (
                <>
                  <strong>Source-scope checks</strong>
                  <ul>
                    {groupedScopeChecks.map((check) => (
                      <li key={`${check.status}:${check.reason}`}>
                        <strong>{check.count} {check.status.replaceAll("_", " ").toLowerCase()}:</strong> {check.reason}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {audit.identityChecks?.length ? (
                <>
                  <strong>Identity-alignment checks</strong>
                  <ul>
                    {audit.identityChecks.map((check) => (
                      <li key={`${check.relation}:${check.spanIds.join(":")}`}>
                        <strong>{check.relation.toLowerCase()} · {check.status.replaceAll("_", " ").toLowerCase()}:</strong>{" "}
                        {check.reason}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </details>
          ) : null}
        </>
      ) : (
        <p className="support-summary-state">
          {state === "running"
            ? "Assessing the evidence bundle…"
            : state === "error"
              ? "Evidence assessment is unavailable. Retry this stage."
              : "The assessment appears after retrieval."}
        </p>
      )}
    </section>
  );
}
