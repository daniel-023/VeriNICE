import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({
  cases: vi.fn(), case: vi.fn(), health: vi.fn(), decompose: vi.fn(),
  retrieveCase: vi.fn(), retrieveDocuments: vi.fn(), assessCaseEvidence: vi.fn(), assessDocumentEvidence: vi.fn(),
  reasonCase: vi.fn(), reasonDocuments: vi.fn(), aggregateVerdict: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: apiMock }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));
import { VeriNICEApp } from "@/components/VeriNICEApp";

const detail = {
  id: "sample-1", claim: "NDF is not included in the complete list.", label: "SUPPORTED" as const,
  documents: [{ id: "doc-1", title: "Official list", url: "https://example.test/list", text: "The complete list consists of Alpha, Beta and Gamma.", layout: "STRUCTURED_LIST" as const }],
};
const atom = { id: "atom-1", text: detail.claim, sourceText: detail.claim, start: 0, end: detail.claim.length, role: "CORE" as const };
const evidence = [{ atomId: atom.id, spans: [{ id: "s1", documentId: "doc-1", text: detail.documents[0].text, start: 0, end: detail.documents[0].text.length }] }];
const assessment = {
  obligations: [{ atomId: atom.id, supportSpanIds: [], refuteSpanIds: [], contextSpanIds: [], sufficiency: "PARTIAL" as const, missingInformation: "Membership check", reason: "Map a set operation.", scopeChecks: [] }],
  materialOmission: { detected: false, supportSpanIds: [], contextSpanIds: [], reason: "None." },
};
const proof = {
  id: "p1", atomId: atom.id, operator: "SET_MEMBERSHIP" as const, status: "PROVED" as const, relation: "SUPPORTS" as const,
  profile: "GENERIC_SET_MEMBERSHIP", preconditions: [], premiseIds: [], premises: [], expression: "ndf ∉ source list", conclusion: "NDF is absent.", explanation: "Validated exhaustive list.", validationWarnings: [],
};

beforeEach(() => {
  apiMock.cases.mockResolvedValue([{ ...detail, documents: detail.documents.map(({ text: _text, ...item }) => item) }]);
  apiMock.case.mockResolvedValue(detail);
  apiMock.health.mockResolvedValue({ status: "ready", decompositionConfigured: true, decompositionReady: true, retrievalConfigured: true, decompositionModel: "qwen", retrievalModel: "bge" });
  apiMock.decompose.mockResolvedValue({ schemaVersion: 2, composition: "SINGLE", atoms: [atom], warnings: [], provider: "ollama", model: "qwen" });
  apiMock.retrieveCase.mockResolvedValue({ evidence, provider: "sentence-transformers", model: "bge", retrievalMethod: "HYBRID" });
  apiMock.retrieveDocuments.mockResolvedValue({ evidence, provider: "sentence-transformers", model: "bge", retrievalMethod: "HYBRID" });
  apiMock.assessCaseEvidence.mockResolvedValue({ assessment, provider: "ollama", model: "qwen" });
  apiMock.assessDocumentEvidence.mockResolvedValue({ assessment, provider: "ollama", model: "qwen" });
  apiMock.reasonCase.mockResolvedValue({ executions: [proof], provider: "ollama+python", model: "qwen" });
  apiMock.reasonDocuments.mockResolvedValue({ executions: [proof], provider: "ollama+python", model: "qwen" });
  apiMock.aggregateVerdict.mockResolvedValue({
    aggregationSchemaVersion: 3, claimId: detail.id, composition: "SINGLE", verdict: "SUPPORTED",
    positions: { supportPosition: true, refutePosition: false, supportObligationIds: [atom.id], refuteObligationIds: [], unresolvedObligationIds: [] },
    obligations: [{ obligationId: atom.id, state: "SUPPORTED", supportEdgeIds: [], refuteEdgeIds: [], unselectedCandidateCount: 1, provisionalRelationCount: 0 }], warnings: [], ruleTrace: ["Resolved symbolic rule."],
  });
});

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("live program-guided workflow", () => {
  it("runs retrieval, Qwen assessment, symbolic reasoning, and aggregation in order", async () => {
    render(<VeriNICEApp mode="live" />);
    await userEvent.click(await screen.findByRole("button", { name: /decompose claim/i }));
    await waitFor(() => expect(apiMock.reasonCase).toHaveBeenCalledTimes(1));
    expect(apiMock.assessCaseEvidence).toHaveBeenCalledTimes(1);
    expect(apiMock.reasonCase.mock.invocationCallOrder[0]).toBeGreaterThan(apiMock.assessCaseEvidence.mock.invocationCallOrder[0]);
    await waitFor(() => expect(apiMock.aggregateVerdict).toHaveBeenCalledWith(expect.objectContaining({ assessment, reasoning: [proof] })));
  });

  it("shows the selected atom's rule result without model attribution or a confidence score", async () => {
    render(<VeriNICEApp mode="live" />);
    await userEvent.click(await screen.findByRole("button", { name: /decompose claim/i }));
    await userEvent.click((await screen.findAllByRole("button", { name: new RegExp(atom.text) }))[0]);
    expect((await screen.findAllByText("Proved", { exact: false })).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Assessed by Qwen/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Executed in Python/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();
    const evidenceHeading = screen.getByRole("heading", { name: "Evidence Assessment" });
    const symbolicHeading = screen.getByRole("heading", { name: "Symbolic Checks" });
    expect(evidenceHeading.compareDocumentPosition(symbolicHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps Stage 03 relation totals claim-wide when the selected atom changes", async () => {
    const secondAtom = {
      ...atom,
      id: "atom-2",
      text: "Beta is excluded from the complete list.",
      sourceText: "Beta is excluded from the complete list.",
    };
    const secondSpan = { ...evidence[0].spans[0], id: "s2" };
    const multiEvidence = [
      evidence[0],
      { atomId: secondAtom.id, spans: [secondSpan] },
    ];
    const multiAssessment = {
      obligations: [
        { ...assessment.obligations[0], atomId: atom.id, supportSpanIds: ["s1"], missingInformation: "" },
        { ...assessment.obligations[0], atomId: secondAtom.id, refuteSpanIds: ["s2"], missingInformation: "" },
      ],
      materialOmission: assessment.materialOmission,
    };
    apiMock.decompose.mockResolvedValueOnce({
      schemaVersion: 2,
      composition: "AND",
      atoms: [atom, secondAtom],
      warnings: [],
      provider: "ollama",
      model: "qwen",
    });
    apiMock.retrieveCase.mockResolvedValueOnce({ evidence: multiEvidence, provider: "sentence-transformers", model: "bge", retrievalMethod: "HYBRID" });
    apiMock.assessCaseEvidence.mockResolvedValueOnce({ assessment: multiAssessment, provider: "ollama", model: "qwen" });
    apiMock.reasonCase.mockResolvedValueOnce({ executions: [], provider: "ollama+python", model: "qwen" });

    render(<VeriNICEApp mode="live" />);
    await userEvent.click(await screen.findByRole("button", { name: /decompose claim/i }));
    const relationList = await screen.findByRole("list", { name: "Claim-wide evidence relation counts" });
    expect(relationList).toHaveTextContent(/1\s*Supports/);
    expect(relationList).toHaveTextContent(/1\s*Refutes/);

    await userEvent.click(screen.getByRole("button", {
      name: `Select atomic claim 2: ${secondAtom.text}`,
    }));
    expect(relationList).toHaveTextContent(/1\s*Supports/);
    expect(relationList).toHaveTextContent(/1\s*Refutes/);
  });

  it("focuses the exact source sentence selected in the reasoning graph", async () => {
    const firstSentence = "The first retrieved sentence is only background.";
    const secondSentence = "The second retrieved sentence is the selected evidence.";
    const sourceText = `${firstSentence} ${secondSentence}`;
    const secondStart = firstSentence.length + 1;
    const focusedDetail = {
      ...detail,
      documents: [{ ...detail.documents[0], text: sourceText }],
    };
    const focusedEvidence = [{
      atomId: atom.id,
      spans: [
        { id: "s1", documentId: "doc-1", text: firstSentence, start: 0, end: firstSentence.length },
        { id: "s2", documentId: "doc-1", text: secondSentence, start: secondStart, end: sourceText.length },
      ],
    }];
    const focusedAssessment = {
      ...assessment,
      obligations: [{
        ...assessment.obligations[0],
        supportSpanIds: ["s1", "s2"],
        sufficiency: "SUFFICIENT" as const,
        missingInformation: "",
      }],
    };
    apiMock.case.mockResolvedValueOnce(focusedDetail);
    apiMock.retrieveCase.mockResolvedValueOnce({
      evidence: focusedEvidence,
      provider: "sentence-transformers",
      model: "bge",
      retrievalMethod: "HYBRID",
    });
    apiMock.assessCaseEvidence.mockResolvedValueOnce({
      assessment: focusedAssessment,
      provider: "ollama",
      model: "qwen",
    });
    apiMock.reasonCase.mockResolvedValueOnce({ executions: [], provider: "ollama+python", model: "qwen" });
    apiMock.aggregateVerdict.mockResolvedValueOnce({
      aggregationSchemaVersion: 3,
      claimId: detail.id,
      composition: "SINGLE",
      verdict: "SUPPORTED",
      positions: {
        supportPosition: true,
        refutePosition: false,
        supportObligationIds: [atom.id],
        refuteObligationIds: [],
        unresolvedObligationIds: [],
      },
      obligations: [{
        obligationId: atom.id,
        state: "SUPPORTED",
        supportEdgeIds: [`edge:SUPPORTS:inference:bundle:${atom.id}:supports:obligation:${detail.id}:${atom.id}`],
        refuteEdgeIds: [],
        unselectedCandidateCount: 0,
        provisionalRelationCount: 0,
      }],
      warnings: [],
      ruleTrace: ["Resolved assessed evidence bundle."],
    });

    render(<VeriNICEApp mode="live" />);
    await userEvent.click(await screen.findByRole("button", { name: /decompose claim/i }));
    await waitFor(() => expect(apiMock.assessCaseEvidence).toHaveBeenCalledTimes(1));

    await userEvent.click(await screen.findByRole("button", {
      name: new RegExp(`open evidence from official list: ${secondSentence}`, "i"),
    }));

    await waitFor(() => {
      const highlights = screen.getAllByTestId("evidence-highlight");
      expect(highlights).toHaveLength(1);
      expect(highlights[0]).toHaveTextContent(secondSentence);
    });
  });

  it("retains decomposition but clears evidence, assessment, and reasoning after a document edit", async () => {
    render(<VeriNICEApp mode="live" />);
    await userEvent.click(await screen.findByRole("button", { name: /decompose claim/i }));
    await waitFor(() => expect(apiMock.reasonCase).toHaveBeenCalled());
    fireEvent.change(screen.getByRole("textbox", { name: /evidence document/i }), { target: { value: "Edited source." } });
    expect(screen.getAllByText(atom.text).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Ready.").length).toBeGreaterThan(0);
  });

  it("uses Retry Rules without repeating decomposition or retrieval", async () => {
    apiMock.reasonCase.mockRejectedValueOnce(new Error("Compiler unavailable.")).mockResolvedValueOnce({ executions: [proof], provider: "ollama+python", model: "qwen" });
    render(<VeriNICEApp mode="live" />);
    await userEvent.click(await screen.findByRole("button", { name: /decompose claim/i }));
    await userEvent.click(await screen.findByRole("button", { name: /retry rules/i }));
    await waitFor(() => expect(apiMock.reasonCase).toHaveBeenCalledTimes(2));
    expect(apiMock.decompose).toHaveBeenCalledTimes(1);
    expect(apiMock.retrieveCase).toHaveBeenCalledTimes(1);
  });

  it("reruns retrieval and downstream stages when the retrieval method changes", async () => {
    render(<VeriNICEApp mode="live" />);
    await userEvent.click(await screen.findByRole("button", { name: /decompose claim/i }));
    await waitFor(() => expect(apiMock.retrieveCase).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByText("Evidence Matching: Hybrid"));
    expect(screen.getByText(/reruns evidence retrieval and all later stages/i)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Hybrid" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Semantic" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Lexical" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Matching method" }), "SEMANTIC");
    await waitFor(() => expect(apiMock.retrieveCase).toHaveBeenCalledTimes(2));
    expect(apiMock.retrieveCase).toHaveBeenLastCalledWith(detail.id, [{ id: atom.id, text: atom.text }], 6, "SEMANTIC");
    expect(apiMock.decompose).toHaveBeenCalledTimes(1);
  });

  it("reruns retrieval with the selected candidate budget", async () => {
    render(<VeriNICEApp mode="live" />);
    await userEvent.click(await screen.findByRole("button", { name: /decompose claim/i }));
    await waitFor(() => expect(apiMock.retrieveCase).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByText("Evidence Matching: Hybrid"));
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Candidate sentences per atomic claim" }),
      "8",
    );
    await waitFor(() => expect(apiMock.retrieveCase).toHaveBeenCalledTimes(2));
    expect(apiMock.retrieveCase).toHaveBeenLastCalledWith(
      detail.id,
      [{ id: atom.id, text: atom.text }],
      8,
      "HYBRID",
    );
    expect(apiMock.decompose).toHaveBeenCalledTimes(1);
  });

  it("keeps AVeriTeC cases in their own category", async () => {
    const constructedCases = Array.from({ length: 15 }, (_, index) => ({
      ...detail,
      id: `constructed-${index + 1}`,
      displayTitle: `Constructed sample ${index + 1}`,
      origin: "CONSTRUCTED" as const,
      category: "SCIENCE" as const,
      documents: detail.documents.map(({ text: _text, ...item }) => item),
    }));
    apiMock.cases.mockResolvedValue([
      ...constructedCases,
      { id: "averitec-dev-0001", claim: "A separate dataset claim.", label: "REFUTED", origin: "AVERITEC", category: "SCIENCE", documents: [] },
      { id: "averitec-dev-0002", claim: "A second dataset claim.", label: "SUPPORTED", origin: "AVERITEC", category: "HISTORY", documents: [] },
      { id: "averitec-dev-0003", claim: "A third dataset claim.", label: "NOT_ENOUGH_EVIDENCE", origin: "AVERITEC", category: "GEOGRAPHY", documents: [] },
    ]);
    render(<VeriNICEApp mode="live" />);
    await userEvent.click(await screen.findByRole("button", { name: "AVeriTeC" }));
    expect(screen.getByRole("option", { name: "16 — A separate dataset claim." })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "17 — A second dataset claim." })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "18 — A third dataset claim." })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "AVeriTeC" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Constructed sample/i })).not.toBeInTheDocument();
  });
});
