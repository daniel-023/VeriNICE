import {
  Braces,
  Check,
  CircleDashed,
  FileSearch,
  GitBranch,
  LoaderCircle,
  Scale,
  Split,
} from "lucide-react";
import type { StageState } from "@/lib/types";

const PENDING_STAGES = [
  { icon: Split, title: "Four-way Verdict" },
];

export function PipelinePanel({
  decompositionState,
  retrievalState,
  nliState,
  graphState,
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
        <span>{recorded ? "4 recorded stages" : "4 live stages"}</span>
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
            <small>04 · {recorded ? "RECORDED" : "DERIVED"}</small>
            <strong>Argumentation Graph</strong>
            <p>
              {graphState === "complete"
                ? `${graphLinkCount} observed NLI link${graphLinkCount === 1 ? "" : "s"} between atoms and evidence.`
                : graphState === "running"
                  ? "Waiting for sentence-level NLI relations."
                  : "Appears after NLI classification completes."}
            </p>
          </span>
          <span className="stage-state">{stateLabel(graphState)}</span>
        </li>

        {PENDING_STAGES.map(({ icon: Icon, title }, index) => (
          <li className="pipeline-stage stage-pending" key={title}>
            <span className="stage-icon">
              <Icon size={19} aria-hidden="true" />
            </span>
            <span className="stage-copy">
                <small>{String(index + 5).padStart(2, "0")} · NEXT</small>
              <strong>{title}</strong>
              <p>
                {title === "Four-way Verdict"
                  ? "Supported, Refuted, Not Enough Evidence, or Conflicting Evidence."
                  : "This stage is reserved for the next implementation milestone."}
              </p>
            </span>
            <span className="stage-state">
              <CircleDashed size={13} aria-hidden="true" /> Pending
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
