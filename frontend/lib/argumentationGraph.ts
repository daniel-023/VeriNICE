import type {
  ArgumentationEdge, ArgumentationGraph, AtomEvidence, AtomEvidenceAssessment,
  ClaimComposition, DecomposedAtom, DemoDocument, EvidenceNode, GraphWarning,
  SymbolicExecution, VerificationObligationNode,
} from "./types";

const warning = (code: GraphWarning["code"], message: string): GraphWarning => ({ code, message });
const evidenceKey = (documentId: string, spanId: string) => `${documentId}:${spanId}`;

export function buildArgumentationGraph(
  claimId: string,
  claim: string,
  composition: ClaimComposition,
  atoms: DecomposedAtom[],
  evidence: AtomEvidence[],
  assessments: AtomEvidenceAssessment[],
  documents: DemoDocument[],
  reasoning: SymbolicExecution[] = [],
  authoritativeArgumentEdgeIds?: ReadonlySet<string>,
): ArgumentationGraph {
  const warnings: GraphWarning[] = [];
  const nodes: ArgumentationGraph["nodes"] = [];
  const edges: ArgumentationEdge[] = [];
  const nodeIds = new Set<string>();
  const edgeIds = new Set<string>();
  const addNode = (node: ArgumentationGraph["nodes"][number]) => {
    if (nodeIds.has(node.id)) return false;
    nodeIds.add(node.id); nodes.push(node); return true;
  };
  const addEdge = (edge: ArgumentationEdge) => {
    if (edgeIds.has(edge.id)) return;
    edgeIds.add(edge.id); edges.push(edge);
  };
  const normalizedClaimId = claimId.trim() || "custom";
  const claimNodeId = `claim:${normalizedClaimId}`;
  addNode({ id: claimNodeId, type: "CASE_CLAIM", text: claim, composition });
  const obligations = new Map<string, VerificationObligationNode>();
  atoms.forEach((atom) => {
    const node: VerificationObligationNode = {
      id: `obligation:${normalizedClaimId}:${atom.id}`, type: "VERIFICATION_OBLIGATION",
      atomId: atom.id, text: atom.text, role: atom.role, sourceText: atom.sourceText,
      start: atom.start, end: atom.end,
    };
    if (claim.slice(atom.start, atom.end) !== atom.sourceText) warnings.push(warning("INVALID_SOURCE_OFFSETS", `Atom ${atom.id} has invalid source offsets.`));
    addNode(node); obligations.set(atom.id, node);
    addEdge({ id: `edge:DECOMPOSES_TO:${claimNodeId}:${node.id}`, source: claimNodeId, target: node.id, type: "DECOMPOSES_TO" });
  });

  const docs = new Map(documents.map((item, index) => [item.id, { item, index }]));
  const spans = new Map<string, { span: AtomEvidence["spans"][number]; rank: number }>();
  evidence.forEach((group) => group.spans.forEach((span, rank) => {
    const key = evidenceKey(span.documentId, span.id);
    const current = spans.get(key);
    if (!current || rank + 1 < current.rank) spans.set(key, { span, rank: rank + 1 });
  }));
  const evidenceNodes = new Map<string, EvidenceNode>();
  const ensureEvidence = (documentId: string, spanId: string): EvidenceNode | null => {
    const key = evidenceKey(documentId, spanId);
    const existing = evidenceNodes.get(key);
    if (existing) return existing;
    const record = spans.get(key);
    if (!record) return null;
    const document = docs.get(documentId)?.item;
    const node: EvidenceNode = {
      id: `evidence:${documentId}:${spanId}`, type: "EVIDENCE", evidenceId: spanId,
      documentId, documentTitle: document?.title ?? documentId, documentUrl: document?.url ?? "",
      text: record.span.text, start: record.span.start, end: record.span.end,
      bestRank: record.rank, contextSpans: record.span.contextSpans,
    };
    evidenceNodes.set(key, node); addNode(node);
    (record.span.contextSpans ?? []).forEach((context) => {
      const contextId = `context:${documentId}:${context.id}`;
      addNode({ id: contextId, type: "CONTEXT", evidenceId: context.id, documentId, text: context.text, start: context.start, end: context.end });
      addEdge({ id: `edge:CONTEXTUALIZES:${contextId}:${node.id}`, source: contextId, target: node.id, type: "CONTEXTUALIZES" });
    });
    return node;
  };

  let omittedCandidateCount = 0;
  assessments.forEach((assessment) => {
    const obligation = obligations.get(assessment.atomId);
    if (!obligation) { warnings.push(warning("MISSING_OBLIGATION", `Assessment references unknown atom ${assessment.atomId}.`)); return; }
    (["SUPPORTS", "REFUTES"] as const).forEach((relation) => {
      const selected = assessment.relations.filter((item) => item.relation === relation && item.decisive);
      if (selected.length >= 2) {
        const inferenceId = `inference:bundle:${assessment.atomId}:${relation.toLowerCase()}`;
        addNode({
          id: inferenceId, type: "INFERENCE", atomId: assessment.atomId,
          inferenceKind: "EVIDENCE_BUNDLE", expression: `${selected.length} source sentences considered jointly`,
          conclusion: relation === "SUPPORTS" ? "The evidence bundle supports this atomic claim." : "The evidence bundle refutes this atomic claim.",
          explanation: "These source sentences were assessed together as one evidence bundle.",
          premiseIds: selected.map((item) => item.spanId), relation, compiledBy: "Qwen",
        });
        selected.forEach((item) => {
          const node = ensureEvidence(item.documentId, item.spanId);
          if (node) addEdge({ id: `edge:REQUIRES:${node.id}:${inferenceId}`, source: node.id, target: inferenceId, type: "REQUIRES" });
        });
        addEdge({ id: `edge:${relation}:${inferenceId}:${obligation.id}`, source: inferenceId, target: obligation.id, type: relation, assessed: true });
      } else if (selected.length === 1) {
        const item = selected[0];
        const node = ensureEvidence(item.documentId, item.spanId);
        if (node) addEdge({ id: `edge:${relation}:${node.id}:${obligation.id}`, source: node.id, target: obligation.id, type: relation, assessed: true });
      }
    });
    const contextual = assessment.relations.filter((item) => item.relation === "CONTEXT");
    const anchors = assessment.relations.filter((item) =>
      (item.relation === "SUPPORTS" || item.relation === "REFUTES") && item.decisive
    );
    contextual.forEach((item) => {
      const anchor = anchors.map((candidate) => ensureEvidence(candidate.documentId, candidate.spanId)).find(Boolean);
      const record = spans.get(evidenceKey(item.documentId, item.spanId));
      if (record && anchor) {
        const contextId = `context:selected:${item.documentId}:${item.spanId}`;
        addNode({
          id: contextId, type: "CONTEXT", evidenceId: item.spanId,
          documentId: item.documentId, text: record.span.text,
          start: record.span.start, end: record.span.end,
        });
        addEdge({ id: `edge:CONTEXTUALIZES:${contextId}:${anchor.id}`, source: contextId, target: anchor.id, type: "CONTEXTUALIZES" });
      }
    });
    omittedCandidateCount += assessment.relations.filter((item) => item.relation === "NOT_SELECTED").length;
  });

  reasoning.forEach((proof) => {
    const obligation = obligations.get(proof.atomId);
    if (!obligation) return;
    const nodeId = `inference:${proof.id}`;
    addNode({
      id: nodeId, type: "INFERENCE", atomId: proof.atomId, inferenceKind: proof.operator,
      expression: proof.expression, conclusion: proof.conclusion, explanation: proof.explanation,
      premiseIds: proof.premiseIds, relation: proof.relation,
      compiledBy: "Qwen", executedBy: "Python",
      status: proof.status,
    });
    proof.premises.forEach((premise) => {
      let source = premise.kind === "EVIDENCE"
        ? (() => {
            const match = [...spans.values()].find(({ span }) =>
              span.documentId === premise.documentId
              && span.start === premise.start
              && span.end === premise.end
              && span.text === premise.text,
            );
            return match ? ensureEvidence(match.span.documentId, match.span.id) : null;
          })()
        : null;
      if (!source) {
        const document = docs.get(premise.documentId)?.item;
        const enclosingSpan = premise.kind === "LIST_CERTIFICATE"
          ? [...spans.values()]
              .filter(({ span }) => (
                span.documentId === premise.documentId
                && span.start <= premise.start
                && span.end >= premise.end
              ))
              .sort((left, right) => (
                (left.span.end - left.span.start) - (right.span.end - right.span.start)
              ))[0]?.span
          : undefined;
        source = {
          id: `evidence:premise:${premise.id}`, type: "EVIDENCE", evidenceId: premise.id,
          documentId: premise.documentId, documentTitle: document?.title ?? premise.documentId,
          documentUrl: document?.url ?? "", text: premise.text, start: premise.start,
          end: premise.end, bestRank: Number.MAX_SAFE_INTEGER,
          listItems: premise.listItems,
          // Older recorded walkthroughs predate structured list items. Their
          // enclosing retrieved span is still exact source text and avoids a
          // heading-only node without re-parsing source lists in the browser.
          displayText: premise.listItems?.length ? undefined : enclosingSpan?.text,
        };
        if (!nodeIds.has(source.id)) addNode(source);
      }
      addEdge({ id: `edge:REQUIRES:${source.id}:${nodeId}`, source: source.id, target: nodeId, type: "REQUIRES" });
    });
    if (proof.relation) {
      addEdge({ id: `edge:${proof.relation}:${nodeId}:${obligation.id}`, source: nodeId, target: obligation.id, type: proof.relation });
    }
  });

  const observedArgumentEdges = edges.filter((item) => item.type === "SUPPORTS" || item.type === "REFUTES");
  const rejectedEdgeIds = new Set<string>();
  if (authoritativeArgumentEdgeIds) {
    observedArgumentEdges.forEach((edge) => {
      if (!authoritativeArgumentEdgeIds.has(edge.id)) {
        rejectedEdgeIds.add(edge.id);
        warnings.push(warning("AGGREGATION_EDGE_MISMATCH", `Backend aggregation did not accept ${edge.id}.`));
      }
    });
  }
  const renderedEdges = edges.filter((edge) => !rejectedEdgeIds.has(edge.id));
  const argumentEdges = renderedEdges.filter((item) => item.type === "SUPPORTS" || item.type === "REFUTES");
  const connected = new Set(argumentEdges.map((edge) => edge.target));
  return {
    schemaVersion: 4, claimId: normalizedClaimId, nodes, edges: renderedEdges, warnings,
    stats: {
      obligationCount: obligations.size,
      evidenceCount: nodes.filter((item) => item.type === "EVIDENCE").length,
      inferenceCount: nodes.filter((item) => item.type === "INFERENCE").length,
      contextCount: nodes.filter((item) => item.type === "CONTEXT").length,
      supportEdgeCount: argumentEdges.filter((item) => item.type === "SUPPORTS").length,
      refuteEdgeCount: argumentEdges.filter((item) => item.type === "REFUTES").length,
      unselectedCandidateCount: omittedCandidateCount,
      obligationsWithoutArgumentEdges: [...obligations.values()].filter((item) => !connected.has(item.id)).length,
    },
  };
}
