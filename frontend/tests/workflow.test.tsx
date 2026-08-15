import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({
  cases: vi.fn(),
  case: vi.fn(),
  health: vi.fn(),
  decompose: vi.fn(),
  retrieveCase: vi.fn(),
  retrieveDocuments: vi.fn(),
  classifySupport: vi.fn(),
  analyzeLinguistics: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiMock }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));
import { VeriGraphApp } from "@/components/VeriGraphApp";

const details = [
  {
    id: "sample-1",
    claim: "Mara joined Orion in 2022 and became CTO.",
    documents: [
      {
        id: "doc-a",
        title: "Appointment report",
        url: "https://example.test/appointment",
        text: "Mara joined Orion in 2022. The company announced the appointment.",
      },
      {
        id: "doc-b",
        title: "Leadership profile",
        url: "https://example.test/profile",
        text: "Orion later named Mara its CTO. Her profile lists the new role.",
      },
    ],
    label: "SUPPORTED" as const,
  },
  {
    id: "sample-2",
    claim: "The archive opened in 2019.",
    documents: [
      {
        id: "doc-c",
        title: "Archive history",
        url: "https://example.test/archive",
        text: "The archive opened in 2021.",
      },
      {
        id: "doc-d",
        title: "Opening announcement",
        url: "https://example.test/announcement",
        text: "Officials announced the archive in 2021.",
      },
    ],
    label: "REFUTED" as const,
  },
];

const summaries = details.map(({ documents, ...sample }) => ({
  ...sample,
  documents: documents.map(({ text: _text, ...document }) => document),
}));

beforeEach(() => {
  apiMock.cases.mockReset().mockResolvedValue(summaries);
  apiMock.case.mockReset().mockImplementation((id: string) =>
    Promise.resolve(details.find((item) => item.id === id)),
  );
  apiMock.health.mockReset().mockResolvedValue({
    status: "configured",
    decompositionConfigured: true,
    retrievalConfigured: true,
    nliConfigured: true,
    linguisticsConfigured: true,
    decompositionModel: "test-model",
    retrievalModel: "test-embedding",
    nliModel: "test-nli",
    linguisticsModel: "en_core_web_sm@3.8.0",
  });
  apiMock.decompose.mockReset().mockResolvedValue({
    atoms: [
      {
        id: "atom-1",
        text: "Mara joined Orion in 2022.",
        sourceText: details[0].claim,
        start: 0,
        end: details[0].claim.length,
      },
      {
        id: "atom-2",
        text: "Mara became CTO.",
        sourceText: details[0].claim,
        start: 0,
        end: details[0].claim.length,
      },
    ],
    provider: "ollama",
    model: "test-model",
  });
  apiMock.retrieveCase.mockReset().mockResolvedValue({
    evidence: [
      {
        atomId: "atom-1",
        spans: [
          {
            id: "doc-a::sentence-1",
            documentId: "doc-a",
            text: "Mara joined Orion in 2022. ",
            start: 0,
            end: 27,
          },
          {
            id: "doc-b::sentence-2",
            documentId: "doc-b",
            text: "Her profile lists the new role.",
            start: 32,
            end: 63,
          },
        ],
      },
      {
        atomId: "atom-2",
        spans: [
          {
            id: "doc-b::sentence-1",
            documentId: "doc-b",
            text: "Orion later named Mara its CTO. ",
            start: 0,
            end: 32,
          },
        ],
      },
    ],
    provider: "sentence-transformers",
    model: "test-embedding",
  });
  apiMock.retrieveDocuments.mockReset().mockResolvedValue({
    evidence: [{ atomId: "atom-1", spans: [] }, { atomId: "atom-2", spans: [] }],
    provider: "sentence-transformers",
    model: "test-embedding",
  });
  apiMock.classifySupport.mockReset().mockResolvedValue({
    classifications: [
      {
        atomId: "atom-1",
        relations: [
          {
            spanId: "doc-a::sentence-1",
            documentId: "doc-a",
            relation: "ENTAILMENT",
          },
          {
            spanId: "doc-b::sentence-2",
            documentId: "doc-b",
            relation: "NEUTRAL",
          },
        ],
      },
      {
        atomId: "atom-2",
        relations: [
          {
            spanId: "doc-b::sentence-1",
            documentId: "doc-b",
            relation: "CONTRADICTION",
          },
        ],
      },
    ],
    provider: "transformers",
    model: "test-nli",
  });
  apiMock.analyzeLinguistics.mockReset().mockResolvedValue({
    analyses: [
      {
        atomId: "atom-1",
        frames: [{
          id: "atom-1-frame-1",
          predicate: { id: "atom-1-predicate", text: "joined", start: 5, end: 11 },
          subjects: [{ id: "atom-1-subject", text: "Mara", start: 0, end: 4 }],
          coreArguments: [{ id: "atom-1-object", text: "Orion", start: 12, end: 17, role: "direct_object" }],
          adjuncts: [{ id: "atom-1-adjunct", text: "in 2022", start: 18, end: 25, kind: "temporal" }],
          otherModifiers: [],
        }],
        cues: [{ id: "atom-1-date", kind: "temporal", text: "2022", start: 21, end: 25 }],
        entities: [{ id: "atom-1-person", label: "PERSON", text: "Mara", start: 0, end: 4 }],
        tokens: [{ id: "atom-1-token-0", text: "Mara", start: 0, end: 4, lemma: "Mara", pos: "PROPN", tag: "NNP", dependency: "nsubj", head: "joined" }],
        status: "complete",
        unresolved: [],
      },
      {
        atomId: "atom-2",
        frames: [{
          id: "atom-2-frame-1",
          predicate: { id: "atom-2-predicate", text: "became", start: 5, end: 11 },
          subjects: [{ id: "atom-2-subject", text: "Mara", start: 0, end: 4 }],
          coreArguments: [{ id: "atom-2-complement", text: "CTO", start: 12, end: 15, role: "subject_complement" }],
          adjuncts: [],
          otherModifiers: [],
        }],
        cues: [],
        entities: [{ id: "atom-2-person", label: "PERSON", text: "Mara", start: 0, end: 4 }],
        tokens: [{ id: "atom-2-token-0", text: "Mara", start: 0, end: 4, lemma: "Mara", pos: "PROPN", tag: "NNP", dependency: "nsubj", head: "became" }],
        status: "complete",
        unresolved: [],
      },
    ],
    provider: "spacy",
    model: "en_core_web_sm@3.8.0",
  });
});

afterEach(() => cleanup());

describe("multidocument claim decomposition workflow", () => {
  it("loads summaries first and the selected sample documents on demand", async () => {
    render(<VeriGraphApp />);
    expect(await screen.findByRole("textbox", { name: "Claim to decompose" })).toHaveValue(
      details[0].claim,
    );
    expect(apiMock.case).toHaveBeenCalledWith("sample-1");
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.getByRole("tab", { name: "Appointment report" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      screen.getByRole("textbox", { name: "Evidence document: Appointment report" }),
    ).toHaveValue(details[0].documents[0].text);
    expect(screen.getByText(/Reference Label · SUPPORTED/i)).toBeInTheDocument();
  });

  it("retrieves by case ID and switches to the selected atom's evidence source", async () => {
    const user = userEvent.setup();
    render(<VeriGraphApp />);
    const claimInput = await screen.findByRole("textbox", { name: "Claim to decompose" });
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await screen.findByText("Mara became CTO.");
    expect(apiMock.retrieveCase).toHaveBeenCalledWith("sample-1", [
      { id: "atom-1", text: "Mara joined Orion in 2022." },
      { id: "atom-2", text: "Mara became CTO." },
    ]);
    expect(apiMock.analyzeLinguistics).toHaveBeenCalledWith([
      { id: "atom-1", text: "Mara joined Orion in 2022." },
      { id: "atom-2", text: "Mara became CTO." },
    ]);
    expect(apiMock.classifySupport).toHaveBeenCalledWith(
      [
        { id: "atom-1", text: "Mara joined Orion in 2022." },
        { id: "atom-2", text: "Mara became CTO." },
      ],
      expect.any(Array),
    );

    await user.click(screen.getByRole("button", { name: /Mara became CTO/i }));
    expect(claimInput).toHaveFocus();
    expect(screen.getByRole("tab", { name: /Leadership profile/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByTestId("evidence-highlight")).toHaveTextContent(
      "Orion later named Mara its CTO.",
    );
    expect(screen.getByRole("heading", { name: "Linguistic Structure" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "NLI Sentence Relations" })).toBeInTheDocument();
    expect(screen.getByText("Contradicts atom")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Predicate: became" }));
    expect(screen.getByLabelText("Atomic claim preview").querySelector("mark")).toHaveTextContent("became");
  });

  it("lists every span of the selected atom and jumps across sources", async () => {
    const user = userEvent.setup();
    render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await screen.findByText("Mara became CTO.");
    await user.click(screen.getByRole("button", { name: /Mara joined Orion/i }));

    const list = screen.getByRole("navigation", { name: "Candidate evidence spans" });
    const entries = within(list).getAllByRole("button");
    expect(entries).toHaveLength(2);
    expect(entries[0]).toHaveTextContent("Appointment report");
    expect(entries[0]).toHaveTextContent("Mara joined Orion in 2022");
    expect(entries[0]).toHaveTextContent("Supports atom");
    expect(entries[1]).toHaveTextContent("Her profile lists the new role.");
    expect(entries[1]).toHaveTextContent("Neither");
    expect(screen.getByText(/1 candidate evidence span highlighted in this source, 1 in other sources/i))
      .toBeInTheDocument();

    await user.click(entries[1]);
    expect(screen.getByRole("tab", { name: /Leadership profile/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByTestId("evidence-highlight")).toHaveTextContent(
      "Her profile lists the new role.",
    );
  });

  it("keeps atoms but clears evidence and the reference label after document edits", async () => {
    const user = userEvent.setup();
    render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await screen.findByText("Mara became CTO.");
    await user.click(screen.getByRole("button", { name: /Mara joined Orion/i }));
    expect(screen.getByTestId("evidence-highlight")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Linguistic Structure" })).toBeInTheDocument();

    await user.type(
      screen.getByRole("textbox", { name: "Evidence document: Appointment report" }),
      " More context.",
    );
    expect(screen.getByText("Mara became CTO.")).toBeInTheDocument();
    expect(screen.queryByTestId("evidence-highlight")).not.toBeInTheDocument();
    expect(screen.queryByText("Supports atom")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Linguistic Structure" })).toBeInTheDocument();
    expect(screen.queryByText(/Reference Label/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await waitFor(() => expect(apiMock.retrieveDocuments).toHaveBeenCalledTimes(1));
    expect(apiMock.retrieveDocuments).toHaveBeenCalledWith(
      expect.any(Array),
      expect.any(Array),
    );
  });

  it("clears decomposition after claim edits", async () => {
    const user = userEvent.setup();
    render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await screen.findByText("Mara became CTO.");
    await user.type(screen.getByRole("textbox", { name: "Claim to decompose" }), " More.");
    expect(screen.queryByText("Mara became CTO.")).not.toBeInTheDocument();
  });

  it("preserves atoms and retries only multidocument retrieval", async () => {
    const user = userEvent.setup();
    apiMock.retrieveCase
      .mockRejectedValueOnce(new Error("Evidence selector timed out. Please retry."))
      .mockResolvedValueOnce({
        evidence: [{ atomId: "atom-1", spans: [] }, { atomId: "atom-2", spans: [] }],
        provider: "sentence-transformers",
        model: "test-embedding",
      });
    render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Claim decomposed; candidate retrieval failed",
    );
    await user.click(screen.getByRole("button", { name: "Retry Evidence" }));
    await waitFor(() => expect(apiMock.retrieveCase).toHaveBeenCalledTimes(2));
    expect(apiMock.decompose).toHaveBeenCalledTimes(1);
  });

  it("keeps evidence when linguistics fails and retries only linguistics", async () => {
    const user = userEvent.setup();
    const successfulAnalysis = apiMock.analyzeLinguistics.getMockImplementation();
    apiMock.analyzeLinguistics
      .mockRejectedValueOnce(new Error("The packaged parser is unavailable."))
      .mockImplementationOnce(successfulAnalysis!);
    render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await user.click(await screen.findByRole("button", { name: /Mara joined Orion/i }));
    expect(await screen.findByTestId("evidence-highlight")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Retry Linguistics" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry Linguistics" }));
    await waitFor(() => expect(apiMock.analyzeLinguistics).toHaveBeenCalledTimes(2));
    expect(apiMock.decompose).toHaveBeenCalledTimes(1);
    expect(apiMock.retrieveCase).toHaveBeenCalledTimes(1);
  });

  it("keeps evidence and retries only NLI classification", async () => {
    const user = userEvent.setup();
    const successfulClassification = apiMock.classifySupport.getMockImplementation();
    apiMock.classifySupport
      .mockRejectedValueOnce(new Error("The local NLI model is unavailable."))
      .mockImplementationOnce(successfulClassification!);
    render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await user.click(await screen.findByRole("button", { name: /Mara joined Orion/i }));
    expect(await screen.findByTestId("evidence-highlight")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Retry NLI" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry NLI" }));
    await waitFor(() => expect(apiMock.classifySupport).toHaveBeenCalledTimes(2));
    expect(apiMock.decompose).toHaveBeenCalledTimes(1);
    expect(apiMock.retrieveCase).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Supports atom")).toBeInTheDocument();
  });

  it("ignores an older linguistic response after the claim changes", async () => {
    const user = userEvent.setup();
    const successful = await apiMock.analyzeLinguistics([]);
    let resolveOlder: (value: typeof successful) => void = () => {};
    const older = new Promise<typeof successful>((resolve) => {
      resolveOlder = resolve;
    });
    apiMock.analyzeLinguistics
      .mockReset()
      .mockReturnValueOnce(older)
      .mockResolvedValueOnce(successful);

    render(<VeriGraphApp />);
    const claimInput = await screen.findByRole("textbox", { name: "Claim to decompose" });
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await user.click(await screen.findByRole("button", { name: /Mara became CTO/i }));
    expect(screen.getByText("Analyzing language…")).toBeInTheDocument();

    await user.type(claimInput, " More context.");
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await user.click(await screen.findByRole("button", { name: /Mara became CTO/i }));
    expect(await screen.findByRole("button", { name: "Predicate: became" })).toBeInTheDocument();

    resolveOlder({ ...successful, analyses: [] });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Predicate: became" })).toBeInTheDocument();
    });
  });

  it("ignores an older NLI response after the document changes", async () => {
    const user = userEvent.setup();
    let resolveOlder: (value: unknown) => void = () => {};
    apiMock.classifySupport.mockReset().mockReturnValueOnce(
      new Promise((resolve) => {
        resolveOlder = resolve;
      }),
    );

    render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    await user.click(screen.getByRole("button", { name: "Decompose Claim" }));
    await user.click(await screen.findByRole("button", { name: /Mara joined Orion/i }));
    expect(screen.getByText("Classifying candidate sentences…")).toBeInTheDocument();

    await user.type(
      screen.getByRole("textbox", { name: "Evidence document: Appointment report" }),
      " Updated.",
    );
    resolveOlder({
      classifications: [
        {
          atomId: "atom-1",
          relations: [
            {
              spanId: "doc-a::sentence-1",
              documentId: "doc-a",
              relation: "ENTAILMENT",
            },
          ],
        },
      ],
      provider: "transformers",
      model: "test-nli",
    });
    await waitFor(() => {
      expect(screen.queryByText("Supports atom")).not.toBeInTheDocument();
    });
  });

  it("synchronizes the active source mirror without React scroll state", async () => {
    const user = userEvent.setup();
    const { container } = render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    const textarea = screen.getByRole("textbox", {
      name: "Evidence document: Appointment report",
    });
    const mirror = container.querySelector(".document-mirror") as HTMLDivElement;
    Object.defineProperty(textarea, "scrollTop", { value: 31, writable: true });
    fireEvent.scroll(textarea);
    expect(mirror.scrollTop).toBe(31);
    await user.click(screen.getByRole("tab", { name: "Leadership profile" }));
  });

  it("supports custom source add, rename, keyboard navigation, and removal", async () => {
    const user = userEvent.setup();
    render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    await user.selectOptions(screen.getByRole("combobox", { name: "Demo Sample" }), "custom");
    expect(screen.getByRole("textbox", { name: "Claim to decompose" })).toHaveValue("");
    expect(screen.getAllByRole("tab")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Add evidence source" }));
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    const title = screen.getByRole("textbox", { name: "Source title" });
    await user.clear(title);
    await user.type(title, "Second report");
    expect(screen.getByRole("tab", { name: "Second report" })).toBeInTheDocument();

    const firstTab = screen.getByRole("tab", { name: "Source 1" });
    firstTab.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Second report" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Remove Second report" }));
    expect(screen.getAllByRole("tab")).toHaveLength(1);
  });

  it("caches full cases after their first load", async () => {
    const user = userEvent.setup();
    render(<VeriGraphApp />);
    await screen.findByDisplayValue(details[0].claim);
    const selector = screen.getByRole("combobox", { name: "Demo Sample" });
    await user.selectOptions(selector, "sample-2");
    await screen.findByDisplayValue(details[1].claim);
    await user.selectOptions(selector, "sample-1");
    await screen.findByDisplayValue(details[0].claim);
    expect(apiMock.case).toHaveBeenCalledTimes(2);
  });
});
