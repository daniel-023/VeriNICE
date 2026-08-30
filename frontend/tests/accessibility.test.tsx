import { cleanup, fireEvent, render } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AtomRail } from "@/components/AtomRail";
import { ArgumentationGraph } from "@/components/ArgumentationGraph";
import { DocumentPanel } from "@/components/DocumentPanel";
import { LinguisticPanel } from "@/components/LinguisticPanel";
import { PipelinePanel } from "@/components/PipelinePanel";
import { SupportSummary } from "@/components/SupportSummary";
import { VerdictPanel } from "@/components/VerdictPanel";
import { buildArgumentationGraph } from "@/lib/argumentationGraph";
import type {
  AtomLinguisticAnalysis,
  DecomposedAtom,
  VerdictAggregationResult,
} from "@/lib/types";

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
    role: "CORE",
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
          graphState="complete"
          graphLinkCount={1}
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
    const onRelationChange = vi.fn();
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
        onRelationChange={onRelationChange}
        selectedAtomText="A fact."
        retrievalState="complete"
      />,
    );
    const list = getByRole("navigation", { name: "Candidate evidence spans" });
    expect(list).toBeInTheDocument();
    expect(getByRole("button", { name: /Full source document/ })).toBeInTheDocument();
    const reviewer = getByRole("combobox", { name: /Reviewer relation for evidence/ });
    fireEvent.change(reviewer, { target: { value: "CONTRADICTION" } });
    expect(onRelationChange).toHaveBeenCalledWith(
      expect.objectContaining({ id: "doc-a::sentence-1" }),
      "CONTRADICTION",
    );
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });

  it("lists five implemented stages and marks them ready before a run", () => {
    const { getByText, getAllByText, queryByText } = render(
      <PipelinePanel
        decompositionState="idle"
        retrievalState="idle"
        nliState="idle"
        graphState="idle"
        graphLinkCount={0}
        atomCount={0}
        evidenceCount={0}
        relationCount={0}
        onRetryEvidence={() => {}}
        onRetryNli={() => {}}
      />,
    );
    expect(getByText("Find candidate evidence")).toBeInTheDocument();
    expect(getByText("Compare claim and evidence")).toBeInTheDocument();
    expect(getByText("Map support and conflict")).toBeInTheDocument();
    expect(getByText("Apply verdict rules")).toBeInTheDocument();
    expect(getByText("5 live stages")).toBeInTheDocument();
    expect(getAllByText("Ready")).toHaveLength(5);
    expect(queryByText("Pending")).not.toBeInTheDocument();
  });

  it("omits the candidate budget when it cannot be changed", () => {
    const { queryByRole } = render(
      <PipelinePanel
        decompositionState="complete"
        retrievalState="complete"
        nliState="complete"
        graphState="complete"
        graphLinkCount={2}
        atomCount={1}
        evidenceCount={6}
        relationCount={6}
        onRetryEvidence={() => {}}
        onRetryNli={() => {}}
        evidencePerAtom={6}
        recorded
      />,
    );
    // Recorded walkthroughs compute nothing in the browser, so the budget is fixed.
    expect(queryByRole("combobox", { name: /Candidates per obligation/i })).not.toBeInTheDocument();
  });

  it("reports the aggregated verdict on stage five once it completes", () => {
    const { getByText } = render(
      <PipelinePanel
        decompositionState="complete"
        retrievalState="complete"
        nliState="complete"
        graphState="complete"
        verdictState="complete"
        verdict="CONFLICTING_EVIDENCE"
        graphLinkCount={3}
        atomCount={2}
        evidenceCount={6}
        relationCount={6}
        onRetryEvidence={() => {}}
        onRetryNli={() => {}}
      />,
    );
    expect(getByText("Aggregated to conflicting evidence.")).toBeInTheDocument();
    expect(getByText("View Verdict")).toHaveAttribute("href", "#case-verdict");
  });

  it("keeps linguistic features and syntax details semantic and keyboard reachable", async () => {
    const { container, getByText, getByRole } = render(
      <LinguisticPanel
        atom={atoms[0]}
        analysis={analysis}
        summary={null}
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
      "case", "Mara joined Orion in 2022.", "SINGLE",
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

    expect(
      getByRole("group", { name: "Case claim, verification obligations, and evidence relationships" }),
    ).toBeInTheDocument();
    expect(getByRole("button", { name: /Obligation 1, CORE: Mara joined Orion in 2022\./ })).toBeInTheDocument();
    expect(
      getByRole("button", { name: /Evidence from Source A: Mara joined Orion\.\. supports obligation 1/ }),
    ).toBeInTheDocument();
    expect(queryByText("Orion published a report.")).not.toBeInTheDocument();
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });

  it("preserves the selected atom when shared evidence is activated", () => {
    const sharedAtoms = [
      { ...atoms[0], text: "First atom.", sourceText: "First atom.", end: 11 },
      { ...atoms[0], id: "atom-2", text: "Second atom.", sourceText: "Second atom.", end: 12 },
    ];
    const graph = buildArgumentationGraph(
      "case", "First atom. Second atom.", "AND", sharedAtoms,
      [
        { atomId: "atom-1", spans: [{ id: "shared", documentId: "doc-a", text: "The same sentence concerns both atoms.", start: 0, end: 38 }] },
        { atomId: "atom-2", spans: [{ id: "shared", documentId: "doc-a", text: "The same sentence concerns both atoms.", start: 0, end: 38 }] },
      ],
      [
        { atomId: "atom-1", relations: [{ spanId: "shared", documentId: "doc-a", relation: "ENTAILMENT" }] },
        { atomId: "atom-2", relations: [{ spanId: "shared", documentId: "doc-a", relation: "ENTAILMENT" }] },
      ],
      sources,
    );
    const onSelectEvidence = vi.fn();
    const { getByRole } = render(
      <ArgumentationGraph
        graph={graph}
        selectedAtomId="atom-2"
        onSelectAtom={() => {}}
        onSelectEvidence={onSelectEvidence}
      />,
    );

    fireEvent.click(getByRole("button", { name: /Evidence from Source A/ }));
    expect(onSelectEvidence.mock.calls[0][0]).toMatchObject({ evidenceId: "shared" });
    expect(onSelectEvidence.mock.calls[0][1]).toBe("atom-2");
  });

  it("collapses the linguistic panel without losing its heading", () => {
    const onToggle = vi.fn();
    const { getByRole, queryByLabelText, rerender } = render(
      <LinguisticPanel
        atom={atoms[0]}
        analysis={analysis}
        summary={null}
        state="complete"
        error={null}
        onRetry={() => {}}
        open
        onToggle={onToggle}
      />,
    );
    const toggle = getByRole("button", { name: /Hide linguistic structure/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(queryByLabelText("Atomic claim preview")).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(onToggle).toHaveBeenCalledTimes(1);

    rerender(
      <LinguisticPanel
        atom={atoms[0]}
        analysis={analysis}
        summary={null}
        state="complete"
        error={null}
        onRetry={() => {}}
        open={false}
        onToggle={onToggle}
      />,
    );
    expect(getByRole("heading", { name: "Linguistic Structure" })).toBeInTheDocument();
    expect(getByRole("button", { name: /Show linguistic structure/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(queryByLabelText("Atomic claim preview")).not.toBeInTheDocument();
  });

  it("presents the aggregated verdict with obligation text and a decision trace", async () => {
    const result: VerdictAggregationResult = {
      aggregationSchemaVersion: 1,
      claimId: "case-1",
      composition: "AND",
      verdict: "REFUTED",
      positions: {
        supportPosition: false,
        attackPosition: true,
        supportObligationIds: [],
        attackObligationIds: ["atom-1"],
        unresolvedObligationIds: [],
      },
      obligations: [
        {
          obligationId: "atom-1",
          state: "REFUTED",
          supportEdgeIds: [],
          attackEdgeIds: ["edge-1"],
          neutralCandidateCount: 2,
        },
      ],
      warnings: [],
      ruleTrace: ["AND attack requires an attack on any obligation.", "Final verdict: REFUTED."],
    };
    const { container, getByRole, getByText } = render(
      <VerdictPanel result={result} atoms={atoms} referenceLabel="SUPPORTED" />,
    );
    expect(getByRole("heading", { name: /Rule-derived evidence status REFUTED/ })).toBeInTheDocument();
    expect(getByText("Mara joined Orion in 2022.")).toBeInTheDocument();
    expect(getByText("Attack position held")).toBeInTheDocument();
    expect(getByText("differs")).toBeInTheDocument();
    expect(getByText("Decision trace")).toBeInTheDocument();
    const audit = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(audit.violations).toEqual([]);
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
    expect(getByRole("heading", { name: "Grounded evidence relations" })).toBeInTheDocument();
    expect(getByText(/not the case verdict/i)).toBeInTheDocument();
    expect(getByRole("list", { name: "Selected atom relation counts" })).toBeInTheDocument();
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
  });
});
