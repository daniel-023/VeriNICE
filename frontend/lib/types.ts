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
  | "ATTRIBUTE_COMPARISON"
  | "TEMPORAL_COMPARISON"
  | "SET_MEMBERSHIP"
  | "DISTINCT_VALUE_COUNT"
  | "EXTREMUM"
  | "INSUFFICIENT_EVIDENCE";

export interface DemoDocumentSummary {
  id: string;
  title: string;
  url: string;
  layout: "PROSE" | "STRUCTURED_LIST";
  publisher?: string;
  retrievedAt?: string | null;
  sourceType?: "SOURCE_EXCERPT" | "FULL_SOURCE";
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

export interface SymbolicPremise {
  id: string;
  documentId: string;
  text: string;
  start: number;
  end: number;
  kind: "EVIDENCE" | "LIST_CERTIFICATE" | "LIST_ITEM" | "OPERAND";
  contentHash?: string | null;
  itemCount?: number | null;
}

export interface SymbolicExecution {
  id: string;
  atomId: string;
  operator: SymbolicOperator;
  status: SymbolicStatus;
  relation: "SUPPORTS" | "REFUTES" | null;
  premiseIds: string[];
  premises: SymbolicPremise[];
  expression: string;
  conclusion: string;
  explanation: string;
  validationWarnings: string[];
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

export interface LinguisticSpan {
  id: string;
  text: string;
  start: number;
  end: number;
}

export type LinguisticArgumentRole =
  | "direct_object"
  | "indirect_object"
  | "passive_agent"
  | "subject_complement"
  | "object_complement"
  | "clausal_complement";

export interface LinguisticArgument extends LinguisticSpan {
  role: LinguisticArgumentRole;
}

export type LinguisticModifierKind =
  | "temporal"
  | "locative"
  | "manner"
  | "causal"
  | "conditional"
  | "purpose";

export interface LinguisticModifier extends LinguisticSpan {
  kind: LinguisticModifierKind;
}

export interface PropositionFrame {
  id: string;
  predicate: LinguisticSpan | null;
  subjects: LinguisticSpan[];
  coreArguments: LinguisticArgument[];
  adjuncts: LinguisticModifier[];
  otherModifiers: LinguisticSpan[];
}

export type LinguisticCueKind =
  | "negation"
  | "quantifier"
  | "modality"
  | "attribution"
  | "temporal"
  | "numeric";

export interface LinguisticCue extends LinguisticSpan {
  kind: LinguisticCueKind;
}

export interface LinguisticEntity extends LinguisticSpan {
  label: string;
}

export interface LinguisticToken extends LinguisticSpan {
  lemma: string;
  pos: string;
  tag: string;
  dependency: string;
  head: string;
}

export interface AtomLinguisticAnalysis {
  atomId: string;
  frames: PropositionFrame[];
  cues: LinguisticCue[];
  entities: LinguisticEntity[];
  tokens: LinguisticToken[];
  status: "complete" | "partial";
  unresolved: Array<"subject" | "predicate">;
}

export type RoleAuditStatus = "MATCH" | "MISMATCH" | "INCONCLUSIVE";

export type LinguisticWarningCode =
  | "ROLE_CUE_MISMATCH"
  | "MULTIPLE_PROPOSITION_FRAMES"
  | "UNRESOLVED_SUBJECT"
  | "UNRESOLVED_PREDICATE"
  | "PARTIAL_LINGUISTIC_ANALYSIS"
  | "NEGATION_SCOPE_UNCLEAR"
  | "ATTRIBUTION_SCOPE_UNCLEAR"
  | "QUALIFIER_ATTACHMENT_UNCLEAR"
  | "NEGATION_NOT_PRESERVED"
  | "NUMERIC_INFORMATION_NOT_PRESERVED"
  | "TEMPORAL_INFORMATION_NOT_PRESERVED"
  | "ATTRIBUTION_NOT_PRESERVED"
  | "MODALITY_NOT_PRESERVED"
  | "LOCATION_NOT_PRESERVED"
  | "CLAIM_FRAME_NOT_COVERED";

export interface ObligationLinguisticSummary {
  atomId: string;
  analysisStatus: "complete" | "partial";
  roleAudit: RoleAuditStatus;
  subjects: string[];
  predicates: string[];
  cueKinds: LinguisticCueKind[];
  modifierKinds: LinguisticModifierKind[];
  entityLabels: string[];
  warnings: LinguisticWarningCode[];
}

export interface LinguisticAnalysisResponse {
  schemaVersion: 2;
  claimAnalysis: AtomLinguisticAnalysis;
  analyses: AtomLinguisticAnalysis[];
  summaries: ObligationLinguisticSummary[];
  claimWarnings: LinguisticWarningCode[];
  provider: "spacy";
  model: string;
}

/** A complete, local pipeline run rendered by the static Vercel walkthrough. */
export interface WalkthroughRun {
  caseId: string;
  schemaVersion: 6;
  composition: ClaimComposition;
  warnings: DecompositionWarning[];
  atoms: DecomposedAtom[];
  evidence: AtomEvidence[];
  assessment: GroundedEvidenceAssessment;
  reasoning: SymbolicExecution[];
  /** Legacy recorded walkthroughs contain only atom analyses; new runs use v2. */
  linguistics: LinguisticAnalysisResponse | AtomLinguisticAnalysis[];
  /** Recorded aggregation result. Absent in walkthroughs recorded before stage 05. */
  verdict?: VerdictAggregationResult;
  recordedWith: {
    pipelineRevision: "submission-ready-v2";
    inputDigest: string;
    decompositionModel: string;
    retrievalModel: string;
    retrievalMethod: RetrievalMethod;
    assessmentModel: string;
    reasoningModel: string;
    linguisticsModel: string;
  };
}

export interface Health {
  status: "ready" | "degraded" | "unconfigured";
  decompositionConfigured: boolean;
  decompositionReady: boolean;
  retrievalConfigured: boolean;
  linguisticsConfigured: boolean;
  decompositionModel: string;
  retrievalModel: string;
  linguisticsModel: string;
}

export type StageState = "idle" | "running" | "complete" | "error";
export type MobilePanel = "atoms" | "pipeline" | "document";
