import type {
  ArgumentationEdge,
  ArgumentationGraph as ArgumentationGraphModel,
  ArgumentationNode,
  NLIRelation,
} from "@/lib/types";

type Position = { x: number; y: number };

const CLAIM_Y = 10;
const ATOM_Y = 50;
const EVIDENCE_Y = 88;

function tierPositions(count: number, y: number): Position[] {
  if (count === 0) return [];
  if (count === 1) return [{ x: 50, y }];
  const inset = 10;
  const span = 100 - inset * 2;
  return Array.from({ length: count }, (_, index) => ({
    x: inset + (span * index) / (count - 1),
    y,
  }));
}

function argumentativeEdges(graph: ArgumentationGraphModel): ArgumentationEdge[] {
  return graph.edges.filter(
    (edge) => edge.relation === "ENTAILMENT" || edge.relation === "CONTRADICTION",
  );
}

function relationVerb(relation: Exclude<NLIRelation, "NEUTRAL">): string {
  return relation === "ENTAILMENT" ? "supports" : "contradicts";
}

export function ArgumentationGraph({
  graph,
  selectedAtomId,
  onSelectAtom,
  onSelectEvidence,
}: {
  graph: ArgumentationGraphModel;
  selectedAtomId: string | null;
  onSelectAtom: (atomId: string) => void;
  onSelectEvidence: (node: ArgumentationNode, atomId: string) => void;
}) {
  const claimNode = graph.nodes.find((node) => node.kind === "claim") ?? null;
  const atomNodes = graph.nodes.filter((node) => node.kind === "atom");
  const evidenceNodes = graph.nodes.filter((node) => node.kind === "evidence");
  const links = argumentativeEdges(graph);

  const atomPositions = new Map(
    atomNodes.map((node, index) => [node.id, tierPositions(atomNodes.length, ATOM_Y)[index]]),
  );
  const evidencePositions = new Map(
    evidenceNodes.map((node, index) => [
      node.id,
      tierPositions(evidenceNodes.length, EVIDENCE_Y)[index],
    ]),
  );
  const atomIndexById = new Map(atomNodes.map((node, index) => [node.id, index + 1]));

  function positionOf(nodeId: string): Position | null {
    if (claimNode && nodeId === claimNode.id) return { x: 50, y: CLAIM_Y };
    return atomPositions.get(nodeId) ?? evidencePositions.get(nodeId) ?? null;
  }

  function evidenceEdges(nodeId: string): ArgumentationEdge[] {
    return links.filter((edge) => edge.target === nodeId);
  }

  function isEdgeActive(edge: ArgumentationEdge): boolean {
    if (!selectedAtomId) return true;
    if (edge.source === selectedAtomId) return true;
    return edge.relation === "DECOMPOSES" && edge.target === selectedAtomId;
  }

  function dominantRelation(rels: ArgumentationEdge[]): "ENTAILMENT" | "CONTRADICTION" | "MIXED" {
    const matching = selectedAtomId
      ? rels.filter((edge) => edge.source === selectedAtomId)
      : rels;
    const pool = matching.length ? matching : rels;
    const relations = new Set(pool.map((edge) => edge.relation));
    if (relations.size === 1) {
      return pool[0].relation === "CONTRADICTION" ? "CONTRADICTION" : "ENTAILMENT";
    }
    return "MIXED";
  }

  function handleEvidenceClick(node: ArgumentationNode): void {
    const rels = evidenceEdges(node.id);
    const preferred = rels.find((edge) => edge.source === selectedAtomId) ?? rels[0];
    onSelectEvidence(node, preferred?.source ?? selectedAtomId ?? "");
  }

  return (
    <section
      className="argumentation-graph"
      id="argumentation-graph"
      aria-labelledby="argumentation-graph-heading"
    >
      <div className="argumentation-heading">
        <div>
          <p className="eyebrow">Stage 04 · Derived</p>
          <h2 id="argumentation-graph-heading">Argumentation Graph</h2>
          <p>See how the claim decomposes and where each atomic claim is supported or contradicted.</p>
        </div>
        <span>{links.length} argumentative link{links.length === 1 ? "" : "s"}</span>
      </div>

      {atomNodes.length ? (
        <>
          <div
            className="graph-canvas"
            role="group"
            aria-label="Claim, atomic claims, and evidence relationships"
          >
            <svg className="graph-edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {graph.edges.map((edge) => {
                const from = positionOf(edge.source);
                const to = positionOf(edge.target);
                if (!from || !to) return null;
                const active = isEdgeActive(edge);
                const relationClass =
                  edge.relation === "DECOMPOSES"
                    ? "edge-decomposes"
                    : edge.relation === "ENTAILMENT"
                      ? "edge-support"
                      : "edge-contradict";
                return (
                  <line
                    key={edge.id}
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    className={`graph-edge ${relationClass}${active ? " active" : " dimmed"}`}
                  />
                );
              })}
            </svg>

            {claimNode ? (
              <div
                className="graph-node graph-node-claim"
                style={{ left: "50%", top: `${CLAIM_Y}%` }}
                title={claimNode.text}
              >
                <small>{claimNode.label}</small>
                <p>{claimNode.text}</p>
              </div>
            ) : null}

            {atomNodes.map((node) => {
              const position = atomPositions.get(node.id);
              if (!position) return null;
              const active = node.id === selectedAtomId;
              const dimmed = Boolean(selectedAtomId) && !active;
              return (
                <button
                  type="button"
                  key={node.id}
                  className={`graph-node graph-node-atom${active ? " active" : ""}${dimmed ? " dimmed" : ""}`}
                  style={{ left: `${position.x}%`, top: `${position.y}%` }}
                  aria-pressed={active}
                  aria-label={`Atom ${atomIndexById.get(node.id)}: ${node.text}`}
                  title={node.text}
                  onClick={() => onSelectAtom(node.atomId ?? node.id)}
                >
                  <small>Atom {atomIndexById.get(node.id)}</small>
                  <p>{node.text}</p>
                </button>
              );
            })}

            {evidenceNodes.map((node) => {
              const position = evidencePositions.get(node.id);
              if (!position) return null;
              const rels = evidenceEdges(node.id);
              const active = Boolean(selectedAtomId) && rels.some((edge) => edge.source === selectedAtomId);
              const dimmed = Boolean(selectedAtomId) && !active;
              const relationClass = dominantRelation(rels).toLowerCase();
              const summary = rels
                .map((edge) => `${relationVerb(edge.relation as Exclude<NLIRelation, "NEUTRAL">)} Atom ${atomIndexById.get(edge.source) ?? "?"}`)
                .join("; ");
              return (
                <button
                  type="button"
                  key={node.id}
                  className={`graph-node graph-node-evidence relation-${relationClass}${active ? " active" : ""}${dimmed ? " dimmed" : ""}`}
                  style={{ left: `${position.x}%`, top: `${position.y}%` }}
                  aria-label={`Evidence from ${node.label}: ${node.text} — ${summary}`}
                  title={node.text}
                  onClick={() => handleEvidenceClick(node)}
                >
                  <small>{node.label}</small>
                  <p>{node.text}</p>
                </button>
              );
            })}
          </div>

          <div className="graph-legend" aria-hidden="true">
            <span className="legend-decomposes">Decomposes</span>
            <span className="legend-support">Supports</span>
            <span className="legend-contradict">Contradicts</span>
          </div>
        </>
      ) : (
        <p className="argumentation-empty">Decompose a claim to see its argumentation graph.</p>
      )}

      <p className="argumentation-note">
        These are sentence-level NLI judgments, not a case verdict. Neutral candidates remain in the evidence pane.
      </p>
    </section>
  );
}
