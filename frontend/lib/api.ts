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
  EvidenceAssessmentResponse,
  GroundedEvidenceAssessment,
  ReasoningResponse,
  RetrievalMethod,
  SymbolicExecution,
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
  retrieveCase: (caseId: string, atoms: AtomInput, evidencePerAtom?: number, retrievalMethod: RetrievalMethod = "HYBRID") =>
    request<EvidenceRetrievalResponse>("/api/v1/retrieve", {
      method: "POST",
      body: JSON.stringify({ caseId, atoms, evidencePerAtom, retrievalMethod }),
    }),
  retrieveDocuments: (
    documents: DemoDocument[],
    atoms: AtomInput,
    evidencePerAtom?: number,
    retrievalMethod: RetrievalMethod = "HYBRID",
  ) =>
    request<EvidenceRetrievalResponse>("/api/v1/retrieve", {
      method: "POST",
      body: JSON.stringify({
        documents: documents.map(({ id, text }) => ({ id, text })),
        atoms,
        evidencePerAtom,
        retrievalMethod,
      }),
    }),
  assessCaseEvidence: (
    caseId: string,
    claim: string,
    atoms: AtomInput,
    evidence: AtomEvidence[],
  ) =>
    request<EvidenceAssessmentResponse>("/api/v1/assess-evidence", {
      method: "POST",
      body: JSON.stringify({
        claim,
        atoms,
        caseId,
        evidence: evidence.map((item) => ({
          atomId: item.atomId,
          spans: item.spans.map(({ id, documentId, text, start, end, contextSpans, context }) => ({
            id,
            documentId,
            text,
            start,
            end,
            contextSpans,
            context,
          })),
        })),
      }),
    }),
  assessDocumentEvidence: (
    documents: DemoDocument[],
    claim: string,
    atoms: AtomInput,
    evidence: AtomEvidence[],
  ) =>
    request<EvidenceAssessmentResponse>("/api/v1/assess-evidence", {
      method: "POST",
      body: JSON.stringify({ claim, atoms, evidence, documents }),
    }),
  reasonCase: (
    caseId: string,
    claim: string,
    atoms: AtomInput,
    evidence: AtomEvidence[],
    assessment: GroundedEvidenceAssessment,
  ) => request<ReasoningResponse>("/api/v1/reason", {
    method: "POST",
    body: JSON.stringify({ caseId, claim, atoms, evidence, assessment }),
  }),
  reasonDocuments: (
    documents: DemoDocument[],
    claim: string,
    atoms: AtomInput,
    evidence: AtomEvidence[],
    assessment: GroundedEvidenceAssessment,
  ) => request<ReasoningResponse>("/api/v1/reason", {
    method: "POST",
    body: JSON.stringify({
      documents: documents.map(({ id, text }) => ({ id, text })),
      claim,
      atoms,
      evidence,
      assessment,
    }),
  }),
  analyzeLinguistics: (input: LinguisticAnalysisInput) =>
    request<LinguisticAnalysisResponse>("/api/v1/analyze-linguistics", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  aggregateVerdict: (input: {
    claimId: string;
    composition: ClaimComposition;
    atoms: DecomposedAtom[];
    evidence: AtomEvidence[];
    assessment: GroundedEvidenceAssessment;
    reasoning?: SymbolicExecution[];
  }) => request<VerdictAggregationResult>("/api/v1/aggregate-verdict", {
    method: "POST",
    body: JSON.stringify(input),
  }),
};
