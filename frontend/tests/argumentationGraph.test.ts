import { describe, expect, it } from "vitest";
import { buildArgumentationGraph } from "@/lib/argumentationGraph";
import type { AtomEvidence, AtomSupportClassification, DecomposedAtom, DemoDocument, ObligationLinguisticSummary } from "@/lib/types";

const claim = "Mara joined Orion and became CTO.";
const atoms: DecomposedAtom[] = [
  { id: "atom-1", text: "Mara joined Orion.", sourceText: "Mara joined Orion", start: 0, end: 17, role: "CORE" },
  { id: "atom-2", text: "Mara became CTO.", sourceText: "became CTO", start: 22, end: 32, role: "CORE" },
];
const documents: DemoDocument[] = [
  { id: "doc-1", title: "Source One", url: "https://example.test/one", text: "Mara joined Orion." },
];
const evidence: AtomEvidence[] = [
  { atomId: "atom-1", spans: [{ id: "span-1", documentId: "doc-1", text: "Mara joined Orion.", start: 0, end: 18 }] },
  { atomId: "atom-2", spans: [{ id: "span-1", documentId: "doc-1", text: "Mara joined Orion.", start: 0, end: 18 }] },
];
const classifications: AtomSupportClassification[] = [
  { atomId: "atom-1", relations: [{ spanId: "span-1", documentId: "doc-1", relation: "ENTAILMENT" }] },
  { atomId: "atom-2", relations: [{ spanId: "span-1", documentId: "doc-1", relation: "CONTRADICTION" }] },
];
const summaries: ObligationLinguisticSummary[] = atoms.map((atom) => ({
  atomId: atom.id, analysisStatus: "complete", roleAudit: "MATCH", subjects: [], predicates: [], cueKinds: [], modifierKinds: [], entityLabels: [], warnings: [],
}));

describe("buildArgumentationGraph", () => {
  it("creates a versioned three-tier graph with deduplicated evidence", () => {
    const graph = buildArgumentationGraph("case-1", claim, "AND", atoms, evidence, classifications, documents, summaries);
    expect(graph.schemaVersion).toBe(2);
    expect(graph.nodes.map((node) => node.type)).toEqual(["CASE_CLAIM", "VERIFICATION_OBLIGATION", "VERIFICATION_OBLIGATION", "EVIDENCE"]);
    expect(graph.edges.filter((edge) => edge.type === "DECOMPOSES_TO")).toHaveLength(2);
    expect(graph.edges.filter((edge) => edge.type === "SUPPORTS")).toHaveLength(1);
    expect(graph.edges.filter((edge) => edge.type === "ATTACKS")).toHaveLength(1);
    expect(graph.nodes.filter((node) => node.type === "EVIDENCE")).toHaveLength(1);
    expect(graph.stats).toMatchObject({ obligationCount: 2, evidenceCount: 1, supportEdgeCount: 1, attackEdgeCount: 1 });
  });

  it("omits neutral relations while retaining the obligation", () => {
    const graph = buildArgumentationGraph("case-1", claim, "AND", atoms.slice(0, 1), [{ atomId: "atom-1", spans: [{ id: "neutral", documentId: "doc-1", text: "Unrelated.", start: 0, end: 10 }] }], [{ atomId: "atom-1", relations: [{ spanId: "neutral", documentId: "doc-1", relation: "NEUTRAL" }] }], documents, summaries.slice(0, 1));
    expect(graph.nodes.map((node) => node.type)).toEqual(["CASE_CLAIM", "VERIFICATION_OBLIGATION"]);
    expect(graph.stats.omittedNeutralCount).toBe(1);
    expect(graph.stats.obligationsWithoutArgumentEdges).toBe(1);
  });

  it("records recoverable input inconsistencies without failing construction", () => {
    const graph = buildArgumentationGraph("case-1", claim, "SINGLE", atoms.slice(0, 1), [], [{ atomId: "missing", relations: [{ spanId: "span", documentId: "doc", relation: "ENTAILMENT" }] }], documents);
    expect(graph.warnings.map((item) => item.code)).toContain("MISSING_LINGUISTIC_SUMMARY");
    expect(graph.warnings.map((item) => item.code)).toContain("MISSING_OBLIGATION");
  });
});
