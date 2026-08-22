import type {
  AtomEvidence,
  ClaimComposition,
  DecomposedAtom,
  DecompositionResponse,
  DemoCase,
  DemoCaseSummary,
  DemoDocument,
  EvidenceRetrievalResponse,
  Health,
  LinguisticAnalysisResponse,
  SupportClassificationResponse,
  VerdictAggregationResult,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

type AtomInput = Array<{ id: string; text: string }>;
type LinguisticAnalysisInput = {
  schemaVersion: 2;
  claimText: string;
  composition: ClaimComposition;
  atoms: DecomposedAtom[];
};

export const api = {
  health: () => request<Health>("/api/v1/health"),
  cases: () => request<DemoCaseSummary[]>("/api/v1/demo-cases"),
  case: (id: string) => request<DemoCase>(`/api/v1/demo-cases/${encodeURIComponent(id)}`),
  decompose: (claim: string) =>
    request<DecompositionResponse>("/api/v1/decompose", {
      method: "POST",
      body: JSON.stringify({ claim }),
    }),
  retrieveCase: (caseId: string, atoms: AtomInput) =>
    request<EvidenceRetrievalResponse>("/api/v1/retrieve", {
      method: "POST",
      body: JSON.stringify({ caseId, atoms }),
    }),
  retrieveDocuments: (documents: DemoDocument[], atoms: AtomInput) =>
    request<EvidenceRetrievalResponse>("/api/v1/retrieve", {
      method: "POST",
      body: JSON.stringify({
        documents: documents.map(({ id, text }) => ({ id, text })),
        atoms,
      }),
    }),
  classifySupport: (atoms: AtomInput, evidence: AtomEvidence[]) =>
    request<SupportClassificationResponse>("/api/v1/classify-support", {
      method: "POST",
      body: JSON.stringify({
        atoms,
        evidence: evidence.map((item) => ({
          atomId: item.atomId,
          spans: item.spans.map(({ id, documentId, text }) => ({
            id,
            documentId,
            text,
          })),
        })),
      }),
    }),
  analyzeLinguistics: (input: LinguisticAnalysisInput) =>
    request<LinguisticAnalysisResponse>("/api/v1/analyze-linguistics", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  aggregateVerdict: (input: {
    claimId: string;
    claim: string;
    composition: ClaimComposition;
    atoms: DecomposedAtom[];
    evidence: AtomEvidence[];
    classifications: SupportClassificationResponse["classifications"];
    linguisticSummaries?: LinguisticAnalysisResponse["summaries"];
  }) => request<VerdictAggregationResult>("/api/v1/aggregate-verdict", {
    method: "POST",
    body: JSON.stringify(input),
  }),
};
