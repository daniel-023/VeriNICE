import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ArgumentationGraph } from "@/components/ArgumentationGraph";
import { DocumentPanel } from "@/components/DocumentPanel";
import { PipelinePanel } from "@/components/PipelinePanel";
import { SymbolicProofPanel } from "@/components/SymbolicProofPanel";
import { SupportSummary } from "@/components/SupportSummary";
import { buildArgumentationGraph } from "@/lib/argumentationGraph";
import type { DecomposedAtom, SymbolicExecution } from "@/lib/types";

afterEach(cleanup);
const atom: DecomposedAtom = { id: "a1", text: "NDF is not listed.", sourceText: "NDF is not listed", start: 0, end: 17, role: "CORE" };
const document = { id: "d1", title: "Official list", url: "https://example.test", text: "The complete list is Alpha and Beta.", layout: "PROSE" as const };
const span = { id: "s1", documentId: "d1", text: document.text, start: 0, end: document.text.length };
const SYMBOLIC_RULE_LABELS = [
  "Set membership",
  "Numeric comparison",
  "Temporal comparison",
  "Attribute comparison",
  "Distinct-value count",
  "Largest/smallest comparison",
];

async function expectAccessible(container: HTMLElement) {
  expect((await axe.run(container)).violations).toEqual([]);
}

describe("Milestone 5 accessibility", () => {
  it("keeps all five pipeline stages and retry controls accessible", async () => {
    const { container } = render(<PipelinePanel
      decompositionState="complete" retrievalState="complete" assessmentState="complete"
      reasoningState="error" atomCount={1} evidenceCount={1}
      relationCounts={{ SUPPORTS: 1, REFUTES: 0, CONTEXT: 0, NOT_SELECTED: 0 }}
      symbolicExecutions={[]} onRetryEvidence={vi.fn()} onRetryAssessment={vi.fn()}
      onRetryReasoning={vi.fn()} verdictState="idle"
    />);
    await expectAccessible(container);
  });

  it("keeps recorded retrieval settings expanded and read-only", async () => {
    const { container } = render(
      <PipelinePanel
        decompositionState="complete"
        retrievalState="complete"
        assessmentState="complete"
        reasoningState="complete"
        atomCount={1}
        evidenceCount={6}
        relationCounts={{ SUPPORTS: 1, REFUTES: 0, CONTEXT: 0, NOT_SELECTED: 5 }}
        symbolicExecutions={[]}
        onRetryEvidence={vi.fn()}
        onRetryAssessment={vi.fn()}
        onRetryReasoning={vi.fn()}
        verdictState="complete"
        verdict="SUPPORTED"
        evidencePerAtom={6}
        retrievalMethod="HYBRID"
        recorded
      />,
    );

    const summary = screen.getByText("Evidence Matching: Hybrid");
    expect(summary.closest("details")).toHaveAttribute("open");
    expect(screen.getByRole("combobox", { name: "Matching method" })).toBeDisabled();
    expect(
      screen.getByRole("combobox", {
        name: "Candidate sentences per atomic claim",
      }),
    ).toBeDisabled();
    expect(
      screen.getByText(/In a live run, changing either setting reruns/i),
    ).toBeVisible();
    await expectAccessible(container);
  });

  it("explains claim-wide evidence relations and all six symbolic rule types", async () => {
    const program: SymbolicExecution["program"] = {
      version: 1,
      steps: [],
      outputStepId: "result",
    };
    const executions: SymbolicExecution[] = [
      {
        id: "supports", atomId: "a1", operator: "ATTRIBUTE_COMPARE", status: "PROVED", relation: "SUPPORTS",
        profile: "EXPLICIT_NEGATION", preconditions: [], premiseIds: [], premises: [], expression: "A = A", conclusion: "The attribute matches.", explanation: "Compared attributes.", validationWarnings: [], program,
      },
      {
        id: "refutes", atomId: "a2", operator: "ATTRIBUTE_COMPARE", status: "DISPROVED", relation: "REFUTES",
        profile: "COUNTRY_LOCATION", preconditions: [], premiseIds: [], premises: [], expression: "B ≠ C", conclusion: "The attribute differs.", explanation: "Compared attributes.", validationWarnings: [], program,
      },
      {
        id: "unresolved", atomId: "a2", operator: "EXTREMUM_COMPARE", status: "UNRESOLVED", relation: null,
        profile: "GENERIC_EXTREMUM_COUNTEREXAMPLE", preconditions: [], premiseIds: [], premises: [], expression: "maximum", conclusion: "No complete universe.", explanation: "Could not resolve.", validationWarnings: [], program,
      },
      {
        id: "not-applicable", atomId: "a2", operator: "TEMPORAL_COMPARE", status: "NOT_APPLICABLE", relation: null,
        profile: "GENERIC_ABSOLUTE_DATE", preconditions: [], premiseIds: [], premises: [], expression: "date", conclusion: "No date relation.", explanation: "Not applicable.", validationWarnings: [], program,
      },
      {
        id: "unresolved-duplicate", atomId: "a1", operator: "EXTREMUM_COMPARE", status: "UNRESOLVED", relation: null,
        profile: "GENERIC_EXTREMUM_COUNTEREXAMPLE", preconditions: [], premiseIds: [], premises: [], expression: "maximum", conclusion: "No complete universe.", explanation: "Could not resolve.", validationWarnings: [], program,
      },
    ];
    const { container } = render(
      <PipelinePanel
        decompositionState="complete" retrievalState="complete" assessmentState="complete"
        reasoningState="complete" atomCount={2} evidenceCount={8}
        relationCounts={{ SUPPORTS: 2, REFUTES: 1, CONTEXT: 1, NOT_SELECTED: 4 }}
        symbolicExecutions={executions} onRetryEvidence={vi.fn()} onRetryAssessment={vi.fn()}
        onRetryReasoning={vi.fn()} verdictState="complete" verdict="REFUTED"
      />,
    );

    const relationList = screen.getByRole("list", { name: "Claim-wide evidence relation counts" });
    expect(relationList).toHaveTextContent(/2\s*Supports/);
    expect(relationList).toHaveTextContent(/1\s*Refutes/);
    expect(relationList).toHaveTextContent(/1\s*Context/);
    expect(relationList).toHaveTextContent(/4\s*Not used/);
    expect(screen.getByText("How Evidence Relations Work")).toBeInTheDocument();
    expect(screen.getByText("View 6 Rule Types")).toBeInTheDocument();
    const ruleSummary = screen.getByRole("group", { name: "Symbolic checks in this run" });
    expect(ruleSummary).toHaveTextContent("Supports");
    expect(ruleSummary).toHaveTextContent("Refutes");
    expect(ruleSummary).toHaveTextContent("Unresolved");
    expect(ruleSummary).toHaveTextContent("Not applicable");
    expect(ruleSummary).toHaveTextContent(/Largest\/smallest comparison\s*×2/);
    SYMBOLIC_RULE_LABELS.forEach((label) => expect(screen.getAllByText(label).length).toBeGreaterThan(0));
    expect(container.querySelectorAll(".stage-rule-catalog > .is-active")).toHaveLength(3);
    expect(screen.getAllByText("Available")).toHaveLength(3);
    await expectAccessible(container);
  });

  it("identifies a completed run that uses direct evidence only", () => {
    render(
      <PipelinePanel
        decompositionState="complete" retrievalState="complete" assessmentState="complete"
        reasoningState="complete" atomCount={1} evidenceCount={0}
        relationCounts={{ SUPPORTS: 0, REFUTES: 0, CONTEXT: 0, NOT_SELECTED: 0 }}
        symbolicExecutions={[]} onRetryEvidence={vi.fn()} onRetryAssessment={vi.fn()}
        onRetryReasoning={vi.fn()} verdictState="complete" verdict="NOT_ENOUGH_EVIDENCE"
      />,
    );
    const relationList = screen.getByRole("list", { name: "Claim-wide evidence relation counts" });
    expect(relationList).toHaveTextContent(/0\s*Supports/);
    expect(relationList).toHaveTextContent(/0\s*Refutes/);
    expect(relationList).toHaveTextContent(/0\s*Context/);
    expect(relationList).toHaveTextContent(/0\s*Not used/);
    expect(screen.getByText("Direct evidence only · no symbolic rule applied.")).toBeVisible();
  });

  it("renders source tabs, highlights and four reviewer relations accessibly", async () => {
    const { container } = render(<DocumentPanel
      documents={[document]} activeDocumentId="d1" onActivate={vi.fn()} onTextChange={vi.fn()}
      onTitleChange={vi.fn()} onAdd={vi.fn()} onRemove={vi.fn()} onRelationChange={vi.fn()}
      spans={[span]} relations={[{
        spanId: "s1", documentId: "d1", relation: "NOT_SELECTED", decisive: false,
        scopeCheck: { spanId: "s1", documentId: "d1", status: "MISMATCH", claimJurisdictions: ["AU"], evidenceJurisdictions: ["US"], reason: "Different jurisdiction." },
      }]}
      selectedAtomText={atom.text} retrievalState="complete"
    />);
    expect(container.textContent).toContain("Different jurisdiction — not used in assessment");
    expect(container.querySelector('option[value="SUPPORTS"]')).toBeDisabled();
    expect(container.querySelector('option[value="REFUTES"]')).toBeDisabled();
    await expectAccessible(container);
  });

  it("keeps curated source metadata compact and leaves match counts in the tabs", () => {
    const curatedDocument = {
      ...document,
      publisher: "U.S. Geological Survey",
      sourceDescriptor: "Institutional source",
      sourceType: "SOURCE_EXCERPT" as const,
    };

    render(<DocumentPanel
      documents={[curatedDocument]} activeDocumentId="d1" onActivate={vi.fn()}
      onTextChange={vi.fn()} onTitleChange={vi.fn()} onAdd={vi.fn()} onRemove={vi.fn()}
      spans={[span]} relations={[]} selectedAtomText={atom.text} retrievalState="complete"
      readOnly
    />);

    expect(screen.getByText("U.S. Geological Survey")).toBeVisible();
    expect(screen.getByRole("link", { name: /view source/i })).toBeVisible();
    expect(screen.queryByText(/Institutional source|Source excerpt/)).not.toBeInTheDocument();
    expect(screen.queryByText(/matches? in this source|elsewhere/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("1 evidence spans")).toBeVisible();
  });

  it("shows source matching status only when it needs attention", () => {
    const baseProps = {
      documents: [document],
      activeDocumentId: "d1",
      onActivate: vi.fn(),
      onTextChange: vi.fn(),
      onTitleChange: vi.fn(),
      onAdd: vi.fn(),
      onRemove: vi.fn(),
      relations: [],
      selectedAtomText: atom.text,
    };
    const { container, rerender } = render(
      <DocumentPanel {...baseProps} spans={[span]} retrievalState="complete" />,
    );

    expect(container.querySelector(".document-match-status")).not.toBeInTheDocument();
    expect(container.querySelector("textarea")).not.toHaveAttribute("aria-describedby");

    rerender(<DocumentPanel {...baseProps} spans={[]} retrievalState="running" />);
    expect(screen.getByText("Matching sentences…")).toBeVisible();

    rerender(<DocumentPanel {...baseProps} spans={[]} retrievalState="error" />);
    expect(screen.getByText("Sentence matching unavailable.")).toBeVisible();

    rerender(<DocumentPanel {...baseProps} spans={[]} retrievalState="complete" />);
    expect(screen.getByText("No matching sentences in this source.")).toBeVisible();
    expect(container.querySelector("textarea")).toHaveAttribute(
      "aria-describedby",
      "document-candidate-status",
    );
  });

  it("renders a compact evidence-to-verdict graph without accessibility violations", async () => {
    const graph = buildArgumentationGraph("case", "NDF is not listed.", "SINGLE", [atom], [{ atomId: "a1", spans: [span] }], [{ atomId: "a1", relations: [{ spanId: "s1", documentId: "d1", relation: "SUPPORTS", decisive: true }] }], [document]);
    const verdict = {
      aggregationSchemaVersion: 3 as const, claimId: "case", composition: "SINGLE" as const, verdict: "SUPPORTED" as const,
      positions: { supportPosition: true, refutePosition: false, supportObligationIds: ["a1"], refuteObligationIds: [], unresolvedObligationIds: [] },
      obligations: [{ obligationId: "a1", state: "SUPPORTED" as const, supportEdgeIds: [], refuteEdgeIds: [], unselectedCandidateCount: 0, provisionalRelationCount: 0 }],
      warnings: [], ruleTrace: [],
    };
    const { container } = render(<ArgumentationGraph graph={graph} selectedAtomId={null} onSelectAtom={vi.fn()} onSelectEvidence={vi.fn()} obligationStates={{ a1: "SUPPORTED" }} verdict={verdict} verdictState="complete" />);
    expect(container.textContent).toContain("Selected evidence");
    expect(container.textContent).toContain("1 sentence");
    expect(container.textContent).toContain("Atomic Claim");
    expect(container.textContent).toContain("Atomic result · O1");
    expect(container.textContent).not.toContain("Joint assessment");
    expect(container.textContent).not.toContain("Composition · SINGLE");
    expect(container.textContent).toContain("Verdict · Single claim");
    expect(container.textContent).toContain("Verdict");
    expect(container.textContent).toContain("SUPPORTED");
    await expectAccessible(container);
  });

  it("keeps every atomic claim visible and opens the exact source from a lane", async () => {
    const secondAtom: DecomposedAtom = { ...atom, id: "a2", text: "Beta is listed.", sourceText: "Beta is listed", start: 0, end: 14 };
    const onSelectEvidence = vi.fn();
    const graph = buildArgumentationGraph(
      "case", "NDF is not listed.", "AND", [atom, secondAtom],
      [{ atomId: "a1", spans: [span] }, { atomId: "a2", spans: [span] }],
      [
        { atomId: "a1", relations: [{ spanId: "s1", documentId: "d1", relation: "SUPPORTS", decisive: true }] },
        { atomId: "a2", relations: [{ spanId: "s1", documentId: "d1", relation: "SUPPORTS", decisive: true }] },
      ],
      [document],
    );
    render(<ArgumentationGraph graph={graph} selectedAtomId="a1" onSelectAtom={vi.fn()} onSelectEvidence={onSelectEvidence} />);
    expect(screen.getByRole("button", { name: /select atomic claim 1/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /select atomic claim 2/i })).toBeVisible();
    const sourceButtons = screen.getAllByRole("button", { name: /open evidence from official list/i });
    expect(sourceButtons).toHaveLength(2);
    expect(screen.getByText("Composition · AND")).toBeVisible();
    await userEvent.click(sourceButtons[1]);
    expect(onSelectEvidence).toHaveBeenCalledWith(expect.objectContaining({ evidenceId: "s1" }), "a2");
  });

  it("aggregates sentence relations across evidence bundles", () => {
    const secondDocument = { ...document, id: "d2", title: "Second source" };
    const secondSpan = { ...span, id: "s2", documentId: "d2" };
    const graph = buildArgumentationGraph(
      "case",
      "NDF is not listed.",
      "SINGLE",
      [atom],
      [{ atomId: "a1", spans: [span, secondSpan] }],
      [{ atomId: "a1", relations: [
        { spanId: "s1", documentId: "d1", relation: "SUPPORTS", decisive: true },
        { spanId: "s2", documentId: "d2", relation: "SUPPORTS", decisive: true },
      ] }],
      [document, secondDocument],
    );
    const { container } = render(<ArgumentationGraph graph={graph} selectedAtomId="a1" onSelectAtom={vi.fn()} onSelectEvidence={vi.fn()} />);
    expect(container.textContent).toContain("Evidence bundle");
    expect(container.textContent).toContain("Joint assessment");
    expect(container.textContent).toContain("Total · 2 support · 0 refute");
  });

  it("keeps routine provisional-evidence diagnostics out of verdict notes", () => {
    const graph = buildArgumentationGraph("case", "NDF is not listed.", "SINGLE", [atom], [{ atomId: "a1", spans: [span] }], [{ atomId: "a1", relations: [] }], [document]);
    const verdict = {
      aggregationSchemaVersion: 3 as const, claimId: "case", composition: "SINGLE" as const, verdict: "SUPPORTED" as const,
      positions: { supportPosition: true, refutePosition: false, supportObligationIds: ["a1"], refuteObligationIds: [], unresolvedObligationIds: [] },
      obligations: [{ obligationId: "a1", state: "SUPPORTED" as const, supportEdgeIds: [], refuteEdgeIds: [], unselectedCandidateCount: 0, provisionalRelationCount: 1 }],
      warnings: [{ code: "PROVISIONAL_EVIDENCE_EXCLUDED", message: "One provisional relation was excluded." }],
      ruleTrace: [],
    };
    const { container } = render(<ArgumentationGraph graph={graph} selectedAtomId="a1" onSelectAtom={vi.fn()} onSelectEvidence={vi.fn()} obligationStates={{ a1: "SUPPORTED" }} verdict={verdict} verdictState="complete" />);
    expect(container.textContent).not.toContain("Verdict notes");
    expect(container.textContent).not.toContain("One provisional relation was excluded.");
  });

  it("presents a grounded location rule between its evidence and atomic result", () => {
    const locationAtom: DecomposedAtom = {
      id: "a1", text: "The landmark is located in Germany.",
      sourceText: "The landmark is located in Germany", start: 0, end: 35,
      role: "LOCATION_CONSTRAINT",
    };
    const locationDocument = {
      ...document, text: "Its official address is Paris, France.",
    };
    const locationSpan = {
      ...span, text: locationDocument.text, end: locationDocument.text.length,
    };
    const graph = buildArgumentationGraph(
      "location-case", `${locationAtom.text}`, "SINGLE", [locationAtom],
      [{ atomId: "a1", spans: [locationSpan] }], [{ atomId: "a1", relations: [] }],
      [locationDocument], [{
        id: "proof-1", atomId: "a1", operator: "ATTRIBUTE_COMPARE", status: "DISPROVED",
        profile: "COUNTRY_LOCATION", preconditions: [], relation: "REFUTES", premiseIds: ["p1"], premises: [{
          id: "p1", documentId: "d1", text: locationDocument.text, start: 0,
          end: locationDocument.text.length, kind: "EVIDENCE",
        }], expression: "France ≠ Germany", conclusion: "The locations differ.",
        explanation: "Compared locations.", validationWarnings: [], program: {
          version: 1, outputStepId: "result", steps: [{
            id: "result", operation: "EQUAL", inputIds: ["p1"], outputType: "BOOLEAN",
            description: "Compare values.",
          }],
        },
      }],
    );
    const { container } = render(<ArgumentationGraph
      graph={graph} selectedAtomId="a1" onSelectAtom={vi.fn()} onSelectEvidence={vi.fn()}
      obligationStates={{ a1: "REFUTED" }}
    />);
    expect(container.textContent).toContain("Location comparison");
    expect(container.textContent).toContain("France ≠ Germany");
    expect(container.textContent).toContain("Atomic result · O1");
    expect(container.textContent).not.toContain("ATTRIBUTE COMPARE");
  });

  it("shows the verdict contribution and keeps rule mechanics in details", async () => {
    const { container } = render(<SymbolicProofPanel atomId="a1" documents={[]} onSelectPremise={vi.fn()} state="complete" proofs={[{
      id: "p1", atomId: "a1", operator: "SET_MEMBERSHIP", status: "PROVED", relation: "SUPPORTS",
      profile: "GENERIC_SET_MEMBERSHIP", preconditions: [], premiseIds: [], premises: [], expression: "ndf ∉ S", conclusion: "NDF is absent.", explanation: "Validated.", validationWarnings: [],
      program: {
        version: 1,
        steps: [{ id: "step-1", operation: "MEMBER", inputIds: [], outputType: "BOOLEAN", description: "Check membership." }],
        outputStepId: "step-1",
      },
    }]} />);
    expect(container.textContent).toContain("Effect on this atom");
    expect(container.textContent).toContain("Supports this atomic claim");
    expect(container.textContent).toContain("Rule details");
    expect(container.textContent).not.toContain("Qwen");
    expect(container.textContent).not.toContain("Python");
    expect(container.textContent?.toLowerCase()).not.toContain("confidence");
    await expectAccessible(container);
  });

  it("hides routine scope checks and groups repeated exceptions", async () => {
    const scopeCheck = {
      spanId: "s1", documentId: "d1", status: "UNRESOLVED" as const,
      claimJurisdictions: [], evidenceJurisdictions: [], reason: "Source scope is unclear.",
    };
    const { container } = render(<SupportSummary
      state="complete"
      classification={{ atomId: "a1", relations: [
        { spanId: "s1", documentId: "d1", relation: "REFUTES", decisive: false },
        { spanId: "s2", documentId: "d1", relation: "CONTEXT", decisive: false },
      ] }}
      audit={{
        atomId: "a1", supportSpanIds: [], refuteSpanIds: ["s1"], contextSpanIds: ["s2"],
        sufficiency: "INSUFFICIENT", missingInformation: "A direct source statement is missing.",
        reason: "The selected material is incomplete.",
        scopeChecks: [scopeCheck, { ...scopeCheck, spanId: "s2" }, {
          ...scopeCheck, spanId: "s3", status: "NOT_APPLICABLE", reason: "No scope comparison is needed.",
        }],
      }}
    />);
    expect(container.textContent).toContain("No decisive relation");
    expect(container.textContent).toContain("1 refute · 1 context");
    expect(container.textContent).toContain("2 unresolved");
    expect(container.textContent).not.toContain("No scope comparison is needed.");
    expect(container.textContent).not.toContain("Not selected");
    await expectAccessible(container);
  });
});
