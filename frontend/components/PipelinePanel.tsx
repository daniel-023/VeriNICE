import {
  Braces,
  Check,
  FileSearch,
  Gavel,
  GitBranch,
  LoaderCircle,
  Scale,
} from "lucide-react";
import type { ReferenceLabel, RetrievalMethod, StageState } from "@/lib/types";
import { MAX_EVIDENCE_PER_ATOM, MIN_EVIDENCE_PER_ATOM } from "@/lib/retrieval";

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
  graphLinkCount,
  atomCount,
  evidenceCount,
  relationCount,
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
  graphLinkCount: number;
  atomCount: number;
  evidenceCount: number;
  relationCount: number;
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
        ? `${relationCount} assessed relation${relationCount === 1 ? "" : "s"}.`
        : assessmentState === "error"
          ? "Assessment failed."
          : retrievalState === "complete"
            ? "Ready."
            : "";
  const reasoningCopy =
    reasoningState === "complete"
      ? `${graphLinkCount} graph relation${graphLinkCount === 1 ? "" : "s"}.`
      : reasoningState === "running"
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
