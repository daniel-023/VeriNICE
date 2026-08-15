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

  evidence.forEach((atomEvidence) => {
    atomEvidence.spans.forEach((span) => {
      const key = `${span.documentId}:${span.id}`;
      const existing = evidenceByKey.get(key);
      if (existing) {
        existing.atomIds = [...(existing.atomIds ?? []), atomEvidence.atomId];
        return;
      }
      const node: ArgumentationNode = {
        id: `evidence-${key}`,
        kind: "evidence",
        label: documentTitles.get(span.documentId) ?? span.documentId,
        text: span.text,
        documentId: span.documentId,
        spanId: span.id,
        atomIds: [atomEvidence.atomId],
      };
      evidenceByKey.set(key, node);
      nodes.push(node);
    });
  });

  const evidenceNodeByKey = new Map(
    [...evidenceByKey.entries()].map(([key, node]) => [key, node.id]),
  );
  classifications.forEach((classification) => {
    classification.relations.forEach((relation) => {
      const evidenceNodeId = evidenceNodeByKey.get(`${relation.documentId}:${relation.spanId}`);
      if (!evidenceNodeId) return;
      edges.push({
        id: `${classification.atomId}-${relation.documentId}-${relation.spanId}-${relation.relation}`,
        source: classification.atomId,
        target: evidenceNodeId,
        relation: relation.relation,
      });
    });
  });

  return { nodes, edges };
}
