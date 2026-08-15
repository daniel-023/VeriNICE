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
}

export interface DecompositionResponse {
  atoms: DecomposedAtom[];
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

export interface LinguisticAnalysisResponse {
  analyses: AtomLinguisticAnalysis[];
  provider: "spacy";
  model: string;
}

/** A complete, local pipeline run rendered by the static Vercel walkthrough. */
export interface WalkthroughRun {
  caseId: string;
  atoms: DecomposedAtom[];
  evidence: AtomEvidence[];
  classifications: AtomSupportClassification[];
  linguistics: AtomLinguisticAnalysis[];
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
