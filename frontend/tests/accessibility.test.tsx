import { cleanup, fireEvent, render } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AtomRail } from "@/components/AtomRail";
import { ArgumentationGraph } from "@/components/ArgumentationGraph";
import { DocumentPanel } from "@/components/DocumentPanel";
import { LinguisticPanel } from "@/components/LinguisticPanel";
import { PipelinePanel } from "@/components/PipelinePanel";
import { SupportSummary } from "@/components/SupportSummary";
import { buildArgumentationGraph } from "@/lib/argumentationGraph";
import type { AtomLinguisticAnalysis, DecomposedAtom } from "@/lib/types";

afterEach(() => cleanup());

const sources = [
  { id: "doc-a", title: "Source A", url: "https://example.test/a", text: "Full source document." },
  { id: "doc-b", title: "Source B", url: "https://example.test/b", text: "Another source." },
];

const atoms: DecomposedAtom[] = [
  {
    id: "atom-1",
    text: "Mara joined Orion in 2022.",
    sourceText: "Mara joined Orion in 2022 and became CTO.",
    start: 0,
    end: 46,
  },
];

const analysis: AtomLinguisticAnalysis = {
  atomId: "atom-1",
  frames: [{
    id: "frame-1",
    predicate: { id: "predicate-1", text: "joined", start: 5, end: 11 },
    subjects: [{ id: "subject-1", text: "Mara", start: 0, end: 4 }],
    coreArguments: [{ id: "object-1", text: "Orion", start: 12, end: 17, role: "direct_object" }],
    adjuncts: [{ id: "adjunct-1", text: "in 2022", start: 18, end: 25, kind: "temporal" }],
    otherModifiers: [],
  }],
  cues: [{ id: "cue-1", kind: "temporal", text: "2022", start: 21, end: 25 }],
  entities: [{ id: "entity-1", label: "PERSON", text: "Mara", start: 0, end: 4 }],
  tokens: [{ id: "token-1", text: "Mara", lemma: "Mara", pos: "PROPN", tag: "NNP", dependency: "nsubj", head: "joined", start: 0, end: 4 }],
  status: "complete",
  unresolved: [],
};

describe("multidocument workbench accessibility", () => {
  it("has no automated violations in the atom and pipeline panels", async () => {
    const { container } = render(
      <main>
        <AtomRail atoms={atoms} state="complete" selectedAtomId={null} onSelect={() => {}} />
        <PipelinePanel
          decompositionState="complete"
          retrievalState="complete"
          nliState="complete"
          atomCount={1}
          evidenceCount={1}
          relationCount={1}
          onRetryEvidence={() => {}}
          onRetryNli={() => {}}
        />
      </main>,
    );
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });

  it("gives tabs, source controls, and the document editor accessible names", async () => {
    const { container, getByRole } = render(
      <DocumentPanel
        documents={sources}
        activeDocumentId="doc-a"
        onActivate={() => {}}
        onTextChange={() => {}}
        onTitleChange={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
        spans={[]}
        relations={[]}
        selectedAtomText={null}
        retrievalState="idle"
      />,
    );
    expect(getByRole("tablist", { name: "Evidence sources" })).toBeInTheDocument();
    expect(getByRole("textbox", { name: "Evidence document: Source A" })).toHaveValue(
      "Full source document.",
    );
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });

  it("exposes candidate evidence spans as a labelled, keyboard-reachable list", async () => {
    const { container, getByRole } = render(
      <DocumentPanel
        documents={sources}
        activeDocumentId="doc-a"
        onActivate={() => {}}
        onTextChange={() => {}}
        onTitleChange={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
        spans={[
          {
            id: "doc-a::sentence-1",
            documentId: "doc-a",
            text: "Full source document.",
            start: 0,
            end: 21,
          },
        ]}
        relations={[
          {
            spanId: "doc-a::sentence-1",
            documentId: "doc-a",
            relation: "ENTAILMENT",
          },
        ]}
        selectedAtomText="A fact."
        retrievalState="complete"
      />,
    );
    const list = getByRole("navigation", { name: "Candidate evidence spans" });
    expect(list).toBeInTheDocument();
    expect(getByRole("button", { name: /Full source document/ })).toBeInTheDocument();
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });

  it("marks all unfinished verification stages as pending", () => {
    const { getByText, getAllByText } = render(
      <PipelinePanel
        decompositionState="idle"
        retrievalState="idle"
        nliState="idle"
        atomCount={0}
        evidenceCount={0}
        relationCount={0}
        onRetryEvidence={() => {}}
        onRetryNli={() => {}}
      />,
    );
    expect(getByText("Semantic Candidate Matching")).toBeInTheDocument();
    expect(getByText("NLI Support Classification")).toBeInTheDocument();
    expect(getByText("Argumentation Graph")).toBeInTheDocument();
    expect(getByText("Four-way Verdict")).toBeInTheDocument();
    expect(getAllByText("Pending")).toHaveLength(1);
  });

  it("keeps linguistic features and syntax details semantic and keyboard reachable", async () => {
    const { container, getByText, getByRole } = render(
      <LinguisticPanel
        atom={atoms[0]}
        analysis={analysis}
        state="complete"
        error={null}
        onRetry={() => {}}
      />,
    );
    expect(getByRole("button", { name: "Predicate: joined" })).toHaveAttribute("aria-pressed", "false");
    const summary = getByText("Syntax Details");
    summary.focus();
    expect(summary).toHaveFocus();
    fireEvent.click(summary);
    expect(getByRole("table")).toBeVisible();
    expect(getByText(/lemma = base word/)).toBeInTheDocument();
    expect(getByRole("tab", { name: "Readable syntax" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(getByRole("tab", { name: "Readable syntax" }), { key: "ArrowRight" });
    expect(getByRole("tab", { name: "Raw details" })).toHaveFocus();
    expect(getByRole("tabpanel")).toHaveAttribute(
      "aria-labelledby",
      getByRole("tab", { name: "Raw details" }).id,
    );
    fireEvent.click(getByRole("tab", { name: "Raw details" }));
    expect(getByRole("tab", { name: "Raw details" })).toHaveAttribute("aria-selected", "true");
    const tokenButton = getByRole("button", { name: "Token: Mara" });
    fireEvent.click(tokenButton);
    expect(tokenButton).toHaveAttribute("aria-pressed", "true");
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });

  it("exposes selected-atom graph relations without neutral candidates", async () => {
    const graph = buildArgumentationGraph(
      "Mara joined Orion in 2022.",
      atoms,
      [{
        atomId: "atom-1",
        spans: [
          { id: "support", documentId: "doc-a", text: "Mara joined Orion.", start: 0, end: 18 },
          { id: "neutral", documentId: "doc-b", text: "Orion published a report.", start: 0, end: 25 },
        ],
      }],
      [{
        atomId: "atom-1",
        relations: [
          { spanId: "support", documentId: "doc-a", relation: "ENTAILMENT" },
          { spanId: "neutral", documentId: "doc-b", relation: "NEUTRAL" },
        ],
      }],
      sources,
    );
    const { container, getByRole, queryByText } = render(
      <ArgumentationGraph
        graph={graph}
        selectedAtomId="atom-1"
        onSelectAtom={() => {}}
        onSelectEvidence={() => {}}
      />,
    );

    expect(getByRole("navigation", { name: "Atomic claims in argumentation graph" })).toBeInTheDocument();
    expect(getByRole("list", { name: "Supports Atom evidence" })).toBeInTheDocument();
    expect(queryByText("Orion published a report.")).not.toBeInTheDocument();
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });

  it("preserves the selected atom when shared evidence is activated", () => {
    const sharedEvidence = {
      id: "evidence-doc-a:shared",
      kind: "evidence" as const,
      label: "Source A",
      text: "The same sentence concerns both atoms.",
      documentId: "doc-a",
      spanId: "shared",
      atomIds: ["atom-1", "atom-2"],
    };
    const onSelectEvidence = vi.fn();
    const { getByRole } = render(
      <ArgumentationGraph
        graph={{
          nodes: [
            { id: "claim", kind: "claim", label: "Original claim", text: "A compound claim." },
            { id: "atom-1", kind: "atom", label: "Atomic claim", text: "First atom.", atomId: "atom-1" },
            { id: "atom-2", kind: "atom", label: "Atomic claim", text: "Second atom.", atomId: "atom-2" },
            sharedEvidence,
          ],
          edges: [
            { id: "edge-1", source: "atom-1", target: sharedEvidence.id, relation: "ENTAILMENT" },
            { id: "edge-2", source: "atom-2", target: sharedEvidence.id, relation: "ENTAILMENT" },
          ],
        }}
        selectedAtomId="atom-2"
        onSelectAtom={() => {}}
        onSelectEvidence={onSelectEvidence}
      />,
    );

    fireEvent.click(getByRole("button", { name: /Supports Atom, from Source A/ }));
    expect(onSelectEvidence).toHaveBeenCalledWith(sharedEvidence, "atom-2");
  });

  it("announces NLI state and exposes relation counts without a verdict", async () => {
    const { container, getByText, getByRole } = render(
      <SupportSummary
        state="complete"
        classification={{
          atomId: "atom-1",
          relations: [
            { spanId: "s1", documentId: "doc-a", relation: "ENTAILMENT" },
            { spanId: "s2", documentId: "doc-b", relation: "NEUTRAL" },
          ],
        }}
      />,
    );
    expect(getByRole("heading", { name: "NLI Sentence Relations" })).toBeInTheDocument();
    expect(getByText(/not the case verdict/i)).toBeInTheDocument();
    expect(getByRole("list", { name: "Selected atom relation counts" })).toBeInTheDocument();
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });
});
