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
import type { DecomposedAtom } from "@/lib/types";

afterEach(cleanup);
const atom: DecomposedAtom = { id: "a1", text: "NDF is not listed.", sourceText: "NDF is not listed", start: 0, end: 17, role: "CORE" };
const document = { id: "d1", title: "Official list", url: "https://example.test", text: "The complete list is Alpha and Beta.", layout: "PROSE" as const };
const span = { id: "s1", documentId: "d1", text: document.text, start: 0, end: document.text.length };

async function expectAccessible(container: HTMLElement) {
  expect((await axe.run(container)).violations).toEqual([]);
}

describe("Milestone 5 accessibility", () => {
  it("keeps all five pipeline stages and retry controls accessible", async () => {
    const { container } = render(<PipelinePanel
      decompositionState="complete" retrievalState="complete" assessmentState="complete"
      reasoningState="error" graphLinkCount={0} atomCount={1} evidenceCount={1}
      relationCount={1} onRetryEvidence={vi.fn()} onRetryAssessment={vi.fn()}
      onRetryReasoning={vi.fn()} verdictState="idle"
    />);
    await expectAccessible(container);
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
        relation: "REFUTES", premiseIds: ["p1"], premises: [{
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
      premiseIds: [], premises: [], expression: "ndf ∉ S", conclusion: "NDF is absent.", explanation: "Validated.", validationWarnings: [],
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
