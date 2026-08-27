import type {
  ArgumentationEdge,
  ArgumentationGraph,
  AtomEvidence,
  AtomSupportClassification,
  ClaimComposition,
  DecomposedAtom,
  DemoDocument,
  EvidenceNode,
  GraphWarning,
  ObligationLinguisticSummary,
  VerificationObligationNode,
} from "./types";

function warning(code: GraphWarning["code"], message: string): GraphWarning {
  return { code, message };
}

function evidenceKey(documentId: string, spanId: string): string {
  return `${documentId}:${spanId}`;
}

export function buildArgumentationGraph(
  claimId: string,
  claim: string,
  composition: ClaimComposition,
  atoms: DecomposedAtom[],
  evidence: AtomEvidence[],
  classifications: AtomSupportClassification[],
  documents: DemoDocument[],
  summaries: ObligationLinguisticSummary[] = [],
  authoritativeArgumentEdgeIds?: ReadonlySet<string>,
): ArgumentationGraph {
  const warnings: GraphWarning[] = [];
  const nodes: ArgumentationGraph["nodes"] = [];
  const edges: ArgumentationEdge[] = [];
  const claimedNodeIds = new Set<string>();
  const claimedEdgeIds = new Set<string>();
  const addNode = (node: ArgumentationGraph["nodes"][number]) => {
    if (claimedNodeIds.has(node.id)) {
      warnings.push(warning("DUPLICATE_NODE_ID", `Duplicate graph node ID: ${node.id}.`));
      return false;
    }
    claimedNodeIds.add(node.id);
    nodes.push(node);
    return true;
  };
  const addEdge = (edge: ArgumentationEdge) => {
    if (claimedEdgeIds.has(edge.id)) {
      warnings.push(warning("DUPLICATE_EDGE_ID", `Duplicate graph edge ID: ${edge.id}.`));
      return;
    }
    claimedEdgeIds.add(edge.id);
    edges.push(edge);
  };

  const normalizedClaimId = claimId.trim() || "custom";
  const claimNodeId = `claim:${normalizedClaimId}`;
  addNode({ id: claimNodeId, type: "CASE_CLAIM", text: claim, composition });

  const summariesByAtomId = new Map(summaries.map((summary) => [summary.atomId, summary]));
  const obligationByAtomId = new Map<string, VerificationObligationNode>();
  atoms.forEach((atom) => {
    const node: VerificationObligationNode = {
      id: `obligation:${normalizedClaimId}:${atom.id}`,
      type: "VERIFICATION_OBLIGATION",
      atomId: atom.id,
      text: atom.text,
      role: atom.role,
      sourceText: atom.sourceText,
      start: atom.start,
      end: atom.end,
      linguistic: summariesByAtomId.get(atom.id),
    };
    if (!atom.text.trim()) warnings.push(warning("EMPTY_OBLIGATION_TEXT", `Atom ${atom.id} has no display text.`));
    if (atom.start < 0 || atom.end <= atom.start || claim.slice(atom.start, atom.end) !== atom.sourceText) {
      warnings.push(warning("INVALID_SOURCE_OFFSETS", `Atom ${atom.id} has invalid source offsets.`));
    }
    if (!node.linguistic) warnings.push(warning("MISSING_LINGUISTIC_SUMMARY", `Atom ${atom.id} has no linguistic summary.`));
    if (addNode(node)) {
      obligationByAtomId.set(atom.id, node);
      addEdge({
        id: `edge:DECOMPOSES_TO:${claimNodeId}:${node.id}`,
        source: claimNodeId,
        target: node.id,
        type: "DECOMPOSES_TO",
      });
    }
  });

  const documentsById = new Map(documents.map((document, index) => [document.id, { document, index }]));
  const spansByKey = new Map<string, { span: AtomEvidence["spans"][number]; rank: number }>();
  evidence.forEach((group) => group.spans.forEach((span, index) => {
    const key = evidenceKey(span.documentId, span.id);
    const existing = spansByKey.get(key);
    if (!existing || index + 1 < existing.rank) spansByKey.set(key, { span, rank: index + 1 });
  }));

  const evidenceNodes = new Map<string, EvidenceNode>();
  const observedArgumentEdgeIds = new Set<string>();
  let omittedNeutralCount = 0;
  classifications.forEach((classification) => {
    const obligation = obligationByAtomId.get(classification.atomId);
    classification.relations.forEach((relation) => {
      if (relation.relation === "NEUTRAL") {
        omittedNeutralCount += 1;
        return;
      }
      if (relation.relation !== "ENTAILMENT" && relation.relation !== "CONTRADICTION") {
        warnings.push(warning("UNSUPPORTED_NLI_LABEL", `Unsupported NLI label for ${classification.atomId}.`));
        return;
      }
      if (!obligation) {
        warnings.push(warning("MISSING_OBLIGATION", `NLI relation references unknown atom ${classification.atomId}.`));
        return;
      }
      const key = evidenceKey(relation.documentId, relation.spanId);
      const spanRecord = spansByKey.get(key);
      if (!spanRecord) {
        warnings.push(warning("MISSING_EVIDENCE", `NLI relation references unknown evidence ${key}.`));
        return;
      }
      let evidenceNode = evidenceNodes.get(key);
      if (!evidenceNode) {
        const documentRecord = documentsById.get(spanRecord.span.documentId);
        evidenceNode = {
          id: `evidence:${spanRecord.span.documentId}:${spanRecord.span.id}`,
          type: "EVIDENCE",
          evidenceId: spanRecord.span.id,
          documentId: spanRecord.span.documentId,
          documentTitle: documentRecord?.document.title ?? spanRecord.span.documentId,
          documentUrl: documentRecord?.document.url ?? "",
          text: spanRecord.span.text,
          start: spanRecord.span.start,
          end: spanRecord.span.end,
          bestRank: spanRecord.rank,
        };
        evidenceNodes.set(key, evidenceNode);
      }
      const edgeType = relation.relation === "ENTAILMENT" ? "SUPPORTS" : "ATTACKS";
      const edgeId = `edge:${edgeType}:${evidenceNode.id}:${obligation.id}`;
      observedArgumentEdgeIds.add(edgeId);
      if (authoritativeArgumentEdgeIds && !authoritativeArgumentEdgeIds.has(edgeId)) {
        warnings.push(warning("AGGREGATION_EDGE_MISMATCH", `The backend did not accept graph relation ${edgeId}.`));
        return;
      }
      addEdge({
        id: edgeId,
        source: evidenceNode.id,
        target: obligation.id,
        type: edgeType,
        nli: { label: relation.relation },
      });
    });
  });
  if (authoritativeArgumentEdgeIds) {
    authoritativeArgumentEdgeIds.forEach((edgeId) => {
      if (!observedArgumentEdgeIds.has(edgeId)) {
        warnings.push(warning("AGGREGATION_EDGE_MISMATCH", `The backend accepted relation ${edgeId}, but it is absent from the graph inputs.`));
      }
    });
  }

  const sortedEvidence = [...evidenceNodes.values()].sort((left, right) => {
    const leftDocument = documentsById.get(left.documentId)?.index ?? Number.MAX_SAFE_INTEGER;
    const rightDocument = documentsById.get(right.documentId)?.index ?? Number.MAX_SAFE_INTEGER;
    return leftDocument - rightDocument || left.start - right.start || left.id.localeCompare(right.id);
  });
  sortedEvidence.forEach(addNode);

  const atomOrder = new Map(atoms.map((atom, index) => [atom.id, index]));
  const atomIdByObligationNodeId = new Map(
    [...obligationByAtomId.values()].map((node) => [node.id, node.atomId]),
  );
  edges.sort((left, right) => {
    const leftStructural = left.type === "DECOMPOSES_TO";
    const rightStructural = right.type === "DECOMPOSES_TO";
    if (leftStructural !== rightStructural) return leftStructural ? -1 : 1;
    const leftAtomId = atomIdByObligationNodeId.get(left.target);
    const rightAtomId = atomIdByObligationNodeId.get(right.target);
    return (atomOrder.get(leftAtomId ?? "") ?? Number.MAX_SAFE_INTEGER)
      - (atomOrder.get(rightAtomId ?? "") ?? Number.MAX_SAFE_INTEGER)
      || left.type.localeCompare(right.type)
      || left.id.localeCompare(right.id);
  });
  const argumentEdges = edges.filter((edge) => edge.type !== "DECOMPOSES_TO");
  const connectedAtoms = new Set(argumentEdges.map((edge) => edge.target));
  return {
    schemaVersion: 2,
    claimId: normalizedClaimId,
    nodes,
    edges,
    warnings,
    stats: {
      obligationCount: obligationByAtomId.size,
      evidenceCount: sortedEvidence.length,
      supportEdgeCount: argumentEdges.filter((edge) => edge.type === "SUPPORTS").length,
      attackEdgeCount: argumentEdges.filter((edge) => edge.type === "ATTACKS").length,
      omittedNeutralCount,
      obligationsWithoutArgumentEdges: [...obligationByAtomId.values()].filter((node) => !connectedAtoms.has(node.id)).length,
    },
  };
}
