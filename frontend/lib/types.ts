export type ReferenceLabel =
  | "SUPPORTED"
  | "REFUTED"
  | "NOT_ENOUGH_EVIDENCE"
  | "CONFLICTING_EVIDENCE";

export interface DemoDocumentSummary {
  id: string;
  title: string;
  url: string;
}

export interface DemoDocument extends DemoDocumentSummary {
  text: string;
}

export interface DemoCaseSummary {
  id: string;
  claim: string;
  documents: DemoDocumentSummary[];
  label: ReferenceLabel;
}

export interface DemoCase {
  id: string;
  claim: string;
  documents: DemoDocument[];
  label: ReferenceLabel;
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
}

export interface AtomEvidence {
  atomId: string;
  spans: EvidenceSpan[];
}

export interface EvidenceRetrievalResponse {
  evidence: AtomEvidence[];
  provider: "sentence-transformers";
  model: string;
}

export type NLIRelation = "ENTAILMENT" | "CONTRADICTION" | "NEUTRAL";

export interface EvidenceRelation {
  spanId: string;
  documentId: string;
  relation: NLIRelation;
}

export interface AtomSupportClassification {
  atomId: string;
  relations: EvidenceRelation[];
}

export type ArgumentationNodeType =
  | "CASE_CLAIM"
  | "VERIFICATION_OBLIGATION"
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
  linguistic?: ObligationLinguisticSummary;
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
}

export type ArgumentationNode =
  | CaseClaimNode
  | VerificationObligationNode
  | EvidenceNode;

export type ArgumentationEdgeType = "DECOMPOSES_TO" | "SUPPORTS" | "ATTACKS";

export interface ArgumentationEdge {
  id: string;
  source: string;
  target: string;
  type: ArgumentationEdgeType;
  /** Present only on NLI-derived support and attack edges. */
  nli?: { label: "ENTAILMENT" | "CONTRADICTION" };
}

export type GraphWarningCode =
  | "MISSING_LINGUISTIC_SUMMARY"
  | "MISSING_EVIDENCE"
  | "MISSING_OBLIGATION"
  | "DUPLICATE_NODE_ID"
  | "DUPLICATE_EDGE_ID"
  | "UNSUPPORTED_NLI_LABEL"
  | "INVALID_SOURCE_OFFSETS"
  | "EMPTY_OBLIGATION_TEXT";

export interface GraphWarning {
  code: GraphWarningCode;
  message: string;
}

export interface GraphStats {
  obligationCount: number;
  evidenceCount: number;
  supportEdgeCount: number;
  attackEdgeCount: number;
  omittedNeutralCount: number;
  obligationsWithoutArgumentEdges: number;
}

export interface ArgumentationGraph {
  schemaVersion: 2;
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
  attackEdgeIds: string[];
  neutralCandidateCount: number;
}

export interface VerdictAggregationResult {
  aggregationSchemaVersion: 1;
  claimId: string;
  composition: ClaimComposition;
  verdict: ReferenceLabel;
  positions: {
    supportPosition: boolean;
    attackPosition: boolean;
    supportObligationIds: string[];
    attackObligationIds: string[];
    unresolvedObligationIds: string[];
  };
  obligations: VerdictObligationSummary[];
  warnings: Array<{ code: string; message: string }>;
  ruleTrace: string[];
}

export interface SupportClassificationResponse {
  classifications: AtomSupportClassification[];
  provider: "transformers";
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
  schemaVersion: 2;
  composition: ClaimComposition;
  warnings: DecompositionWarning[];
  atoms: DecomposedAtom[];
  evidence: AtomEvidence[];
  classifications: AtomSupportClassification[];
  /** Legacy recorded walkthroughs contain only atom analyses; new runs use v2. */
  linguistics: LinguisticAnalysisResponse | AtomLinguisticAnalysis[];
  recordedWith: {
    decompositionModel: string;
    retrievalModel: string;
    nliModel: string;
    linguisticsModel: string;
  };
}

export interface Health {
  status: "configured" | "unconfigured";
  decompositionConfigured: boolean;
  retrievalConfigured: boolean;
  nliConfigured: boolean;
  linguisticsConfigured: boolean;
  decompositionModel: string;
  retrievalModel: string;
  nliModel: string;
  linguisticsModel: string;
}

export type StageState = "idle" | "running" | "complete" | "error";
export type MobilePanel = "atoms" | "pipeline" | "document";
