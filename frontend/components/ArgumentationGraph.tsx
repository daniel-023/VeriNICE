import type {
  ArgumentationEdge,
  ArgumentationGraph as ArgumentationGraphModel,
  EvidenceNode,
  ObligationEvidenceState,
  VerificationObligationNode,
} from "@/lib/types";

type Position = { x: number; y: number };
const CLAIM_Y = 10;
const OBLIGATION_Y = 50;
const EVIDENCE_Y = 88;

function tierPositions(count: number, y: number): Position[] {
  if (count === 1) return [{ x: 50, y }];
  const inset = 10;
  return Array.from({ length: count }, (_, index) => ({
    x: inset + ((100 - inset * 2) * index) / Math.max(count - 1, 1),
    y,
  }));
}

function edgeLabel(type: ArgumentationEdge["type"]): string {
  return type === "DECOMPOSES_TO" ? "decomposes to" : type === "SUPPORTS" ? "supports" : "attacks";
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
  const evidencePositions = new Map(evidence.map((node, index) => [node.id, tierPositions(evidence.length, EVIDENCE_Y)[index]]));
  const obligationPositions = new Map(obligations.map((node, index) => [node.id, tierPositions(obligations.length, OBLIGATION_Y)[index]]));
  const argumentEdges = graph.edges.filter((edge) => edge.type !== "DECOMPOSES_TO");

  const positionOf = (id: string): Position | null => {
    if (claimNode?.id === id) return { x: 50, y: CLAIM_Y };
    return obligationPositions.get(id) ?? evidencePositions.get(id) ?? null;
  };
  const edgesForEvidence = (id: string) => argumentEdges.filter((edge) => edge.source === id);
  const edgesForObligation = (id: string) => argumentEdges.filter((edge) => edge.target === id);
  const selectedObligation = obligations.find((node) => node.atomId === selectedAtomId);
  const isActive = (edge: ArgumentationEdge) => !selectedObligation || edge.target === selectedObligation.id;

  return (
    <section className="argumentation-graph" id="argumentation-graph" aria-labelledby="argumentation-graph-heading">
      <div className="argumentation-heading">
        <div>
          <p className="eyebrow">Stage 04 · Derived</p>
          <h2 id="argumentation-graph-heading">Argumentation Graph</h2>
          <p>Evidence supports or attacks typed verification obligations; this is not a case verdict.</p>
        </div>
        <span>{graph.stats.supportEdgeCount + graph.stats.attackEdgeCount} argument links</span>
      </div>
      <div className="graph-stats" aria-label="Graph statistics">
        <span>{claimNode?.composition ?? "SINGLE"} · {graph.stats.obligationCount} obligations</span>
        <span>{graph.stats.supportEdgeCount} support · {graph.stats.attackEdgeCount} attack · {graph.stats.omittedNeutralCount} neutral omitted</span>
      </div>

      {obligations.length ? <>
        <div className="graph-canvas" role="group" aria-label="Case claim, verification obligations, and evidence relationships">
          <svg className="graph-edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {graph.edges.map((edge) => {
              const from = positionOf(edge.source);
              const to = positionOf(edge.target);
              if (!from || !to) return null;
              const relationClass = edge.type === "DECOMPOSES_TO" ? "edge-decomposes" : edge.type === "SUPPORTS" ? "edge-support" : "edge-attack";
              return <line key={edge.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={`graph-edge ${relationClass}${isActive(edge) ? " active" : " dimmed"}`} />;
            })}
          </svg>
          {claimNode ? <div className="graph-node graph-node-claim" style={{ left: "50%", top: `${CLAIM_Y}%` }} title={claimNode.text}>
            <small>Case claim · {claimNode.composition}</small><p>{claimNode.text}</p>
          </div> : null}
          {obligations.map((node, index) => {
            const position = obligationPositions.get(node.id);
            if (!position) return null;
            const active = node.atomId === selectedAtomId;
            const edgeCount = edgesForObligation(node.id);
            const cues = node.linguistic?.cueKinds.filter((cue) => ["numeric", "temporal", "modality", "attribution"].includes(cue)) ?? [];
            const warning = node.linguistic?.warnings.length || node.linguistic?.roleAudit === "MISMATCH";
            const verdictState = obligationStates[node.atomId];
            return <button type="button" key={node.id} className={`graph-node graph-node-obligation${active ? " active" : ""}${selectedObligation && !active ? " dimmed" : ""}${warning ? " warning" : ""}`} style={{ left: `${position.x}%`, top: `${position.y}%` }} aria-pressed={active} aria-label={`Obligation ${index + 1}, ${node.role}: ${node.text}`} title={node.text} onClick={() => onSelectAtom(node.atomId)}>
              <small>O{index + 1} · {node.role}</small><p>{node.text}</p>
              <span className="graph-badges">{cues.map((cue) => <em key={cue}>{cue}</em>)}{verdictState ? <em>{verdictState.toLowerCase()}</em> : null}{warning ? <em className="warning-badge">warning</em> : null}<em>{edgeCount.filter((edge) => edge.type === "SUPPORTS").length}↑ {edgeCount.filter((edge) => edge.type === "ATTACKS").length}↓</em></span>
            </button>;
          })}
          {evidence.map((node) => {
            const position = evidencePositions.get(node.id);
            if (!position) return null;
            const relations = edgesForEvidence(node.id);
            const active = !selectedObligation || relations.some((edge) => edge.target === selectedObligation.id);
            const types = new Set(relations.map((edge) => edge.type));
            const relationClass = types.size > 1 ? "mixed" : types.has("ATTACKS") ? "attack" : "support";
            return <button type="button" key={node.id} className={`graph-node graph-node-evidence relation-${relationClass}${active ? " active" : " dimmed"}`} style={{ left: `${position.x}%`, top: `${position.y}%` }} aria-label={`Evidence from ${node.documentTitle}: ${node.text}. ${relations.map((edge) => `${edgeLabel(edge.type)} obligation ${obligations.findIndex((item) => item.id === edge.target) + 1}`).join("; ")}`} title={node.text} onClick={() => {
              const preferred = relations.find((edge) => edge.target === selectedObligation?.id) ?? relations[0];
              const atomId = preferred ? obligationById.get(preferred.target)?.atomId : selectedAtomId;
              if (atomId) onSelectEvidence(node, atomId);
            }}>
              <small>{node.documentTitle} · rank {node.bestRank}</small><p>{node.text}</p>
            </button>;
          })}
        </div>
        <div className="graph-legend"><span className="legend-decomposes">Decomposes to</span><span className="legend-support">Supports</span><span className="legend-attack">Attacks</span><span className="legend-warning">Linguistic warning</span></div>
      </> : <p className="argumentation-empty">Decompose a claim to see its argumentation graph.</p>}
      {graph.warnings.length ? <p className="argumentation-note">Graph warnings: {graph.warnings.map((item) => item.code).join(", ")}</p> : null}
      <p className="argumentation-note">Neutral candidates remain in the evidence pane and do not create graph edges.</p>
    </section>
  );
}
