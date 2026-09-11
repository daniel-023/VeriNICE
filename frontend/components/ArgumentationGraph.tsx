"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type {
  ArgumentationEdge,
  ArgumentationGraph as ArgumentationGraphModel,
  EvidenceNode,
  GraphWarningCode,
  InferenceNode,
  ObligationEvidenceState,
  StageState,
  VerdictAggregationResult,
  VerificationObligationNode,
} from "@/lib/types";

type Relation = "SUPPORTS" | "REFUTES";

interface ReasoningPath {
  id: string;
  kind: "ASSESSMENT" | "RULE";
  relation: Relation;
  evidence: EvidenceNode[];
  inference: InferenceNode | null;
}

interface ReasoningLane {
  obligation: VerificationObligationNode;
  paths: ReasoningPath[];
}

interface DisplayEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  relation?: Relation;
}

interface DrawnEdge extends DisplayEdge {
  path: string;
  labelX: number;
  labelY: number;
  markerEnd?: boolean;
}

const WARNING_COPY: Record<GraphWarningCode, string> = {
  MISSING_EVIDENCE: "A relation referenced evidence that is no longer retrieved.",
  MISSING_OBLIGATION: "A relation referenced an atomic claim that is no longer present.",
  DUPLICATE_NODE_ID: "Duplicate graph nodes were discarded.",
  DUPLICATE_EDGE_ID: "Duplicate graph edges were discarded.",
  UNSUPPORTED_RELATION: "An unrecognised evidence relation was skipped.",
  INVALID_SOURCE_OFFSETS: "Some atomic-claim spans no longer align to the claim text.",
  EMPTY_OBLIGATION_TEXT: "An atomic claim has no display text.",
  AGGREGATION_EDGE_MISMATCH: "The graph and verdict aggregation disagree about an evidence relation.",
};

const COMPOSITION_RULE: Record<string, string> = {
  SINGLE: "The atomic claim determines the verdict.",
  AND: "Every atomic claim must be supported; 1 refuted atom refutes the full claim.",
  OR: "1 supported atom supports the full claim; every atom must be refuted to refute it.",
};

const RULE_LABELS: Record<string, string> = {
  SET_MEMBERSHIP: "Set membership",
  NUMERIC_COMPARE: "Numeric comparison",
  TEMPORAL_COMPARE: "Temporal comparison",
  ATTRIBUTE_COMPARE: "Attribute comparison",
  COUNT_DISTINCT: "Distinct-value count",
  EXTREMUM_COMPARE: "Extremum comparison",
};

function display(value: string): string {
  return value.replaceAll("_", " ");
}

function verdictClass(verdict: string): string {
  return `verdict-${verdict.toLowerCase().replaceAll("_", "-")}`;
}

function uniqueEvidence(nodes: EvidenceNode[]): EvidenceNode[] {
  const seen = new Set<string>();
  return nodes.filter((node) => {
    if (seen.has(node.id)) return false;
    seen.add(node.id);
    return true;
  });
}

/** Convert graph-v4 storage nodes into the paths used by the presentation layer. */
function presentationLanes(graph: ArgumentationGraphModel): ReasoningLane[] {
  const obligations = graph.nodes.filter(
    (node): node is VerificationObligationNode => node.type === "VERIFICATION_OBLIGATION",
  );
  const evidenceById = new Map(
    graph.nodes.filter((node): node is EvidenceNode => node.type === "EVIDENCE").map((node) => [node.id, node]),
  );
  const inferenceById = new Map(
    graph.nodes.filter((node): node is InferenceNode => node.type === "INFERENCE").map((node) => [node.id, node]),
  );

  return obligations.map((obligation) => {
    const paths = graph.edges
      .filter((edge): edge is ArgumentationEdge & { type: Relation } => (
        edge.target === obligation.id && (edge.type === "SUPPORTS" || edge.type === "REFUTES")
      ))
      .flatMap((edge): ReasoningPath[] => {
        const directEvidence = evidenceById.get(edge.source);
        if (directEvidence) {
          return [{ id: edge.id, kind: "ASSESSMENT", relation: edge.type, evidence: [directEvidence], inference: null }];
        }

        const inference = inferenceById.get(edge.source);
        if (!inference) return [];
        if (inference.inferenceKind !== "EVIDENCE_BUNDLE" && inference.status !== "PROVED" && inference.status !== "DISPROVED") return [];
        const premises = graph.edges
          .filter((candidate) => candidate.type === "REQUIRES" && candidate.target === inference.id)
          .map((candidate) => evidenceById.get(candidate.source))
          .filter((node): node is EvidenceNode => Boolean(node));
        return [{
          id: edge.id,
          kind: inference.inferenceKind === "EVIDENCE_BUNDLE" ? "ASSESSMENT" : "RULE",
          relation: edge.type,
          evidence: uniqueEvidence(premises),
          inference,
        }];
      });
    return { obligation, paths };
  });
}

function relationCounts(graph: ArgumentationGraphModel, obligationId?: string) {
  const inferenceById = new Map(
    graph.nodes.filter((node): node is InferenceNode => node.type === "INFERENCE").map((node) => [node.id, node]),
  );
  const evidenceIds = new Set(graph.nodes.filter((node) => node.type === "EVIDENCE").map((node) => node.id));
  return graph.edges
    .filter((edge) => (
      (edge.type === "SUPPORTS" || edge.type === "REFUTES") && (!obligationId || edge.target === obligationId)
    ))
    .reduce((counts, edge) => {
      const inference = inferenceById.get(edge.source);
      const contribution = inference?.inferenceKind === "EVIDENCE_BUNDLE"
        ? Math.max(1, graph.edges.filter((candidate) => (
            candidate.type === "REQUIRES" && candidate.target === inference.id && evidenceIds.has(candidate.source)
          )).length)
        : 1;
      counts[edge.type === "SUPPORTS" ? "support" : "refute"] += contribution;
      return counts;
    }, { support: 0, refute: 0 });
}

function roleLabel(role?: string): string {
  return display(role ?? "CORE").toLowerCase();
}

function ruleLabel(path: ReasoningPath, obligation: VerificationObligationNode): string {
  const kind = path.inference?.inferenceKind ?? "SYMBOLIC_RULE";
  if (kind === "ATTRIBUTE_COMPARE" && /\b(?:located|location)\b/i.test(obligation.text)) {
    return "Location comparison";
  }
  return RULE_LABELS[kind] ?? display(kind).toLowerCase();
}

function hasProcessNode(path: ReasoningPath): boolean {
  return path.kind === "RULE" || path.inference !== null;
}

function displayEdges(lanes: ReasoningLane[], composition: string): DisplayEdge[] {
  const edges: DisplayEdge[] = [];
  lanes.forEach(({ obligation, paths }) => {
    edges.push({ id: `decompose:${obligation.atomId}`, source: "claim", target: `atom:${obligation.atomId}`, label: "decomposes to" });
    paths.forEach((path) => {
      edges.push({
        id: `evidence:${path.id}`,
        source: `atom:${obligation.atomId}`,
        target: `evidence:${path.id}`,
        label: "checked against",
      });
      if (hasProcessNode(path)) {
        edges.push({
          id: `process:${path.id}`,
          source: `evidence:${path.id}`,
          target: `process:${path.id}`,
          label: path.kind === "RULE" ? "used by" : "assessed",
        });
      }
      edges.push({
        id: `relation:${path.id}`,
        source: hasProcessNode(path) ? `process:${path.id}` : `evidence:${path.id}`,
        target: `result:${obligation.atomId}`,
        label: path.relation === "SUPPORTS" ? "supports" : "refutes",
        relation: path.relation,
      });
    });
    if (!paths.length) {
      edges.push({ id: `empty:${obligation.atomId}`, source: `atom:${obligation.atomId}`, target: `empty:${obligation.atomId}`, label: "checked against" });
      edges.push({ id: `unresolved:${obligation.atomId}`, source: `empty:${obligation.atomId}`, target: `result:${obligation.atomId}`, label: "unresolved" });
    }
    edges.push({
      id: `aggregate:${obligation.atomId}`,
      source: `result:${obligation.atomId}`,
      target: composition === "SINGLE" ? "verdict" : "composition",
      label: composition === "SINGLE" ? "determines" : "contributes",
    });
  });
  if (composition !== "SINGLE") {
    edges.push({ id: "verdict", source: "composition", target: "verdict", label: "determines" });
  }
  return edges;
}

function hierarchicalPath(from: DOMRect, to: DOMRect, root: DOMRect) {
  const x1 = from.left - root.left + from.width / 2;
  const y1 = from.bottom - root.top;
  const x2 = to.left - root.left + to.width / 2;
  const y2 = to.top - root.top;
  const terminalY = Math.max(y1, y2 - 12);
  const middleY = y1 + (terminalY - y1) / 2;

  // The diagram has a strict top-to-bottom hierarchy. Keeping every edge on
  // the same bottom-to-top route prevents structural links from changing to
  // side-entry curves as node widths or lane counts change.
  return {
    path: `M ${x1} ${y1} C ${x1} ${middleY}, ${x2} ${middleY}, ${x2} ${terminalY} L ${x2} ${y2}`,
    labelX: (x1 + x2) / 2,
    labelY: middleY - 4,
  };
}

function routedEdges(edges: DisplayEdge[], nodes: Map<string, DOMRect>, root: DOMRect): DrawnEdge[] {
  const decompositionEdges = edges.filter((edge) => edge.id.startsWith("decompose:"));
  const contributionEdges = edges.filter((edge) => edge.id.startsWith("aggregate:") && edge.target === "composition");
  const evidenceSplits = new Map<string, DisplayEdge[]>();
  const relationMerges = new Map<string, DisplayEdge[]>();
  const relationsByTarget = new Map<string, DisplayEdge[]>();
  edges.forEach((edge) => {
    if (edge.id.startsWith("evidence:")) {
      evidenceSplits.set(edge.source, [...(evidenceSplits.get(edge.source) ?? []), edge]);
    }
    if (edge.id.startsWith("relation:")) {
      const key = `${edge.target}:${edge.relation ?? "NEUTRAL"}`;
      relationMerges.set(key, [...(relationMerges.get(key) ?? []), edge]);
      relationsByTarget.set(edge.target, [...(relationsByTarget.get(edge.target) ?? []), edge]);
    }
  });

  // When support and refutation converge on one result, join the coloured
  // branches before a single neutral arrow. Two arrowheads at the same target
  // overlap, while separate target anchors make the connecting curves look
  // unrelated even though they jointly determine the conflicting state.
  const mixedRelationFanIns = [...relationsByTarget.values()].filter((group) => (
    group.length > 1 && new Set(group.map((edge) => edge.relation)).size > 1
  ));
  const mixedRelationIds = new Set(mixedRelationFanIns.flat().map((edge) => edge.id));

  const splitGroups = [
    ...(decompositionEdges.length > 1 ? [decompositionEdges] : []),
    ...[...evidenceSplits.values()].filter((group) => group.length > 1),
  ];
  const mergeGroups = [
    ...(contributionEdges.length > 1 ? [contributionEdges] : []),
    ...[...relationMerges.values()].filter((group) => (
      group.length > 1 && group.every((edge) => !mixedRelationIds.has(edge.id))
    )),
  ];
  const groupedIds = new Set(
    [...splitGroups.flat(), ...mergeGroups.flat(), ...mixedRelationFanIns.flat()]
      .map((edge) => edge.id),
  );
  const routed = edges.flatMap((edge): DrawnEdge[] => {
    if (groupedIds.has(edge.id)) return [];
    const source = nodes.get(edge.source);
    const target = nodes.get(edge.target);
    return source && target ? [{ ...edge, ...hierarchicalPath(source, target, root) }] : [];
  });

  splitGroups.forEach((group, groupIndex) => {
    const source = nodes.get(group[0].source);
    const targets = group
      .map((edge) => ({ edge, rect: nodes.get(edge.target) }))
      .filter((item): item is { edge: DisplayEdge; rect: DOMRect } => Boolean(item.rect));
    if (source && targets.length) {
      const sourceX = source.left - root.left + source.width / 2;
      const sourceY = source.bottom - root.top;
      const targetTop = Math.min(...targets.map(({ rect }) => rect.top - root.top));
      const splitY = sourceY + Math.max(16, (targetTop - sourceY) * .5);
      const targetXs = targets.map(({ rect }) => rect.left - root.left + rect.width / 2);
      routed.push({
        id: `split:${groupIndex}:trunk`,
        source: group[0].source,
        target: `split:${groupIndex}:junction`,
        label: group[0].label,
        path: `M ${sourceX} ${sourceY} L ${sourceX} ${splitY}`,
        labelX: sourceX,
        labelY: sourceY + (splitY - sourceY) / 2 + 3,
        markerEnd: false,
      });
      routed.push({
        id: `split:${groupIndex}:rail`,
        source: `split:${groupIndex}:junction`,
        target: `split:${groupIndex}:branches`,
        label: "",
        path: `M ${Math.min(sourceX, ...targetXs)} ${splitY} L ${Math.max(sourceX, ...targetXs)} ${splitY}`,
        labelX: sourceX,
        labelY: splitY,
        markerEnd: false,
      });
      targets.forEach(({ edge, rect }) => {
        const targetX = rect.left - root.left + rect.width / 2;
        const targetY = rect.top - root.top;
        routed.push({
          ...edge,
          label: "",
          path: `M ${targetX} ${splitY} L ${targetX} ${targetY}`,
          labelX: targetX,
          labelY: splitY + (targetY - splitY) / 2,
        });
      });
    }
  });

  mixedRelationFanIns.forEach((group) => {
    const target = nodes.get(group[0].target);
    const sources = group
      .map((edge) => ({ edge, rect: nodes.get(edge.source) }))
      .filter((item): item is { edge: DisplayEdge; rect: DOMRect } => Boolean(item.rect))
      .sort((left, right) => left.rect.left - right.rect.left);
    if (!target || !sources.length) return;
    const targetCenterX = target.left - root.left + target.width / 2;
    const targetY = target.top - root.top;
    const junctionY = targetY - 14;
    sources.forEach(({ edge, rect }) => {
      const sourceX = rect.left - root.left + rect.width / 2;
      const sourceY = rect.bottom - root.top;
      const middleY = sourceY + (junctionY - sourceY) / 2;
      routed.push({
        ...edge,
        path: `M ${sourceX} ${sourceY} C ${sourceX} ${middleY}, ${targetCenterX} ${middleY}, ${targetCenterX} ${junctionY}`,
        labelX: (sourceX + targetCenterX) / 2,
        labelY: middleY - 4,
        markerEnd: false,
      });
    });
    routed.push({
      id: `mixed-relation:${group[0].target}:trunk`,
      source: `mixed-relation:${group[0].target}:junction`,
      target: group[0].target,
      label: "",
      path: `M ${targetCenterX} ${junctionY} L ${targetCenterX} ${targetY}`,
      labelX: targetCenterX,
      labelY: junctionY,
    });
  });

  mergeGroups.forEach((group, groupIndex) => {
    const target = nodes.get(group[0].target);
    const sources = group
      .map((edge) => ({ edge, rect: nodes.get(edge.source) }))
      .filter((item): item is { edge: DisplayEdge; rect: DOMRect } => Boolean(item.rect));
    if (target && sources.length) {
      const targetX = target.left - root.left + target.width / 2;
      const targetY = target.top - root.top;
      const highestSourceBottom = Math.max(...sources.map(({ rect }) => rect.bottom - root.top));
      const mergeY = targetY - Math.max(16, (targetY - highestSourceBottom) * .5);
      const sourceXs = sources.map(({ rect }) => rect.left - root.left + rect.width / 2);
      sources.forEach(({ edge, rect }) => {
        const sourceX = rect.left - root.left + rect.width / 2;
        const sourceY = rect.bottom - root.top;
        routed.push({
          ...edge,
          label: "",
          path: `M ${sourceX} ${sourceY} L ${sourceX} ${mergeY}`,
          labelX: sourceX,
          labelY: sourceY + (mergeY - sourceY) / 2,
          markerEnd: false,
        });
      });
      routed.push({
        id: `merge:${groupIndex}:rail`,
        source: `merge:${groupIndex}:branches`,
        target: `merge:${groupIndex}:junction`,
        label: "",
        path: `M ${Math.min(targetX, ...sourceXs)} ${mergeY} L ${Math.max(targetX, ...sourceXs)} ${mergeY}`,
        labelX: targetX,
        labelY: mergeY,
        markerEnd: false,
      });
      routed.push({
        id: `merge:${groupIndex}:trunk`,
        source: `merge:${groupIndex}:junction`,
        target: group[0].target,
        label: group[0].label,
        relation: group[0].relation,
        path: `M ${targetX} ${mergeY} L ${targetX} ${targetY}`,
        labelX: targetX,
        labelY: mergeY + (targetY - mergeY) / 2 + 3,
      });
    }
  });

  return routed;
}

export function ArgumentationGraph({
  graph,
  selectedAtomId,
  onSelectAtom,
  onSelectEvidence,
  onSelectInference,
  obligationStates = {},
  verdict = null,
  verdictState = "idle",
}: {
  graph: ArgumentationGraphModel;
  selectedAtomId: string | null;
  onSelectAtom: (atomId: string) => void;
  onSelectEvidence: (node: EvidenceNode, atomId: string) => void;
  onSelectInference?: (node: InferenceNode, premises: EvidenceNode[]) => void;
  obligationStates?: Record<string, ObligationEvidenceState>;
  verdict?: VerdictAggregationResult | null;
  verdictState?: StageState;
}) {
  const graphRef = useRef<HTMLDivElement>(null);
  const [drawnEdges, setDrawnEdges] = useState<DrawnEdge[]>([]);
  const claimNode = graph.nodes.find((node) => node.type === "CASE_CLAIM") ?? null;
  const lanes = useMemo(() => presentationLanes(graph), [graph]);
  const composition = claimNode?.composition ?? "SINGLE";
  const total = relationCounts(graph);
  const distinctWarnings = [...new Set(graph.warnings.map((item) => item.code))];

  useEffect(() => {
    const root = graphRef.current;
    if (!root) return;
    let frame = 0;
    const edges = displayEdges(lanes, composition);
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rootRect = root.getBoundingClientRect();
        const nodes = new Map<string, DOMRect>();
        root.querySelectorAll<HTMLElement>("[data-graph-node]").forEach((element) => {
          const id = element.dataset.graphNode;
          if (id) nodes.set(id, element.getBoundingClientRect());
        });
        setDrawnEdges(routedEdges(edges, nodes, rootRect));
      });
    };
    update();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(root);
    root.querySelectorAll<HTMLElement>("[data-graph-node]").forEach((element) => observer?.observe(element));
    window.addEventListener("resize", update);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [lanes, composition]);

  return (
    <section className="argumentation-graph" id="reasoning-graph" aria-labelledby="reasoning-graph-heading">
      <div className="argumentation-heading">
        <div>
          <p className="eyebrow">Stage 04–05</p>
          <h2 id="reasoning-graph-heading">Reasoning Graph</h2>
          <p>How decisive source evidence leads to the verdict.</p>
        </div>
        <span>{composition} · {graph.stats.obligationCount} atomic claim{graph.stats.obligationCount === 1 ? "" : "s"}</span>
      </div>

      {lanes.length ? (
        <div className="logic-graph" ref={graphRef} aria-label="Claim-to-verdict reasoning graph">
          <svg className="logic-edge-layer" aria-hidden="true">
            <defs>
              <marker id="logic-arrow-neutral" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" />
              </marker>
              <marker id="logic-arrow-support" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" />
              </marker>
              <marker id="logic-arrow-refute" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" />
              </marker>
            </defs>
            {drawnEdges.map((edge) => (
              <g className={`logic-edge-group${edge.relation ? ` relation-${edge.relation.toLowerCase()}` : ""}`} key={edge.id}>
                <path
                  className="logic-edge"
                  d={edge.path}
                  markerEnd={edge.markerEnd === false
                    ? undefined
                    : `url(#logic-arrow-${edge.relation === "SUPPORTS" ? "support" : edge.relation === "REFUTES" ? "refute" : "neutral"})`}
                />
                {edge.label ? <text className="logic-edge-label" x={edge.labelX} y={edge.labelY} textAnchor="middle">{edge.label}</text> : null}
              </g>
            ))}
          </svg>

          <div className="logic-claim-node" data-graph-node="claim">
            <small>Claim · {composition}</small>
            <strong>{claimNode?.text}</strong>
          </div>

          <div className={`logic-branches${lanes.length > 1 ? " multiple" : ""}`}>
            {lanes.map(({ obligation, paths }, laneIndex) => {
              const active = obligation.atomId === selectedAtomId;
              return (
                <article className={`logic-branch${active ? " active" : ""}`} key={obligation.id} aria-labelledby={`reasoning-atom-${obligation.atomId}`}>
                  <button
                    type="button"
                    id={`reasoning-atom-${obligation.atomId}`}
                    className="logic-atom-node"
                    data-graph-node={`atom:${obligation.atomId}`}
                    aria-pressed={active}
                    aria-label={`Select atomic claim ${laneIndex + 1}: ${obligation.text}`}
                    onClick={() => onSelectAtom(obligation.atomId)}
                    title={obligation.text}
                  >
                    <small>Atomic Claim O{laneIndex + 1} · {roleLabel(obligation.role)}</small>
                    <strong>{obligation.text}</strong>
                  </button>

                  <div className={`logic-paths${paths.length > 1 ? " multiple" : ""}`}>
                    {paths.length ? paths.map((path) => (
                      <div className="logic-path" key={path.id}>
                        <div
                          className={`logic-evidence-group ${path.kind === "RULE" ? "rule-premise" : `relation-${path.relation.toLowerCase()}`}`}
                          data-graph-node={`evidence:${path.id}`}
                        >
                          <div className="logic-evidence-group-heading">
                            <small>{path.kind === "RULE" ? "Rule premises" : "Selected evidence"}</small>
                            <span>{path.evidence.length} {path.kind === "RULE"
                              ? `premise${path.evidence.length === 1 ? "" : "s"}`
                              : `sentence${path.evidence.length === 1 ? "" : "s"}`}</span>
                          </div>
                          {path.evidence.length ? path.evidence.map((node) => (
                            <button
                              type="button"
                              className="logic-evidence-node logic-evidence-item"
                              key={node.id}
                              onClick={() => onSelectEvidence(node, obligation.atomId)}
                              aria-label={`Open evidence from ${node.documentTitle}: ${node.listItems?.length
                                ? `${node.text}${node.listItems.map((item) => item.text).join(", ")}`
                                : node.displayText ?? node.text}`}
                              title={node.displayText ?? node.text}
                            >
                              <small>{node.documentTitle}</small>
                              {node.listItems?.length ? (
                                <div className="logic-grounded-list">
                                  <span>{node.text.trim()}</span>
                                  <ul aria-label={`${node.listItems.length} grounded list items`}>
                                    {node.listItems.map((item) => <li key={item.id}>{item.text}</li>)}
                                  </ul>
                                </div>
                              ) : <span>{node.displayText ?? node.text}</span>}
                            </button>
                          )) : <span className="logic-empty-node">No grounded premise</span>}
                        </div>

                        {hasProcessNode(path) ? (
                          <button
                            type="button"
                            className={`logic-inference-node relation-${path.relation.toLowerCase()}`}
                            data-graph-node={`process:${path.id}`}
                            onClick={() => {
                              if (path.inference && onSelectInference) onSelectInference(path.inference, path.evidence);
                              else onSelectAtom(obligation.atomId);
                            }}
                            aria-label={path.kind === "RULE"
                              ? `${ruleLabel(path, obligation)} ${path.inference?.status?.toLowerCase()}`
                              : `Joint evidence assessment ${path.relation.toLowerCase()}`}
                          >
                            <small>{path.kind === "RULE" ? "Symbolic rule" : "Evidence bundle"}</small>
                            <strong>{path.kind === "RULE" ? ruleLabel(path, obligation) : "Joint assessment"}</strong>
                            {path.kind === "RULE" ? <span>{path.inference?.expression}</span> : null}
                          </button>
                        ) : null}
                      </div>
                    )) : (
                      <div className="logic-empty-node" data-graph-node={`empty:${obligation.atomId}`}>
                        <small>Evidence</small><strong>No decisive evidence</strong>
                      </div>
                    )}
                  </div>

                  <div
                    className={`logic-atom-result state-${(obligationStates[obligation.atomId] ?? "UNRESOLVED").toLowerCase()}`}
                    data-graph-node={`result:${obligation.atomId}`}
                  >
                    <strong>Atomic result · O{laneIndex + 1}</strong>
                    <span>{display(obligationStates[obligation.atomId] ?? "UNRESOLVED")}</span>
                  </div>

                </article>
              );
            })}
          </div>

          <div className={`logic-terminal${composition === "SINGLE" ? " single" : ""}`} id="case-verdict">
            {composition !== "SINGLE" ? <div className="logic-composition-node" data-graph-node="composition">
              <small>Composition · {composition}</small>
              <strong>{COMPOSITION_RULE[composition]}</strong>
              <span>{lanes.map(({ obligation }, index) => `O${index + 1} ${display(obligationStates[obligation.atomId] ?? "UNRESOLVED").toLowerCase()}`).join(" · ")}</span>
            </div> : null}
            <div className={`logic-verdict-node${verdict ? ` ${verdictClass(verdict.verdict)}` : ""}`} data-graph-node="verdict" aria-live="polite">
              <small>Verdict{composition === "SINGLE" ? " · Single claim" : ""}</small>
              <strong>{verdict ? display(verdict.verdict) : verdictState === "running" ? "Calculating…" : "Pending"}</strong>
            </div>
          </div>

        </div>
      ) : <p className="argumentation-empty">The reasoning graph will appear after decomposition.</p>}

      <div className="graph-footer">
        <div className="graph-legend" aria-label="Relation legend">
          <span className="legend-support">Supports</span>
          <span className="legend-refute">Refutes</span>
        </div>
        <p className="argumentation-note">Total · {total.support} support · {total.refute} refute</p>
      </div>

      {distinctWarnings.length ? (
        <details className="graph-warnings">
          <summary>{distinctWarnings.length} graph note{distinctWarnings.length === 1 ? "" : "s"}</summary>
          <ul>{distinctWarnings.map((code) => <li key={code}>{WARNING_COPY[code]}</li>)}</ul>
        </details>
      ) : null}
    </section>
  );
}
