import { describe, expect, it } from "vitest";
import { buildArgumentationGraph } from "@/lib/argumentationGraph";
import type { AtomEvidence, AtomEvidenceAssessment, DecomposedAtom, DemoDocument } from "@/lib/types";

const claim = "Mara joined Orion and became CTO.";
const atoms: DecomposedAtom[] = [
  { id: "atom-1", text: "Mara joined Orion.", sourceText: "Mara joined Orion", start: 0, end: 17, role: "CORE" },
  { id: "atom-2", text: "Mara became CTO.", sourceText: "became CTO", start: 22, end: 32, role: "CORE" },
];
const documents: DemoDocument[] = [
  { id: "doc-1", title: "Source One", url: "https://example.test/one", text: "Mara joined Orion.", layout: "PROSE" },
];
const evidence: AtomEvidence[] = [
  { atomId: "atom-1", spans: [{ id: "span-1", documentId: "doc-1", text: "Mara joined Orion.", start: 0, end: 18 }] },
  { atomId: "atom-2", spans: [{ id: "span-1", documentId: "doc-1", text: "Mara joined Orion.", start: 0, end: 18 }] },
];
const classifications: AtomEvidenceAssessment[] = [
  { atomId: "atom-1", relations: [{ spanId: "span-1", documentId: "doc-1", relation: "SUPPORTS", decisive: true }] },
  { atomId: "atom-2", relations: [{ spanId: "span-1", documentId: "doc-1", relation: "REFUTES", decisive: true }] },
];

describe("buildArgumentationGraph", () => {
  it("creates a versioned three-tier graph with deduplicated evidence", () => {
    const graph = buildArgumentationGraph("case-1", claim, "AND", atoms, evidence, classifications, documents);
    expect(graph.schemaVersion).toBe(4);
    expect(graph.nodes.map((node) => node.type)).toEqual(["CASE_CLAIM", "VERIFICATION_OBLIGATION", "VERIFICATION_OBLIGATION", "EVIDENCE"]);
    expect(graph.edges.filter((edge) => edge.type === "DECOMPOSES_TO")).toHaveLength(2);
    expect(graph.edges.filter((edge) => edge.type === "SUPPORTS")).toHaveLength(1);
    expect(graph.edges.filter((edge) => edge.type === "REFUTES")).toHaveLength(1);
    expect(graph.nodes.filter((node) => node.type === "EVIDENCE")).toHaveLength(1);
    expect(graph.stats).toMatchObject({ obligationCount: 2, evidenceCount: 1, supportEdgeCount: 1, refuteEdgeCount: 1 });
  });

  it("omits unselected candidates while retaining the obligation", () => {
    const graph = buildArgumentationGraph("case-1", claim, "AND", atoms.slice(0, 1), [{ atomId: "atom-1", spans: [{ id: "unselected", documentId: "doc-1", text: "Unrelated.", start: 0, end: 10 }] }], [{ atomId: "atom-1", relations: [{ spanId: "unselected", documentId: "doc-1", relation: "NOT_SELECTED", decisive: false }] }], documents);
    expect(graph.nodes.map((node) => node.type)).toEqual(["CASE_CLAIM", "VERIFICATION_OBLIGATION"]);
    expect(graph.stats.unselectedCandidateCount).toBe(1);
    expect(graph.stats.obligationsWithoutArgumentEdges).toBe(1);
  });

  it("records recoverable input inconsistencies without failing construction", () => {
    const graph = buildArgumentationGraph("case-1", claim, "SINGLE", atoms.slice(0, 1), [], [{ atomId: "missing", relations: [{ spanId: "span", documentId: "doc", relation: "SUPPORTS", decisive: true }] }], documents);
    expect(graph.warnings.map((item) => item.code)).toContain("MISSING_OBLIGATION");
  });

  it("renders only the argument relations accepted by backend aggregation", () => {
    const accepted = new Set(["edge:SUPPORTS:evidence:doc-1:span-1:obligation:case-1:atom-1"]);
    const graph = buildArgumentationGraph("case-1", claim, "AND", atoms, evidence, classifications, documents, [], accepted);
    expect(graph.edges.filter((edge) => edge.type === "SUPPORTS")).toHaveLength(1);
    expect(graph.edges.filter((edge) => edge.type === "REFUTES")).toHaveLength(0);
    expect(graph.warnings.map((item) => item.code)).toContain("AGGREGATION_EDGE_MISMATCH");
  });

  it("keeps a complete source list inside one certificate node", () => {
    const listText = "Three members: Alpha, Beta, and Gamma.";
    const listDocument = { ...documents[0], text: listText };
    const listEvidence = [{
      atomId: "atom-1",
      spans: [{ id: "list-span", documentId: "doc-1", text: listText, start: 0, end: listText.length }],
    }];
    const graph = buildArgumentationGraph(
      "list-case", claim, "SINGLE", atoms.slice(0, 1), listEvidence,
      [{ atomId: "atom-1", relations: [] }], [listDocument], [{
        id: "proof-list", atomId: "atom-1", operator: "SET_MEMBERSHIP", status: "DISPROVED",
        relation: "REFUTES", premiseIds: ["certificate"], premises: [{
          id: "certificate", documentId: "doc-1", text: "Three members: ", start: 0, end: 15,
          kind: "LIST_CERTIFICATE", contentHash: "hash", itemCount: 3,
          listItems: [
            { id: "item-1", documentId: "doc-1", text: "Alpha", start: 15, end: 20, contentHash: "hash" },
            { id: "item-2", documentId: "doc-1", text: "Beta", start: 22, end: 26, contentHash: "hash" },
            { id: "item-3", documentId: "doc-1", text: "Gamma", start: 32, end: 37, contentHash: "hash" },
          ],
        }], expression: "Delta ∈ source list", conclusion: "Delta is absent.", explanation: "Complete list.",
        validationWarnings: [], program: {
          version: 1, outputStepId: "result", steps: [{
            id: "result", operation: "MEMBER", inputIds: ["certificate"], outputType: "BOOLEAN",
            description: "Check membership.",
          }],
        },
      }],
    );
    const certificate = graph.nodes.find((node) => node.type === "EVIDENCE" && node.evidenceId === "certificate");
    expect(certificate?.type === "EVIDENCE" ? certificate.listItems?.map((item) => item.text) : []).toEqual([
      "Alpha", "Beta", "Gamma",
    ]);
  });
});
