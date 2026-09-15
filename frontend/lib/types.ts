export type ReferenceLabel =
  | "SUPPORTED"
  | "REFUTED"
  | "NOT_ENOUGH_EVIDENCE"
  | "CONFLICTING_EVIDENCE";

export type DemoTopic =
  | "POLITICS_ELECTIONS"
  | "PUBLIC_HEALTH"
  | "CLIMATE_ENVIRONMENT"
  | "ECONOMY_BUSINESS"
  | "SCIENCE_TECHNOLOGY"
  | "LAW_PUBLIC_POLICY"
  | "CONFLICT_SECURITY"
  | "SOCIETY_CULTURE";

export type DemoChallenge =
  | "MULTI_PART"
  | "NEGATION"
  | "NUMBERS"
  | "TIME"
  | "ATTRIBUTION"
  | "CAUSALITY"
  | "LIST_SET_REASONING"
  | "CONFLICTING_SOURCES"
  | "SPARSE_EVIDENCE";

export type DemoOrigin = "CONSTRUCTED" | "AVERITEC";
export type DemoCategory = "SCIENCE" | "HISTORY" | "GEOGRAPHY" | "TECHNOLOGY" | "CURRENT_AFFAIRS";
export type DemoFocus =
  | "DECOMPOSITION"
  | "DIRECT_EVIDENCE"
  | "NUMERIC_COMPARISON"
  | "ATTRIBUTE_COMPARISON"
  | "TEMPORAL_COMPARISON"
  | "SET_MEMBERSHIP"
  | "DISTINCT_VALUE_COUNT"
  | "EXTREMUM"
  | "INSUFFICIENT_EVIDENCE"
  | "CONFLICTING_EVIDENCE";

export interface DemoDocumentSummary {
  id: string;
  title: string;
  url: string;
  layout: "PROSE" | "STRUCTURED_LIST";
  publisher?: string;
  retrievedAt?: string | null;
  sourceType?: "SOURCE_EXCERPT" | "FULL_SOURCE";
  sourceDescriptor?: string;
  excerptRationale?: string;
  excerptSha256?: string | null;
  sourceSha256?: string | null;
}

export interface DemoDocument extends DemoDocumentSummary {
  text: string;
}

export interface DemoCaseSummary {
  id: string;
  claim: string;
  documents: DemoDocumentSummary[];
  label: ReferenceLabel;
  displayTitle?: string;
  topics?: DemoTopic[];
  challenges?: DemoChallenge[];
  featured?: boolean;
  origin?: DemoOrigin;
  category?: DemoCategory | null;
  demoFocus?: DemoFocus | null;
}

export interface DemoCase extends Omit<DemoCaseSummary, "documents"> {
  documents: DemoDocument[];
}

export interface DecomposedAtom {
  id: string;
  text: string;
  sourceText: string;
  start: number;
  end: number;
  role: ObligationRole;
}

export type ClaimComposition = "SINGLE" | "AND" | "OR";

export type ObligationRole =
  | "CORE"
  | "NUMERIC_CONSTRAINT"
  | "TEMPORAL_CONSTRAINT"
  | "ATTRIBUTION"
  | "LOCATION_CONSTRAINT"
  | "CAUSAL_RELATION"
  | "CONDITIONAL"
  | "MODALITY_CONSTRAINT";

export interface DecompositionWarning {
  code: string;
  message: string;
}

export interface DecompositionResponse {
  schemaVersion: 2;
  composition: ClaimComposition;
  atoms: DecomposedAtom[];
  warnings: DecompositionWarning[];
  provider: "ollama";
  model: string;
}

export interface EvidenceSpan {
  id: string;
  documentId: string;
  text: string;
  start: number;
  end: number;
  /** Explicit source sentences used only to interpret the evidence anchor. */
  contextSpans?: EvidenceContextSpan[];
  /** Backward-compatible assembled premise for recorded runs. */
  context?: string;
}

export interface EvidenceContextSpan {
  id: string;
  documentId: string;
  text: string;
  start: number;
  end: number;
  direction: "PREVIOUS" | "NEXT";
}

export interface AtomEvidence {
  atomId: string;
  spans: EvidenceSpan[];
}

export interface EvidenceRetrievalResponse {
  evidence: AtomEvidence[];
  provider: "sentence-transformers" | "python";
  model: string;
  retrievalMethod: RetrievalMethod;
}

export type RetrievalMethod = "HYBRID" | "SEMANTIC" | "LEXICAL";

export type CandidateRelation = "SUPPORTS" | "REFUTES" | "CONTEXT" | "NOT_SELECTED";

export interface EvidenceRelation {
  spanId: string;
  documentId: string;
  relation: CandidateRelation;
  decisive: boolean;
  scopeCheck?: EvidenceScopeCheck;
}

export interface AtomEvidenceAssessment {
  atomId: string;
  relations: EvidenceRelation[];
}

export type ArgumentationNodeType =
  | "CASE_CLAIM"
  | "VERIFICATION_OBLIGATION"
  | "INFERENCE"
  | "CONTEXT"
  | "EVIDENCE";

export interface CaseClaimNode {
  id: string;
  type: "CASE_CLAIM";
  text: string;
  composition: ClaimComposition;
}

export interface VerificationObligationNode {
  id: string;
  type: "VERIFICATION_OBLIGATION";
  atomId: string;
  text: string;
  role: ObligationRole;
  sourceText: string;
  start: number;
  end: number;
}

export interface EvidenceNode {
  id: string;
  type: "EVIDENCE";
  evidenceId: string;
  documentId: string;
  documentTitle: string;
  documentUrl: string;
  text: string;
  start: number;
  end: number;
  bestRank: number;
  contextSpans?: EvidenceContextSpan[];
  displayText?: string;
  listItems?: SymbolicListItem[];
}

export interface ContextNode {
  id: string;
  type: "CONTEXT";
  evidenceId: string;
  documentId: string;
  text: string;
  start: number;
  end: number;
}

export interface InferenceNode {
  id: string;
  type: "INFERENCE";
  atomId: string;
  inferenceKind: "EVIDENCE_BUNDLE" | SymbolicOperator;
  expression: string;
  conclusion: string;
  explanation: string;
  premiseIds: string[];
  relation: "SUPPORTS" | "REFUTES" | null;
  compiledBy?: string;
  executedBy?: string;
  status?: SymbolicStatus;
}

export type ArgumentationNode =
  | CaseClaimNode
  | VerificationObligationNode
  | ContextNode
  | InferenceNode
  | EvidenceNode;

export type ArgumentationEdgeType = "DECOMPOSES_TO" | "CONTEXTUALIZES" | "REQUIRES" | "SUPPORTS" | "REFUTES";

export interface ArgumentationEdge {
  id: string;
  source: string;
  target: string;
  type: ArgumentationEdgeType;
  assessed?: boolean;
}

export type GraphWarningCode =
  | "MISSING_EVIDENCE"
  | "MISSING_OBLIGATION"
  | "DUPLICATE_NODE_ID"
  | "DUPLICATE_EDGE_ID"
  | "UNSUPPORTED_RELATION"
  | "INVALID_SOURCE_OFFSETS"
  | "EMPTY_OBLIGATION_TEXT"
  | "AGGREGATION_EDGE_MISMATCH";

export interface GraphWarning {
  code: GraphWarningCode;
  message: string;
}

export interface GraphStats {
  obligationCount: number;
  evidenceCount: number;
  inferenceCount: number;
  contextCount: number;
  supportEdgeCount: number;
  refuteEdgeCount: number;
  unselectedCandidateCount: number;
  obligationsWithoutArgumentEdges: number;
}

export interface ArgumentationGraph {
  schemaVersion: 4;
  claimId: string;
  nodes: ArgumentationNode[];
  edges: ArgumentationEdge[];
  warnings: GraphWarning[];
  stats: GraphStats;
}

export type ObligationEvidenceState = "SUPPORTED" | "REFUTED" | "CONFLICTING" | "UNRESOLVED";

export interface VerdictObligationSummary {
  obligationId: string;
  state: ObligationEvidenceState;
  supportEdgeIds: string[];
  refuteEdgeIds: string[];
  unselectedCandidateCount: number;
  provisionalRelationCount: number;
}

export interface VerdictAggregationResult {
  aggregationSchemaVersion: 3;
  claimId: string;
  composition: ClaimComposition;
  verdict: ReferenceLabel;
  positions: {
    supportPosition: boolean;
    refutePosition: boolean;
    materialOmissionPosition?: boolean;
    supportObligationIds: string[];
    refuteObligationIds: string[];
    unresolvedObligationIds: string[];
  };
  obligations: VerdictObligationSummary[];
  warnings: Array<{ code: string; message: string }>;
  ruleTrace: string[];
}

export interface EvidenceAssessmentResponse {
  assessment: GroundedEvidenceAssessment;
  provider: "ollama";
  model: string;
}

export interface GroundedObligationAudit {
  atomId: string;
  supportSpanIds: string[];
  refuteSpanIds: string[];
  contextSpanIds?: string[];
  sufficiency: "SUFFICIENT" | "PARTIAL" | "INSUFFICIENT";
  missingInformation: string;
  reason: string;
  scopeChecks: EvidenceScopeCheck[];
}

export interface MaterialOmissionCertificate {
  detected: boolean;
  supportSpanIds: string[];
  contextSpanIds: string[];
  reason: string;
}

export type EvidenceScopeStatus = "MATCH" | "MISMATCH" | "UNRESOLVED" | "NOT_APPLICABLE";

export interface EvidenceScopeCheck {
  spanId: string;
  documentId: string;
  status: EvidenceScopeStatus;
  claimJurisdictions: string[];
  evidenceJurisdictions: string[];
  reason: string;
}

export interface GroundedEvidenceAssessment {
  obligations: GroundedObligationAudit[];
  materialOmission: MaterialOmissionCertificate;
}

export type SymbolicOperator = "SET_MEMBERSHIP" | "NUMERIC_COMPARE" | "TEMPORAL_COMPARE" | "ATTRIBUTE_COMPARE" | "COUNT_DISTINCT" | "EXTREMUM_COMPARE";
export type SymbolicStatus = "PROVED" | "DISPROVED" | "UNRESOLVED" | "NOT_APPLICABLE";
export type SymbolicPreconditionStatus = "PASSED" | "FAILED" | "UNRESOLVED";

export interface SymbolicPrecondition {
  name: string;
  status: SymbolicPreconditionStatus;
  detail: string;
}

export interface SymbolicListItem {
  id: string;
  documentId: string;
  text: string;
  start: number;
  end: number;
  contentHash: string;
}

export interface SymbolicPremise {
  id: string;
  documentId: string;
  text: string;
  start: number;
  end: number;
  kind: "EVIDENCE" | "LIST_CERTIFICATE" | "LIST_ITEM" | "OPERAND";
  contentHash?: string | null;
  itemCount?: number | null;
  listItems?: SymbolicListItem[];
}

export interface SymbolicExecution {
  id: string;
  atomId: string;
  operator: SymbolicOperator;
  profile: string;
  status: SymbolicStatus;
  relation: "SUPPORTS" | "REFUTES" | null;
  premiseIds: string[];
  premises: SymbolicPremise[];
  expression: string;
  conclusion: string;
  explanation: string;
  validationWarnings: string[];
  preconditions: SymbolicPrecondition[];
  program: {
    version: 1;
    steps: Array<{
      id: string;
      operation: "LOOKUP" | "EQUAL" | "NOT_EQUAL" | "NUMERIC_COMPARE" | "TEMPORAL_COMPARE" | "MEMBER" | "COUNT_DISTINCT" | "EXTREMUM_COUNTEREXAMPLE";
      inputIds: string[];
      outputType: "FACT" | "BOOLEAN" | "NUMBER" | "DATE" | "SET";
      description: string;
    }>;
    outputStepId: string;
  };
}

export interface ReasoningResponse {
  executions: SymbolicExecution[];
  provider: "ollama+python";
  model: string;
}

/** A complete, local pipeline run rendered by the static Vercel walkthrough. */
export interface WalkthroughRun {
  caseId: string;
  schemaVersion: 7;
  composition: ClaimComposition;
  warnings: DecompositionWarning[];
  atoms: DecomposedAtom[];
  evidence: AtomEvidence[];
  assessment: GroundedEvidenceAssessment;
  reasoning: SymbolicExecution[];
  /** Recorded aggregation result. Absent in walkthroughs recorded before stage 05. */
  verdict?: VerdictAggregationResult;
  recordedWith: {
    pipelineRevision: "generalized-symbolic-v5";
    inputDigest: string;
    decompositionModel: string;
    retrievalModel: string;
    retrievalMethod: RetrievalMethod;
    assessmentModel: string;
    reasoningModel: string;
  };
}

export interface Health {
  status: "ready" | "degraded" | "unconfigured";
  decompositionConfigured: boolean;
  decompositionReady: boolean;
  retrievalConfigured: boolean;
  decompositionModel: string;
  retrievalModel: string;
}

export type StageState = "idle" | "running" | "complete" | "error";
export type MobilePanel = "atoms" | "pipeline" | "document";
