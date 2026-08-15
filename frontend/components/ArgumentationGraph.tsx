import type { CSSProperties } from "react";
import type {
  ArgumentationEdge,
  ArgumentationGraph as ArgumentationGraphModel,
  ArgumentationNode,
  NLIRelation,
} from "@/lib/types";

const relationLabels: Record<ArgumentationEdge["relation"], string> = {
  DECOMPOSES: "decomposes",
  ENTAILMENT: "supports",
  CONTRADICTION: "contradicts",
  NEUTRAL: "neither",
};

const relationClasses: Record<ArgumentationEdge["relation"], string> = {
  DECOMPOSES: "graph-edge-decomposes",
  ENTAILMENT: "graph-edge-entailment",
  CONTRADICTION: "graph-edge-contradiction",
  NEUTRAL: "graph-edge-neutral",
};

const relationOrder: NLIRelation[] = ["ENTAILMENT", "CONTRADICTION", "NEUTRAL"];

const GRAPH_WIDTH = 920;
const CLAIM_HEIGHT = 64;
const NODE_WIDTH = 245;
const NODE_HEIGHT = 72;
const ROW_GAP = 16;

function nodeStyle(x: number, y: number): CSSProperties {
  return { left: `${x}px`, top: `${y}px`, width: `${NODE_WIDTH}px` };
}

function edgePath(edge: ArgumentationEdge, positions: Map<string, { x: number; y: number }>) {
  const source = positions.get(edge.source);
  const target = positions.get(edge.target);
  if (!source || !target) return null;
  const sourceX = source.x + NODE_WIDTH;
  const sourceY = source.y + NODE_HEIGHT / 2;
  const targetX = target.x;
  const targetY = target.y + NODE_HEIGHT / 2;
  const control = Math.max(55, Math.abs(targetX - sourceX) * 0.42);
  return `M ${sourceX} ${sourceY} C ${sourceX + control} ${sourceY}, ${targetX - control} ${targetY}, ${targetX} ${targetY}`;
}

function relationCount(graph: ArgumentationGraphModel, relation: NLIRelation): number {
  return graph.edges.filter((edge) => edge.relation === relation).length;
}

export function ArgumentationGraph({
  graph,
  onSelectAtom,
  onSelectEvidence,
}: {
  graph: ArgumentationGraphModel;
  onSelectAtom: (atomId: string) => void;
  onSelectEvidence: (node: ArgumentationNode) => void;
}) {
  const claim = graph.nodes.find((node) => node.kind === "claim");
  const atoms = graph.nodes.filter((node) => node.kind === "atom");
  const evidence = graph.nodes.filter((node) => node.kind === "evidence");
  if (!atoms.length) {
    return <p className="argumentation-empty">The graph appears after claim decomposition.</p>;
  }

  const positions = new Map<string, { x: number; y: number }>();
  if (claim) positions.set(claim.id, { x: (GRAPH_WIDTH - NODE_WIDTH) / 2, y: 12 });
  atoms.forEach((node, index) => positions.set(node.id, { x: 18, y: 112 + index * (NODE_HEIGHT + ROW_GAP) }));
  evidence.forEach((node, index) => positions.set(node.id, { x: 505, y: 112 + index * (NODE_HEIGHT + ROW_GAP) }));
  const height = Math.max(atoms.length, evidence.length, 1) * (NODE_HEIGHT + ROW_GAP) + 132;

  return (
    <section className="argumentation-graph" aria-labelledby="argumentation-graph-heading">
      <div className="argumentation-heading">
        <div>
          <h3 id="argumentation-graph-heading">Argumentation Graph</h3>
          <p>Observed links between atomic claims and candidate evidence.</p>
        </div>
        <span>{graph.edges.filter((edge) => edge.relation !== "DECOMPOSES").length} NLI links</span>
      </div>
      <div className="argumentation-legend" aria-label="Graph relation legend">
        {relationOrder.map((relation) => (
          <span className={relationClasses[relation]} key={relation}>
            <i aria-hidden="true" /> {relationLabels[relation]}
            <strong>{relationCount(graph, relation)}</strong>
          </span>
        ))}
      </div>
      <div className="argumentation-scroll">
        <div className="argumentation-canvas" style={{ height: `${height}px`, width: `${GRAPH_WIDTH}px` }}>
          <svg className="argumentation-edges" viewBox={`0 0 ${GRAPH_WIDTH} ${height}`} aria-hidden="true">
            {graph.edges.map((edge) => {
              const path = edgePath(edge, positions);
              return path ? <path className={relationClasses[edge.relation]} d={path} key={edge.id} /> : null;
            })}
          </svg>
          {claim ? (
            <div
              className="argumentation-node graph-node-claim"
              style={nodeStyle((GRAPH_WIDTH - NODE_WIDTH) / 2, 12)}
            >
              <small>{claim.label}</small>
              <strong>{claim.text}</strong>
            </div>
          ) : null}
          {atoms.map((node, index) => (
            <button
              type="button"
              className="argumentation-node graph-node-atom"
              style={nodeStyle(18, 112 + index * (NODE_HEIGHT + ROW_GAP))}
              onClick={() => onSelectAtom(node.atomId ?? node.id)}
              key={node.id}
              aria-label={`Atomic claim: ${node.text}`}
            >
              <small>{node.label} {index + 1}</small>
              <strong>{node.text}</strong>
            </button>
          ))}
          {evidence.map((node, index) => (
            <button
              type="button"
              className="argumentation-node graph-node-evidence"
              style={nodeStyle(505, 112 + index * (NODE_HEIGHT + ROW_GAP))}
              onClick={() => onSelectEvidence(node)}
              key={node.id}
              aria-label={`Evidence from ${node.label}: ${node.text}`}
            >
              <small>{node.label}</small>
              <strong>{node.text}</strong>
            </button>
          ))}
        </div>
      </div>
      <p className="argumentation-note">NLI links are sentence-level model judgments, not a final case verdict.</p>
    </section>
  );
}
