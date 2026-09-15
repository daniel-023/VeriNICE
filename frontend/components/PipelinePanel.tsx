import {
  Braces,
  Check,
  FileSearch,
  Gavel,
  GitBranch,
  Info,
  LoaderCircle,
  Scale,
} from "lucide-react";
import type {
  CandidateRelation,
  ReferenceLabel,
  RetrievalMethod,
  StageState,
  SymbolicExecution,
} from "@/lib/types";
import { MAX_EVIDENCE_PER_ATOM, MIN_EVIDENCE_PER_ATOM } from "@/lib/retrieval";

type EvidenceRelationCounts = Record<CandidateRelation, number>;

const EVIDENCE_RELATIONS: Array<{
  relation: CandidateRelation;
  label: string;
  description: string;
}> = [
  { relation: "SUPPORTS", label: "Supports", description: "Directly establishes the atomic claim." },
  { relation: "REFUTES", label: "Refutes", description: "Directly contradicts the atomic claim." },
  { relation: "CONTEXT", label: "Context", description: "Helps interpret evidence but establishes neither truth value." },
  { relation: "NOT_SELECTED", label: "Not used", description: "Was retrieved but not selected for assessment." },
];

const SYMBOLIC_RULES: Array<{
  operator: SymbolicExecution["operator"];
  label: string;
  description: string;
}> = [
  { operator: "SET_MEMBERSHIP", label: "Set membership", description: "Checks whether an item appears in a source list; absence counts only when the list is complete." },
  { operator: "NUMERIC_COMPARE", label: "Numeric comparison", description: "Compares numbers when they refer to the same quantity, unit, entity, and time." },
  { operator: "TEMPORAL_COMPARE", label: "Temporal comparison", description: "Compares absolute dates or date ranges tied to the same event." },
  { operator: "ATTRIBUTE_COMPARE", label: "Attribute comparison", description: "Compares a claimed attribute with an explicitly stated source attribute using a supported pattern." },
  { operator: "COUNT_DISTINCT", label: "Distinct-value count", description: "Counts distinct source values; an exact total requires a complete list." },
  { operator: "EXTREMUM_COMPARE", label: "Largest/smallest comparison", description: "Finds a comparable counterexample that can refute a largest or smallest claim." },
];
const SYMBOLIC_RULES_BY_OPERATOR = new Map(
  SYMBOLIC_RULES.map((rule) => [rule.operator, rule]),
);

function ruleOutcome(proof: SymbolicExecution): {
  label: "Supports" | "Refutes" | "Unresolved" | "Not applicable";
  className: "supports" | "refutes" | "unresolved" | "not-applicable";
} {
  if (proof.relation === "SUPPORTS") return { label: "Supports", className: "supports" };
  if (proof.relation === "REFUTES") return { label: "Refutes", className: "refutes" };
  if (proof.status === "UNRESOLVED") return { label: "Unresolved", className: "unresolved" };
  return { label: "Not applicable", className: "not-applicable" };
}

type RuleResultGroup = {
  key: string;
  label: string;
  count: number;
  outcome: ReturnType<typeof ruleOutcome>;
};

const PROFILE_LABELS: Record<string, string> = {
  GENERIC_DISTINCT_VALUES: "Explicit category values",
  AWARD_RECIPIENT: "Award recipient",
  AWARD_MOTIVATION: "Award motivation",
  COUNTRY_LOCATION: "Country location",
  EXCLUSIVE_PURPOSE: "Exclusive purpose",
  EXPLICIT_NEGATION: "Explicit negation",
};

function groupRuleResults(executions: SymbolicExecution[]): RuleResultGroup[] {
  const groups = new Map<string, RuleResultGroup>();
  executions.forEach((proof) => {
    const outcome = ruleOutcome(proof);
    const key = `${proof.operator}:${proof.profile}:${outcome.className}`;
    const existing = groups.get(key);
    if (existing) {
      existing.count += 1;
      return;
    }
    groups.set(key, {
      key,
      label: [
        SYMBOLIC_RULES_BY_OPERATOR.get(proof.operator)?.label
          ?? proof.operator.replaceAll("_", " ").toLowerCase(),
        PROFILE_LABELS[proof.profile],
      ].filter(Boolean).join(" · "),
      count: 1,
      outcome,
    });
  });
  return [...groups.values()];
}

function verdictWord(verdict: ReferenceLabel): string {
  return verdict.replaceAll("_", " ").toLowerCase();
}

const RETRIEVAL_METHOD_LABELS: Record<RetrievalMethod, string> = {
  HYBRID: "Hybrid",
  SEMANTIC: "Semantic",
  LEXICAL: "Lexical",
};

const RETRIEVAL_METHOD_HELP: Record<RetrievalMethod, string> = {
  HYBRID: "Combines semantic and lexical rankings using equal-weight reciprocal-rank fusion.",
  SEMANTIC: "Ranks sentences by cosine similarity between normalized BGE embeddings.",
  LEXICAL: "Ranks normalized token overlap, with bonuses for matching numbers and list entries.",
};

export function PipelinePanel({
  decompositionState,
  retrievalState,
  assessmentState,
  reasoningState,
  verdictState = "idle",
  verdict = null,
  atomCount,
  evidenceCount,
  relationCounts,
  symbolicExecutions,
  onRetryEvidence,
  onRetryAssessment,
  onRetryReasoning,
  evidencePerAtom,
  onEvidencePerAtomChange,
  retrievalMethod = "HYBRID",
  onRetrievalMethodChange,
  recorded = false,
}: {
  decompositionState: StageState;
  retrievalState: StageState;
  assessmentState: StageState;
  reasoningState: StageState;
  verdictState?: StageState;
  verdict?: ReferenceLabel | null;
  atomCount: number;
  evidenceCount: number;
  relationCounts: EvidenceRelationCounts;
  symbolicExecutions: SymbolicExecution[];
  onRetryEvidence: () => void;
  onRetryAssessment: () => void;
  onRetryReasoning: () => void;
  evidencePerAtom?: number;
  /** Omitted when the budget cannot be changed, as in recorded walkthroughs. */
  onEvidencePerAtomChange?: (value: number) => void;
  retrievalMethod?: RetrievalMethod;
  /** Omitted when the retrieval method cannot be changed in a recorded run. */
  onRetrievalMethodChange?: (value: RetrievalMethod) => void;
  recorded?: boolean;
}) {
  const retrievalMethodLabel = RETRIEVAL_METHOD_LABELS[retrievalMethod];
  const decompositionCopy =
    decompositionState === "running"
      ? "Finding atomic claims."
      : decompositionState === "complete"
        ? `${atomCount} atomic claim${atomCount === 1 ? "" : "s"}.`
        : decompositionState === "error"
          ? "Decomposition failed."
          : "";
  const retrievalCopy =
    retrievalState === "running"
      ? "Matching source sentences."
      : retrievalState === "complete"
        ? `${evidenceCount} candidate sentence${evidenceCount === 1 ? "" : "s"}.`
        : retrievalState === "error"
          ? "Retrieval failed."
          : decompositionState === "complete"
            ? "Ready."
            : "";
  const assessmentCopy =
    assessmentState === "running"
      ? "Assessing matched sentences."
      : assessmentState === "complete"
        ? "Claim-wide relation assessment."
        : assessmentState === "error"
          ? "Assessment failed."
          : retrievalState === "complete"
            ? "Ready."
            : "";
  const reasoningCopy =
    reasoningState === "running"
        ? "Checking applicable rules."
        : reasoningState === "error"
          ? "Rule check failed."
          : "";
  const verdictCopy =
    verdictState === "complete" && verdict
      ? `Result: ${verdictWord(verdict)}.`
      : verdictState === "running"
          ? "Combining atomic-claim results."
        : verdictState === "error"
          ? "Verdict unavailable."
          : reasoningState === "complete"
            ? "Ready."
            : "";
  const executionsByOperator = new Map<SymbolicExecution["operator"], SymbolicExecution[]>();
  symbolicExecutions.forEach((execution) => {
    const current = executionsByOperator.get(execution.operator);
    if (current) current.push(execution);
    else executionsByOperator.set(execution.operator, [execution]);
  });
  const groupedRuleResults = groupRuleResults(symbolicExecutions);
  const decisiveRuleResults = groupedRuleResults.filter(
    ({ outcome }) => outcome.className === "supports" || outcome.className === "refutes",
  );
  const otherRuleResults = groupedRuleResults.filter(
    ({ outcome }) => outcome.className !== "supports" && outcome.className !== "refutes",
  );

  const renderRuleResults = (groups: RuleResultGroup[], label: string) => (
    <div className="stage-rule-group">
      <p className="stage-rule-group-label">{label}</p>
      <ul className="stage-rule-results" aria-label={label}>
        {groups.map((group) => (
          <li className={`stage-rule-${group.outcome.className}`} key={group.key}>
            <span className="stage-rule-marker" aria-hidden="true" />
            <span className="stage-rule-name">
              {group.label}
              {group.count > 1 ? <small aria-label={`${group.count} executions`}> ×{group.count}</small> : null}
            </span>
            <strong>{group.outcome.label}</strong>
          </li>
        ))}
      </ul>
    </div>
  );

  const stateLabel = (state: StageState) =>
    state === "complete"
      ? "Complete"
      : state === "running"
        ? "Running"
        : state === "error"
          ? "Error"
          : "Ready";

  return (
    <section className="pipeline-panel" aria-labelledby="pipeline-heading">
      <div className="graph-heading">
        <div>
          <p className="eyebrow">Verification Pipeline</p>
          <h2 id="pipeline-heading">From Claim to Verdict</h2>
        </div>
        <span>{recorded ? "5 recorded stages" : "5 live stages"}</span>
      </div>

      <ol className="pipeline-stages">
        <li className={`pipeline-stage stage-${decompositionState}`}>
          <span className="stage-icon">
            {decompositionState === "running" ? (
              <LoaderCircle className="spin" size={19} aria-hidden="true" />
            ) : decompositionState === "complete" ? (
              <Check size={19} aria-hidden="true" />
            ) : (
              <Braces size={19} aria-hidden="true" />
            )}
          </span>
          <span className="stage-copy">
            <small>01 · {recorded ? "RECORDED" : "LIVE"}</small>
            <strong>Decompose Claim</strong>
            {decompositionCopy ? <p>{decompositionCopy}</p> : null}
          </span>
          <span className="stage-state">
            {stateLabel(decompositionState)}
          </span>
        </li>

        <li className={`pipeline-stage stage-${retrievalState}`}>
          <span className="stage-icon">
            {retrievalState === "running" ? (
              <LoaderCircle className="spin" size={19} aria-hidden="true" />
            ) : retrievalState === "complete" ? (
              <Check size={19} aria-hidden="true" />
            ) : (
              <FileSearch size={19} aria-hidden="true" />
            )}
          </span>
          <span className="stage-copy">
            <small>02 · {recorded ? "RECORDED" : "LIVE"}</small>
            <strong>Retrieve Evidence</strong>
            {retrievalCopy ? <p>{retrievalCopy}</p> : null}
            <details
              className="stage-retrieval-options"
              open={recorded ? true : undefined}
            >
              <summary
                onClick={
                  recorded ? (event) => event.preventDefault() : undefined
                }
              >
                Evidence Matching: {retrievalMethodLabel}
              </summary>
              <div className="stage-retrieval-controls">
                  <label className="stage-budget">
                    <span>Matching method</span>
                    <select
                      name="retrieval-method"
                      value={retrievalMethod}
                      disabled={!onRetrievalMethodChange || retrievalState === "running"}
                      aria-describedby="retrieval-method-help retrieval-rerun-help"
                      onChange={(event) => onRetrievalMethodChange?.(event.target.value as RetrievalMethod)}
                    >
                      <option value="HYBRID">Hybrid</option>
                      <option value="SEMANTIC">Semantic</option>
                      <option value="LEXICAL">Lexical</option>
                    </select>
                  </label>
                  {evidencePerAtom !== undefined ? (
                    <label className="stage-budget">
                      <span>Candidate sentences per atomic claim</span>
                      <select
                        name="evidence-per-atom"
                        value={evidencePerAtom}
                        disabled={!onEvidencePerAtomChange || retrievalState === "running"}
                        aria-describedby="retrieval-rerun-help"
                        onChange={(event) => onEvidencePerAtomChange?.(Number(event.target.value))}
                      >
                        {Array.from(
                          { length: MAX_EVIDENCE_PER_ATOM - MIN_EVIDENCE_PER_ATOM + 1 },
                          (_, index) => MIN_EVIDENCE_PER_ATOM + index,
                        ).map((value) => (
                          <option key={value} value={value}>{value}</option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  <p className="stage-retrieval-help" id="retrieval-method-help">
                    {RETRIEVAL_METHOD_HELP[retrievalMethod]}
                  </p>
                  <p className="stage-retrieval-help" id="retrieval-rerun-help">
                    {recorded
                      ? "These recorded values are fixed here. In a live run, changing either setting reruns evidence retrieval and all later stages."
                      : "Changing either setting reruns evidence retrieval and all later stages."}
                  </p>
              </div>
            </details>
          </span>
          <span className="stage-actions">
            <span className="stage-state">{stateLabel(retrievalState)}</span>
            {retrievalState === "error" ? (
              <button type="button" className="retry-button" onClick={onRetryEvidence}>
                Retry Evidence
              </button>
            ) : null}
          </span>
        </li>

        <li className={`pipeline-stage stage-${assessmentState}`}>
          <span className="stage-icon">
            {assessmentState === "running" ? (
              <LoaderCircle className="spin" size={19} aria-hidden="true" />
            ) : assessmentState === "complete" ? (
              <Check size={19} aria-hidden="true" />
            ) : (
              <Scale size={19} aria-hidden="true" />
            )}
          </span>
          <span className="stage-copy">
            <small>03 · {recorded ? "RECORDED" : "LIVE"}</small>
            <strong>Assess Evidence</strong>
            {assessmentCopy ? <p>{assessmentCopy}</p> : null}
            {assessmentState === "complete" ? (
              <>
                <p className="stage-summary-label">Claim-Wide Relations</p>
                <ul className="stage-result-chips" aria-label="Claim-wide evidence relation counts">
                  {EVIDENCE_RELATIONS.map(({ relation, label }) => (
                    <li
                      className={`stage-result-${relation.toLowerCase().replaceAll("_", "-")}${relationCounts[relation] === 0 ? " is-zero" : ""}`}
                      key={relation}
                    >
                      <strong>{relationCounts[relation]}</strong>
                      <span>{label}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            <details className="stage-explainer">
              <summary><Info size={13} aria-hidden="true" />How Evidence Relations Work</summary>
              <div className="stage-explainer-content">
                <dl>
                  {EVIDENCE_RELATIONS.map(({ relation, label, description }) => (
                    <div key={relation}>
                      <dt>{label}</dt>
                      <dd>{description}</dd>
                    </div>
                  ))}
                </dl>
                <p>Support and refutation affect the verdict only when the evidence bundle for that atomic claim is sufficient.</p>
              </div>
            </details>
          </span>
          <span className="stage-actions">
            <span className="stage-state">{stateLabel(assessmentState)}</span>
            {assessmentState === "error" ? (
              <button type="button" className="retry-button" onClick={onRetryAssessment}>
                Retry Assessment
              </button>
            ) : null}
          </span>
        </li>

        <li className={`pipeline-stage stage-${reasoningState}`}>
          <span className="stage-icon">
            {reasoningState === "complete" ? <Check size={19} aria-hidden="true" /> : reasoningState === "running" ? <LoaderCircle className="spin" size={19} aria-hidden="true" /> : <GitBranch size={19} aria-hidden="true" />}
          </span>
          <span className="stage-copy">
            <small>04 · {recorded ? "RECORDED" : "LIVE"}</small>
            <strong>Apply Symbolic Rules</strong>
            {reasoningCopy ? <p>{reasoningCopy}</p> : null}
            {reasoningState === "complete" ? (
              symbolicExecutions.length ? (
                <>
                  <p className="stage-summary-label">Checks in This Run</p>
                  <div className="stage-rule-groups" role="group" aria-label="Symbolic checks in this run">
                    {decisiveRuleResults.length
                      ? renderRuleResults(decisiveRuleResults, "Decisive")
                      : null}
                    {otherRuleResults.length
                      ? renderRuleResults(
                          otherRuleResults,
                          decisiveRuleResults.length ? "Other Attempted Checks" : "Attempted Checks",
                        )
                      : null}
                  </div>
                </>
              ) : <p className="stage-direct-evidence">Direct evidence only · no symbolic rule applied.</p>
            ) : null}
            <details className="stage-explainer">
              <summary><Info size={13} aria-hidden="true" />View 6 Rule Types</summary>
              <div className="stage-explainer-content">
                <dl className="stage-rule-catalog">
                  {SYMBOLIC_RULES.map(({ operator, label, description }) => {
                    const executions = executionsByOperator.get(operator) ?? [];
                    const outcomes = [...new Set(executions.map((proof) => ruleOutcome(proof).label))];
                    return (
                      <div className={executions.length ? "is-active" : undefined} key={operator}>
                        <dt>
                          <span>{label}</span>
                          <small>{outcomes.length ? outcomes.join(" · ") : "Available"}</small>
                        </dt>
                        <dd>{description}</dd>
                      </div>
                    );
                  })}
                </dl>
                <p>VeriNICE generates eligible rule and source-premise candidates. The model selects from them, and deterministic Python code validates and executes the chosen rule. Unsupported or ambiguous cases remain unresolved.</p>
              </div>
            </details>
            {reasoningState === "complete" ? (
              <a className="stage-link" href="#reasoning-graph">View Reasoning Graph</a>
            ) : null}
          </span>
          <span className="stage-actions">
            <span className="stage-state">{stateLabel(reasoningState)}</span>
            {reasoningState === "error" ? <button type="button" className="retry-button" onClick={onRetryReasoning}>Retry Rules</button> : null}
          </span>
        </li>

        <li className={`pipeline-stage stage-${verdictState}`}>
          <span className="stage-icon">
            {verdictState === "complete" ? <Check size={19} aria-hidden="true" /> : <Gavel size={19} aria-hidden="true" />}
          </span>
          <span className="stage-copy">
            <small>05 · DETERMINISTIC</small>
            <strong>Verdict</strong>
            {verdictCopy ? <p>{verdictCopy}</p> : null}
            {verdictState === "complete" ? (
              <a className="stage-link" href="#case-verdict">View Verdict</a>
            ) : null}
          </span>
          <span className="stage-state">{stateLabel(verdictState)}</span>
        </li>
      </ol>
    </section>
  );
}
