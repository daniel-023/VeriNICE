import type {
  ArgumentationGraph,
  ArgumentationNode,
  AtomEvidence,
  AtomSupportClassification,
  DecomposedAtom,
  DemoDocument,
} from "./types";

export function buildArgumentationGraph(
  claim: string,
  atoms: DecomposedAtom[],
  evidence: AtomEvidence[],
  classifications: AtomSupportClassification[],
  documents: DemoDocument[],
): ArgumentationGraph {
  const nodes: ArgumentationNode[] = [];
  const edges: ArgumentationGraph["edges"] = [];
  const documentTitles = new Map(documents.map((document) => [document.id, document.title]));
  const spansByKey = new Map<string, AtomEvidence["spans"][number]>(
    evidence.flatMap((item) =>
      item.spans.map((span) => [`${span.documentId}:${span.id}`, span] as const),
    ),
  );
  const evidenceByKey = new Map<string, ArgumentationNode>();

  if (claim.trim()) {
    nodes.push({ id: "claim", kind: "claim", label: "Original claim", text: claim });
  }

  atoms.forEach((atom) => {
    nodes.push({ id: atom.id, kind: "atom", label: "Atomic claim", text: atom.text, atomId: atom.id });
    if (claim.trim()) {
      edges.push({ id: `claim-${atom.id}`, source: "claim", target: atom.id, relation: "DECOMPOSES" });
    }
  });

  classifications.forEach((classification) => {
    classification.relations.forEach((relation) => {
      // Neutral means no argumentative relation. It remains visible in the
      // evidence pane but does not become an edge or node in this graph.
      if (relation.relation === "NEUTRAL") return;
      const key = `${relation.documentId}:${relation.spanId}`;
      const span = spansByKey.get(key);
      if (!span) return;
      let evidenceNode = evidenceByKey.get(key);
      if (!evidenceNode) {
        evidenceNode = {
          id: `evidence-${key}`,
          kind: "evidence",
          label: documentTitles.get(span.documentId) ?? span.documentId,
          text: span.text,
          documentId: span.documentId,
          spanId: span.id,
          atomIds: [classification.atomId],
        };
        evidenceByKey.set(key, evidenceNode);
        nodes.push(evidenceNode);
      } else if (!evidenceNode.atomIds?.includes(classification.atomId)) {
        evidenceNode.atomIds = [...(evidenceNode.atomIds ?? []), classification.atomId];
      }
      edges.push({
        id: `${classification.atomId}-${relation.documentId}-${relation.spanId}-${relation.relation}`,
        source: classification.atomId,
        target: evidenceNode.id,
        relation: relation.relation,
      });
    });
  });

  return { nodes, edges };
}
