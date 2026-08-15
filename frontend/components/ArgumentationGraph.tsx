import type {
  ArgumentationEdge,
  ArgumentationGraph as ArgumentationGraphModel,
  ArgumentationNode,
  NLIRelation,
} from "@/lib/types";

const relationLabels: Record<Exclude<NLIRelation, "NEUTRAL">, string> = {
  ENTAILMENT: "Supports Atom",
  CONTRADICTION: "Contradicts Atom",
};

function argumentativeEdges(graph: ArgumentationGraphModel): ArgumentationEdge[] {
  return graph.edges.filter(
    (edge) => edge.relation === "ENTAILMENT" || edge.relation === "CONTRADICTION",
  );
}

function EvidenceGroup({
  relation,
  nodes,
  atomId,
  onSelectEvidence,
}: {
  relation: Exclude<NLIRelation, "NEUTRAL">;
  nodes: ArgumentationNode[];
  atomId: string;
  onSelectEvidence: (node: ArgumentationNode, atomId: string) => void;
}) {
  const label = relationLabels[relation];
  return (
    <section className={`argumentation-relation relation-${relation.toLowerCase()}`}>
      <h3>
        <span aria-hidden="true" /> {label}
        <strong>{nodes.length}</strong>
      </h3>
      {nodes.length ? (
        <ul aria-label={`${label} evidence`}>
          {nodes.map((node) => (
            <li key={`${relation}-${node.id}`}>
              <button
                type="button"
                className="argumentation-evidence-node"
                onClick={() => onSelectEvidence(node, atomId)}
                aria-label={`${label}, from ${node.label}: ${node.text}`}
              >
                <small>{node.label}</small>
                <span>{node.text}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p>No sentence has this relation to the selected atom.</p>
      )}
    </section>
  );
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
  const claim = graph.nodes.find((node) => node.kind === "claim");
  const atoms = graph.nodes.filter((node) => node.kind === "atom");
  const evidenceById = new Map(
    graph.nodes.filter((node) => node.kind === "evidence").map((node) => [node.id, node]),
  );
  const edges = argumentativeEdges(graph);
  const selectedAtom = atoms.find((node) => node.id === selectedAtomId) ?? null;
  const selectedEdges = selectedAtom
    ? edges.filter((edge) => edge.source === selectedAtom.id)
    : [];
  const relationNodes = (relation: Exclude<NLIRelation, "NEUTRAL">) =>
    selectedEdges
      .filter((edge) => edge.relation === relation)
      .map((edge) => evidenceById.get(edge.target))
      .filter((node): node is ArgumentationNode => Boolean(node));

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
          <p>Inspect support and contradiction links for one atomic claim at a time.</p>
        </div>
        <span>{edges.length} argumentative link{edges.length === 1 ? "" : "s"}</span>
      </div>

      <nav className="argumentation-atom-selector" aria-label="Atomic claims in argumentation graph">
        {atoms.map((atom, index) => (
          <button
            type="button"
            className={atom.id === selectedAtomId ? "active" : undefined}
            aria-pressed={atom.id === selectedAtomId}
            onClick={() => onSelectAtom(atom.atomId ?? atom.id)}
            key={atom.id}
          >
            Atom {index + 1}
          </button>
        ))}
      </nav>

      {selectedAtom ? (
        <div className="argumentation-path">
          {claim ? (
            <article className="argumentation-claim-node">
              <small>{claim.label}</small>
              <p>{claim.text}</p>
            </article>
          ) : null}
          <div className="argumentation-connector" aria-hidden="true">
            <span>Decomposes To</span>
          </div>
          <article className="argumentation-atom-node">
            <small>Selected Atomic Claim</small>
            <p>{selectedAtom.text}</p>
          </article>
          <div className="argumentation-relations">
            <EvidenceGroup
              relation="ENTAILMENT"
              nodes={relationNodes("ENTAILMENT")}
              atomId={selectedAtom.id}
              onSelectEvidence={onSelectEvidence}
            />
            <EvidenceGroup
              relation="CONTRADICTION"
              nodes={relationNodes("CONTRADICTION")}
              atomId={selectedAtom.id}
              onSelectEvidence={onSelectEvidence}
            />
          </div>
        </div>
      ) : (
        <p className="argumentation-empty">Select an atomic claim to inspect its argumentative links.</p>
      )}

      <p className="argumentation-note">
        These are sentence-level NLI judgments, not a case verdict. Neutral candidates remain in the evidence pane.
      </p>
    </section>
  );
}
