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
import { MAX_EVIDENCE_PER_ATOM, MIN_EVIDENCE_PER_ATOM } from "@/lib/retrieval";

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
  evidencePerAtom,
  onEvidencePerAtomChange,
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
  evidencePerAtom?: number;
  /** Omitted when the budget cannot be changed, as in recorded walkthroughs. */
  onEvidencePerAtomChange?: (value: number) => void;
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
      ? "Auditing the evidence bundle for grounded support and explicit attacks."
      : nliState === "complete"
        ? `${relationCount} grounded relation${relationCount === 1 ? "" : "s"} classified.`
        : nliState === "error"
          ? "Atoms and candidate evidence are preserved. Retry the evidence audit only."
          : retrievalState === "complete"
            ? "Waiting to audit the retrieved candidates."
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
            <strong>Structure the claim</strong>
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
            <strong>Find candidate evidence</strong>
            <p>{retrievalCopy}</p>
            {onEvidencePerAtomChange && evidencePerAtom !== undefined ? (
              <label className="stage-budget">
                <span>Candidates per obligation</span>
                <select
                  name="evidence-per-atom"
                  value={evidencePerAtom}
                  disabled={retrievalState === "running"}
                  onChange={(event) => onEvidencePerAtomChange(Number(event.target.value))}
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
            <strong>Audit grounded evidence</strong>
            <p>{nliCopy}</p>
          </span>
          <span className="stage-actions">
            <span className="stage-state">{stateLabel(nliState)}</span>
            {nliState === "error" ? (
              <button type="button" className="retry-button" onClick={onRetryNli}>
                Retry audit
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
            <strong>Map support and conflict</strong>
            <p>
              {graphState === "complete"
                ? `${graphLinkCount} support or contradiction link${graphLinkCount === 1 ? "" : "s"} ready to inspect.`
                : graphState === "running"
                  ? "Waiting for grounded evidence relations."
                  : "Appears after the evidence audit completes."}
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
            <strong>Apply verdict rules</strong>
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
