import type {
  ArgumentationEdge,
  ArgumentationGraph as ArgumentationGraphModel,
  EvidenceNode,
  GraphWarningCode,
  ObligationEvidenceState,
  VerificationObligationNode,
} from "@/lib/types";

type Position = { x: number; y: number };

/** X is a percentage of canvas width; Y is a pixel offset inside the canvas. */
const CLAIM_Y = 52;
const TIER_GAP = 118;
const ROW_GAP = 112;
const MAX_COLUMNS = 4;
const CANVAS_PADDING = 56;

function columnsFor(count: number): number {
  return Math.max(1, Math.min(count, MAX_COLUMNS));
}

function rowsFor(count: number): number {
  return Math.max(1, Math.ceil(count / columnsFor(count)));
}

/** Lay a tier out in wrapped, centre-justified rows so nodes never overlap. */
function gridPositions(count: number, startY: number): Position[] {
  const columns = columnsFor(count);
  return Array.from({ length: count }, (_, index) => {
    const row = Math.floor(index / columns);
    const inRow = Math.min(columns, count - row * columns);
    const column = index - row * columns;
    return {
      x: ((column + 0.5) / inRow) * 100,
      y: startY + row * ROW_GAP,
    };
  });
}

function edgeLabel(type: ArgumentationEdge["type"]): string {
  return type === "DECOMPOSES_TO" ? "decomposes to" : type === "SUPPORTS" ? "supports" : "attacks";
}

const WARNING_COPY: Record<GraphWarningCode, string> = {
  MISSING_LINGUISTIC_SUMMARY: "Linguistic summaries are missing for some obligations.",
  MISSING_EVIDENCE: "A relation referenced evidence that is no longer retrieved.",
  MISSING_OBLIGATION: "A relation referenced an obligation that is no longer present.",
  DUPLICATE_NODE_ID: "Duplicate graph nodes were discarded.",
  DUPLICATE_EDGE_ID: "Duplicate graph edges were discarded.",
  UNSUPPORTED_NLI_LABEL: "An unrecognised NLI label was skipped.",
  INVALID_SOURCE_OFFSETS: "Some obligation spans no longer align to the claim text.",
  EMPTY_OBLIGATION_TEXT: "An obligation has no display text.",
  AGGREGATION_EDGE_MISMATCH: "The graph and backend aggregation disagree about an argument relation.",
};

/** A curved edge reads far better than a straight line once tiers wrap. */
function edgePath(from: Position, to: Position): string {
  const bend = Math.max(18, Math.abs(to.y - from.y) * 0.42);
  return `M ${from.x} ${from.y} C ${from.x} ${from.y + bend}, ${to.x} ${to.y - bend}, ${to.x} ${to.y}`;
}

export function ArgumentationGraph({
  graph,
  selectedAtomId,
  onSelectAtom,
  onSelectEvidence,
  obligationStates = {},
}: {
  graph: ArgumentationGraphModel;
  selectedAtomId: string | null;
  onSelectAtom: (atomId: string) => void;
  onSelectEvidence: (node: EvidenceNode, atomId: string) => void;
  obligationStates?: Record<string, ObligationEvidenceState>;
}) {
  const claimNode = graph.nodes.find((node) => node.type === "CASE_CLAIM") ?? null;
  const obligations = graph.nodes.filter(
    (node): node is VerificationObligationNode => node.type === "VERIFICATION_OBLIGATION",
  );
  const evidence = graph.nodes.filter((node): node is EvidenceNode => node.type === "EVIDENCE");
  const obligationById = new Map(obligations.map((node) => [node.id, node]));

  const obligationStartY = CLAIM_Y + TIER_GAP;
  const evidenceStartY = obligationStartY + (rowsFor(obligations.length) - 1) * ROW_GAP + TIER_GAP;
  const canvasHeight =
    evidenceStartY + (rowsFor(evidence.length) - 1) * ROW_GAP + CANVAS_PADDING;
  const columns = Math.max(columnsFor(obligations.length), columnsFor(evidence.length));

  const obligationPositions = new Map(
    obligations.map((node, index) => [node.id, gridPositions(obligations.length, obligationStartY)[index]]),
  );
  const evidencePositions = new Map(
    evidence.map((node, index) => [node.id, gridPositions(evidence.length, evidenceStartY)[index]]),
  );
  const argumentEdges = graph.edges.filter((edge) => edge.type !== "DECOMPOSES_TO");

  const positionOf = (id: string): Position | null => {
    if (claimNode?.id === id) return { x: 50, y: CLAIM_Y };
    return obligationPositions.get(id) ?? evidencePositions.get(id) ?? null;
  };
  const edgesForEvidence = (id: string) => argumentEdges.filter((edge) => edge.source === id);
  const edgesForObligation = (id: string) => argumentEdges.filter((edge) => edge.target === id);
  const selectedObligation = obligations.find((node) => node.atomId === selectedAtomId);
  const isActive = (edge: ArgumentationEdge) => !selectedObligation || edge.target === selectedObligation.id;
  const distinctWarnings = [...new Set(graph.warnings.map((item) => item.code))];

  return (
    <section className="argumentation-graph" id="argumentation-graph" aria-labelledby="argumentation-graph-heading">
      <div className="argumentation-heading">
        <div>
          <p className="eyebrow">Stage 04 · Derived</p>
          <h2 id="argumentation-graph-heading">Argumentation Graph</h2>
          <p>Evidence supports or attacks typed verification obligations; this is not a case verdict.</p>
        </div>
        <span>
          {claimNode?.composition ?? "SINGLE"} · {graph.stats.obligationCount} obligation
          {graph.stats.obligationCount === 1 ? "" : "s"}
        </span>
      </div>

      {obligations.length ? <>
        <div
          className="graph-canvas"
          role="group"
          aria-label="Case claim, verification obligations, and evidence relationships"
          style={{ height: `${canvasHeight}px`, ["--graph-columns" as string]: columns }}
        >
          <svg
            className="graph-edges"
            viewBox={`0 0 100 ${canvasHeight}`}
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {graph.edges.map((edge) => {
              const from = positionOf(edge.source);
              const to = positionOf(edge.target);
              if (!from || !to) return null;
              const relationClass = edge.type === "DECOMPOSES_TO" ? "edge-decomposes" : edge.type === "SUPPORTS" ? "edge-support" : "edge-attack";
              return (
                <path
                  key={edge.id}
                  d={edgePath(from, to)}
                  fill="none"
                  className={`graph-edge ${relationClass}${isActive(edge) ? " active" : " dimmed"}`}
                />
              );
            })}
          </svg>

          {claimNode ? (
            <div className="graph-node graph-node-claim" style={{ left: "50%", top: `${CLAIM_Y}px` }} title={claimNode.text}>
              <small>Case claim · {claimNode.composition}</small>
              <p>{claimNode.text}</p>
            </div>
          ) : null}

          {obligations.map((node, index) => {
            const position = obligationPositions.get(node.id);
            if (!position) return null;
            const active = node.atomId === selectedAtomId;
            const relations = edgesForObligation(node.id);
            const supportCount = relations.filter((edge) => edge.type === "SUPPORTS").length;
            const attackCount = relations.filter((edge) => edge.type === "ATTACKS").length;
            const warning = Boolean(node.linguistic?.warnings.length) || node.linguistic?.roleAudit === "MISMATCH";
            const verdictState = obligationStates[node.atomId];
            const role = node.role ?? "CORE";
            return (
              <button
                type="button"
                key={node.id}
                className={`graph-node graph-node-obligation${active ? " active" : ""}${selectedObligation && !active ? " dimmed" : ""}${verdictState ? ` state-${verdictState.toLowerCase()}` : ""}`}
                style={{ left: `${position.x}%`, top: `${position.y}px` }}
                aria-pressed={active}
                aria-label={`Obligation ${index + 1}, ${role}: ${node.text}`}
                title={node.text}
                onClick={() => onSelectAtom(node.atomId)}
              >
                <small>
                  O{index + 1} · {role.replaceAll("_", " ").toLowerCase()}
                  {warning ? <span className="graph-warning-dot" title="Linguistic warning" aria-hidden="true" /> : null}
                </small>
                <p>{node.text}</p>
                <span className="graph-badges">
                  {verdictState ? <em className={`state-badge state-${verdictState.toLowerCase()}`}>{verdictState.toLowerCase()}</em> : null}
                  <em className="edge-badge">{supportCount}↑ {attackCount}↓</em>
                </span>
              </button>
            );
          })}

          {evidence.map((node) => {
            const position = evidencePositions.get(node.id);
            if (!position) return null;
            const relations = edgesForEvidence(node.id);
            const active = !selectedObligation || relations.some((edge) => edge.target === selectedObligation.id);
            const types = new Set(relations.map((edge) => edge.type));
            const relationClass = types.size > 1 ? "mixed" : types.has("ATTACKS") ? "attack" : "support";
            return (
              <button
                type="button"
                key={node.id}
                className={`graph-node graph-node-evidence relation-${relationClass}${active ? " active" : " dimmed"}`}
                style={{ left: `${position.x}%`, top: `${position.y}px` }}
                aria-label={`Evidence from ${node.documentTitle}: ${node.text}. ${relations.map((edge) => `${edgeLabel(edge.type)} obligation ${obligations.findIndex((item) => item.id === edge.target) + 1}`).join("; ")}`}
                title={node.text}
                onClick={() => {
                  const preferred = relations.find((edge) => edge.target === selectedObligation?.id) ?? relations[0];
                  const atomId = preferred ? obligationById.get(preferred.target)?.atomId : selectedAtomId;
                  if (atomId) onSelectEvidence(node, atomId);
                }}
              >
                <small>{node.documentTitle}</small>
                <p>{node.text}</p>
              </button>
            );
          })}
        </div>

        <div className="graph-footer">
          <div className="graph-legend">
            <span className="legend-decomposes">Decomposes to</span>
            <span className="legend-support">Supports</span>
            <span className="legend-attack">Attacks</span>
            <span className="legend-warning">Linguistic warning</span>
          </div>
          <p className="argumentation-note">
            {graph.stats.supportEdgeCount} support · {graph.stats.attackEdgeCount} attack ·{" "}
            {graph.stats.omittedNeutralCount} neutral candidate
            {graph.stats.omittedNeutralCount === 1 ? "" : "s"} left in the evidence pane
          </p>
        </div>
      </> : <p className="argumentation-empty">Decompose a claim to see its argumentation graph.</p>}

      {distinctWarnings.length ? (
        <details className="graph-warnings">
          <summary>{distinctWarnings.length} graph inspection note{distinctWarnings.length === 1 ? "" : "s"}</summary>
          <ul>
            {distinctWarnings.map((code) => (
              <li key={code}>{WARNING_COPY[code] ?? code.replaceAll("_", " ").toLowerCase()}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
