import { describe, expect, it } from "vitest";
import { buildArgumentationGraph } from "@/lib/argumentationGraph";
import type { AtomEvidence, AtomSupportClassification, DecomposedAtom, DemoDocument } from "@/lib/types";

const atoms: DecomposedAtom[] = [
  { id: "atom-1", text: "Mara joined Orion.", sourceText: "Mara joined Orion.", start: 0, end: 19 },
  { id: "atom-2", text: "Mara became CTO.", sourceText: "Mara became CTO.", start: 20, end: 36 },
];

const documents: DemoDocument[] = [
  { id: "doc-1", title: "Source One", url: "https://example.test/one", text: "Mara joined Orion." },
];

const evidence: AtomEvidence[] = [
  { atomId: "atom-1", spans: [
    { id: "span-1", documentId: "doc-1", text: "Mara joined Orion.", start: 0, end: 18 },
    { id: "span-neutral", documentId: "doc-1", text: "Orion issued a report.", start: 19, end: 41 },
  ] },
  { atomId: "atom-2", spans: [{ id: "span-1", documentId: "doc-1", text: "Mara joined Orion.", start: 0, end: 18 }] },
];

const classifications: AtomSupportClassification[] = [
  { atomId: "atom-1", relations: [{ spanId: "span-1", documentId: "doc-1", relation: "ENTAILMENT" }] },
  { atomId: "atom-2", relations: [{ spanId: "span-1", documentId: "doc-1", relation: "CONTRADICTION" }] },
];

describe("buildArgumentationGraph", () => {
  it("creates claim, atom, and deduplicated evidence nodes with NLI edges", () => {
    const graph = buildArgumentationGraph(
      "Mara joined Orion and became CTO.",
      atoms,
      evidence,
      classifications,
      documents,
    );

    expect(graph.nodes.map((node) => node.kind)).toEqual(["claim", "atom", "atom", "evidence"]);
    expect(graph.nodes.find((node) => node.kind === "evidence")?.atomIds).toEqual(["atom-1", "atom-2"]);
    expect(graph.edges.filter((edge) => edge.relation === "DECOMPOSES")).toHaveLength(2);
    expect(graph.edges.map((edge) => edge.relation)).toContain("ENTAILMENT");
    expect(graph.edges.map((edge) => edge.relation)).toContain("CONTRADICTION");
  });

  it("keeps neutral candidates out of the argumentative graph", () => {
    const graph = buildArgumentationGraph(
      "Mara joined Orion.",
      atoms.slice(0, 1),
      evidence.slice(0, 1),
      [{
        atomId: "atom-1",
        relations: [
          { spanId: "span-1", documentId: "doc-1", relation: "ENTAILMENT" },
          { spanId: "span-neutral", documentId: "doc-1", relation: "NEUTRAL" },
        ],
      }],
      documents,
    );

    expect(graph.edges.map((edge) => edge.relation)).not.toContain("NEUTRAL");
    expect(graph.nodes.map((node) => node.text)).not.toContain("Orion issued a report.");
  });

  it("does not invent NLI edges before classifications exist", () => {
    const graph = buildArgumentationGraph("Mara joined Orion.", atoms.slice(0, 1), evidence.slice(0, 1), [], documents);

    expect(graph.edges).toEqual([
      { id: "claim-atom-1", source: "claim", target: "atom-1", relation: "DECOMPOSES" },
    ]);
  });
});
