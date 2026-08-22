import {
  Braces,
  Check,
  FileSearch,
  Gavel,
  GitBranch,
  LoaderCircle,
  Scale,
} from "lucide-react";
import type { ReferenceLabel, StageState } from "@/lib/types";

function verdictWord(verdict: ReferenceLabel): string {
  return verdict.replaceAll("_", " ").toLowerCase();
}

export function PipelinePanel({
  decompositionState,
  retrievalState,
  nliState,
  graphState,
  verdictState = "idle",
  verdict = null,
  graphLinkCount,
  atomCount,
  evidenceCount,
  relationCount,
  onRetryEvidence,
  onRetryNli,
  recorded = false,
}: {
  decompositionState: StageState;
  retrievalState: StageState;
  nliState: StageState;
  graphState: StageState;
  verdictState?: StageState;
  verdict?: ReferenceLabel | null;
  graphLinkCount: number;
  atomCount: number;
  evidenceCount: number;
  relationCount: number;
  onRetryEvidence: () => void;
  onRetryNli: () => void;
  recorded?: boolean;
}) {
  const decompositionCopy =
    decompositionState === "running"
      ? "The LLM is identifying independently verifiable facts."
      : decompositionState === "complete"
        ? `${atomCount} atomic claim${atomCount === 1 ? "" : "s"} ready.`
        : decompositionState === "error"
          ? "Decomposition failed. Correct the issue and retry."
          : "Ready when you click Decompose Claim.";
  const retrievalCopy =
    retrievalState === "running"
      ? "Semantically matching atomic claims to sentences across sources."
      : retrievalState === "complete"
        ? `${evidenceCount} candidate evidence sentence${evidenceCount === 1 ? "" : "s"} matched.`
        : retrievalState === "error"
          ? "Atoms are preserved. Retry candidate evidence retrieval only."
          : decompositionState === "complete"
            ? "Waiting to search the source documents."
            : "Runs automatically after decomposition.";
  const nliCopy =
    nliState === "running"
      ? "Comparing every candidate sentence with its atomic claim."
      : nliState === "complete"
        ? `${relationCount} sentence relation${relationCount === 1 ? "" : "s"} classified.`
        : nliState === "error"
          ? "Atoms and candidate evidence are preserved. Retry NLI only."
          : retrievalState === "complete"
            ? "Waiting to classify the retrieved candidates."
            : "Runs automatically after candidate retrieval.";
  const verdictCopy =
    verdictState === "complete" && verdict
      ? `Aggregated to ${verdictWord(verdict)}.`
      : verdictState === "running"
        ? "Applying the composition rule to every obligation."
        : verdictState === "error"
          ? "Aggregation is unavailable. The graph above is unchanged."
          : graphState === "complete"
            ? "Waiting to aggregate obligation states."
            : "Runs automatically after the argumentation graph.";

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
            <strong>LLM Claim Decomposition</strong>
            <p>{decompositionCopy}</p>
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
            <strong>Semantic Candidate Matching</strong>
            <p>{retrievalCopy}</p>
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

        <li className={`pipeline-stage stage-${nliState}`}>
          <span className="stage-icon">
            {nliState === "running" ? (
              <LoaderCircle className="spin" size={19} aria-hidden="true" />
            ) : nliState === "complete" ? (
              <Check size={19} aria-hidden="true" />
            ) : (
              <Scale size={19} aria-hidden="true" />
            )}
          </span>
          <span className="stage-copy">
            <small>03 · {recorded ? "RECORDED" : "LIVE"}</small>
            <strong>NLI Support Classification</strong>
            <p>{nliCopy}</p>
          </span>
          <span className="stage-actions">
            <span className="stage-state">{stateLabel(nliState)}</span>
            {nliState === "error" ? (
              <button type="button" className="retry-button" onClick={onRetryNli}>
                Retry NLI
              </button>
            ) : null}
          </span>
        </li>

        <li className={`pipeline-stage stage-${graphState}`}>
          <span className="stage-icon">
            {graphState === "complete" ? <Check size={19} aria-hidden="true" /> : <GitBranch size={19} aria-hidden="true" />}
          </span>
          <span className="stage-copy">
            <small>04 · DERIVED</small>
            <strong>Argumentation Graph</strong>
            <p>
              {graphState === "complete"
                ? `${graphLinkCount} support or contradiction link${graphLinkCount === 1 ? "" : "s"} ready to inspect.`
                : graphState === "running"
                  ? "Waiting for sentence-level NLI relations."
                  : "Appears after NLI classification completes."}
            </p>
            {graphState === "complete" ? (
              <a className="stage-link" href="#argumentation-graph">View Argumentation Graph</a>
            ) : null}
          </span>
          <span className="stage-state">{stateLabel(graphState)}</span>
        </li>

        <li className={`pipeline-stage stage-${verdictState}`}>
          <span className="stage-icon">
            {verdictState === "complete" ? <Check size={19} aria-hidden="true" /> : <Gavel size={19} aria-hidden="true" />}
          </span>
          <span className="stage-copy">
            <small>05 · DETERMINISTIC</small>
            <strong>Four-way Verdict</strong>
            <p>{verdictCopy}</p>
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
