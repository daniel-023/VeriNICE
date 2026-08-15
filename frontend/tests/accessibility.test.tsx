import { cleanup, fireEvent, render } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it } from "vitest";
import { AtomRail } from "@/components/AtomRail";
import { DocumentPanel } from "@/components/DocumentPanel";
import { LinguisticPanel } from "@/components/LinguisticPanel";
import { PipelinePanel } from "@/components/PipelinePanel";
import { SupportSummary } from "@/components/SupportSummary";
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
    expect(getAllByText("Pending")).toHaveLength(2);
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
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
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
