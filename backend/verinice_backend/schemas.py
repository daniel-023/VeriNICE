from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


#: Retrieval budget per obligation. The operator chooses a value in this range;
#: retrieval and evidence assessment both size their span lists from it.
MIN_EVIDENCE_PER_ATOM = 1
MAX_EVIDENCE_PER_ATOM = 12
DEFAULT_EVIDENCE_PER_ATOM = 6


class RetrievalMethod(str, Enum):
    hybrid = "HYBRID"
    semantic = "SEMANTIC"
    lexical = "LEXICAL"


class ReferenceLabel(str, Enum):
    supported = "SUPPORTED"
    refuted = "REFUTED"
    not_enough_evidence = "NOT_ENOUGH_EVIDENCE"
    conflicting_evidence = "CONFLICTING_EVIDENCE"


class DemoTopic(str, Enum):
    politics_elections = "POLITICS_ELECTIONS"
    public_health = "PUBLIC_HEALTH"
    climate_environment = "CLIMATE_ENVIRONMENT"
    economy_business = "ECONOMY_BUSINESS"
    science_technology = "SCIENCE_TECHNOLOGY"
    law_public_policy = "LAW_PUBLIC_POLICY"
    conflict_security = "CONFLICT_SECURITY"
    society_culture = "SOCIETY_CULTURE"


class DemoOrigin(str, Enum):
    constructed = "CONSTRUCTED"
    averitec = "AVERITEC"


class DemoCategory(str, Enum):
    science = "SCIENCE"
    history = "HISTORY"
    geography = "GEOGRAPHY"
    technology = "TECHNOLOGY"
    current_affairs = "CURRENT_AFFAIRS"


class DemoFocus(str, Enum):
    decomposition = "DECOMPOSITION"
    direct_evidence = "DIRECT_EVIDENCE"
    numeric_comparison = "NUMERIC_COMPARISON"
    attribute_comparison = "ATTRIBUTE_COMPARISON"
    temporal_comparison = "TEMPORAL_COMPARISON"
    set_membership = "SET_MEMBERSHIP"
    distinct_value_count = "DISTINCT_VALUE_COUNT"
    extremum = "EXTREMUM"
    insufficient_evidence = "INSUFFICIENT_EVIDENCE"
    conflicting_evidence = "CONFLICTING_EVIDENCE"


class DemoSourceType(str, Enum):
    source_excerpt = "SOURCE_EXCERPT"
    full_source = "FULL_SOURCE"


class DemoChallenge(str, Enum):
    multi_part = "MULTI_PART"
    negation = "NEGATION"
    numbers = "NUMBERS"
    time = "TIME"
    attribution = "ATTRIBUTION"
    causality = "CAUSALITY"
    list_set_reasoning = "LIST_SET_REASONING"
    conflicting_sources = "CONFLICTING_SOURCES"
    sparse_evidence = "SPARSE_EVIDENCE"


class ClaimComposition(str, Enum):
    """Flat logical composition supported by decomposition schema version 2."""

    single = "SINGLE"
    and_ = "AND"
    or_ = "OR"


class ObligationRole(str, Enum):
    core = "CORE"
    numeric_constraint = "NUMERIC_CONSTRAINT"
    temporal_constraint = "TEMPORAL_CONSTRAINT"
    attribution = "ATTRIBUTION"
    location_constraint = "LOCATION_CONSTRAINT"
    causal_relation = "CAUSAL_RELATION"
    conditional = "CONDITIONAL"
    modality_constraint = "MODALITY_CONSTRAINT"


class DocumentLayout(str, Enum):
    prose = "PROSE"
    structured_list = "STRUCTURED_LIST"


class DemoDocumentSummary(APIModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=4000)
    layout: DocumentLayout = DocumentLayout.prose
    publisher: str = Field(default="", max_length=200)
    retrieved_at: Optional[str] = Field(default=None, max_length=40)
    source_type: DemoSourceType = DemoSourceType.full_source
    source_descriptor: str = Field(default="", max_length=120)
    excerpt_rationale: str = Field(default="", max_length=500)
    excerpt_sha256: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_sha256: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("id", "title", "url")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value


class DemoDocument(DemoDocumentSummary):
    text: str = Field(min_length=1, max_length=250000)

    @field_validator("text")
    @classmethod
    def reject_blank_document(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document text cannot be blank")
        return value


class DemoCaseSummary(APIModel):
    id: str = Field(min_length=1, max_length=100)
    claim: str = Field(min_length=1, max_length=5000)
    documents: List[DemoDocumentSummary] = Field(min_length=1, max_length=8)
    label: ReferenceLabel
    display_title: str = Field(default="", max_length=120)
    topics: List[DemoTopic] = Field(default_factory=list, max_length=3)
    challenges: List[DemoChallenge] = Field(default_factory=list, max_length=6)
    featured: bool = False
    origin: DemoOrigin = DemoOrigin.averitec
    category: Optional[DemoCategory] = None
    demo_focus: Optional[DemoFocus] = None

    @field_validator("id", "claim")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value

    @model_validator(mode="after")
    def reject_duplicate_document_ids(self) -> "DemoCaseSummary":
        document_ids = [document.id for document in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document IDs must be unique within a case")
        return self


class DemoCase(APIModel):
    id: str = Field(min_length=1, max_length=100)
    claim: str = Field(min_length=1, max_length=5000)
    documents: List[DemoDocument] = Field(min_length=1, max_length=8)
    label: ReferenceLabel
    display_title: str = Field(default="", max_length=120)
    topics: List[DemoTopic] = Field(default_factory=list, max_length=3)
    challenges: List[DemoChallenge] = Field(default_factory=list, max_length=6)
    featured: bool = False
    origin: DemoOrigin = DemoOrigin.averitec
    category: Optional[DemoCategory] = None
    demo_focus: Optional[DemoFocus] = None

    @field_validator("id", "claim")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value

    @model_validator(mode="after")
    def reject_duplicate_document_ids(self) -> "DemoCase":
        document_ids = [document.id for document in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document IDs must be unique within a case")
        return self

    def summary(self) -> DemoCaseSummary:
        return DemoCaseSummary(
            id=self.id,
            claim=self.claim,
            label=self.label,
            display_title=self.display_title,
            topics=self.topics,
            challenges=self.challenges,
            featured=self.featured,
            origin=self.origin,
            category=self.category,
            demo_focus=self.demo_focus,
            documents=[
                DemoDocumentSummary(
                    id=document.id, title=document.title, url=document.url,
                    layout=document.layout,
                    publisher=document.publisher,
                    retrieved_at=document.retrieved_at,
                    source_type=document.source_type,
                    source_descriptor=document.source_descriptor,
                    excerpt_rationale=document.excerpt_rationale,
                    excerpt_sha256=document.excerpt_sha256,
                    source_sha256=document.source_sha256,
                )
                for document in self.documents
            ],
        )


class DecompositionRequest(APIModel):
    claim: str = Field(min_length=1, max_length=5000)

    @field_validator("claim")
    @classmethod
    def reject_blank_claim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim cannot be blank")
        return value


class ObligationDraft(APIModel):
    """Semantic content returned by the decomposition model."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    text: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    role: ObligationRole


class ClaimDecompositionDraft(APIModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    composition: ClaimComposition
    obligations: List[ObligationDraft] = Field(min_length=1, max_length=12)


class DecompositionWarning(APIModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)


class DecomposedAtom(APIModel):
    id: str
    text: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    role: ObligationRole

    @field_validator("id", "text", "source_text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value


class DecompositionResponse(APIModel):
    schema_version: Literal[2] = 2
    composition: ClaimComposition
    atoms: List[DecomposedAtom] = Field(min_length=1, max_length=12)
    warnings: List[DecompositionWarning] = Field(default_factory=list)
    provider: Literal["ollama"] = "ollama"
    model: str


class PipelineAtom(APIModel):
    id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("id", "text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value


RetrievalAtom = PipelineAtom


class RetrievalDocument(APIModel):
    id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=250000)
    title: str = Field(default="", max_length=300)

    @field_validator("id", "text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value


class RetrievalRequest(APIModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )

    case_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    documents: Optional[List[RetrievalDocument]] = Field(
        default=None, min_length=1, max_length=8
    )
    atoms: List[PipelineAtom] = Field(min_length=1, max_length=12)
    evidence_per_atom: int = Field(
        default=DEFAULT_EVIDENCE_PER_ATOM,
        ge=MIN_EVIDENCE_PER_ATOM,
        le=MAX_EVIDENCE_PER_ATOM,
    )
    retrieval_method: RetrievalMethod = RetrievalMethod.hybrid

    @model_validator(mode="after")
    def validate_input_mode_and_ids(self) -> "RetrievalRequest":
        if (self.case_id is None) == (self.documents is None):
            raise ValueError("provide exactly one of caseId or documents")
        atom_ids = [atom.id for atom in self.atoms]
        if len(atom_ids) != len(set(atom_ids)):
            raise ValueError("atom IDs must be unique")
        if self.documents is not None:
            document_ids = [document.id for document in self.documents]
            if len(document_ids) != len(set(document_ids)):
                raise ValueError("document IDs must be unique")
            if sum(len(document.text) for document in self.documents) > 1_000_000:
                raise ValueError("combined document text is too large")
        return self


class EvidenceContextSpan(APIModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=1000)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    direction: Literal["PREVIOUS", "NEXT"]


class EvidenceSpan(APIModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    #: Explicit, source-grounded sentences used only to interpret the anchor.
    context_spans: List[EvidenceContextSpan] = Field(default_factory=list, max_length=2)
    #: Backward-compatible assembled premise for recorded runs and classifiers.
    context: Optional[str] = Field(default=None, max_length=4000)


class AtomEvidence(APIModel):
    atom_id: str = Field(min_length=1)
    spans: List[EvidenceSpan] = Field(max_length=MAX_EVIDENCE_PER_ATOM)


class EvidenceRetrievalResponse(APIModel):
    evidence: List[AtomEvidence]
    provider: Literal["sentence-transformers", "python"] = "sentence-transformers"
    model: str
    retrieval_method: RetrievalMethod = RetrievalMethod.hybrid


class AssessmentInputSpan(APIModel):
    id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    start: int = Field(default=0, ge=0)
    end: int = Field(default=1, gt=0)
    context_spans: List[EvidenceContextSpan] = Field(default_factory=list, max_length=2)
    context: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("id", "document_id", "text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value


class AssessmentAtomEvidence(APIModel):
    atom_id: str = Field(min_length=1, max_length=100)
    spans: List[AssessmentInputSpan] = Field(default_factory=list, max_length=MAX_EVIDENCE_PER_ATOM)

    @model_validator(mode="after")
    def reject_duplicate_spans(self) -> "AssessmentAtomEvidence":
        span_ids = [(span.document_id, span.id) for span in self.spans]
        if len(span_ids) != len(set(span_ids)):
            raise ValueError("evidence spans must be unique within an atom")
        return self


class EvidenceAssessmentRequest(APIModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )

    atoms: List[PipelineAtom] = Field(min_length=1, max_length=12)
    evidence: List[AssessmentAtomEvidence] = Field(min_length=1, max_length=12)
    claim: str = Field(min_length=1, max_length=5000)
    case_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    documents: Optional[List[DemoDocument]] = Field(default=None, min_length=1, max_length=8)

    @field_validator("claim")
    @classmethod
    def reject_blank_claim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_atom_coverage(self) -> "EvidenceAssessmentRequest":
        if (self.case_id is None) == (self.documents is None):
            raise ValueError("provide exactly one of caseId or documents")
        atom_ids = [atom.id for atom in self.atoms]
        evidence_atom_ids = [item.atom_id for item in self.evidence]
        if len(atom_ids) != len(set(atom_ids)):
            raise ValueError("atom IDs must be unique")
        if len(evidence_atom_ids) != len(set(evidence_atom_ids)):
            raise ValueError("each atom must have exactly one evidence group")
        if set(evidence_atom_ids) != set(atom_ids):
            raise ValueError("evidence must cover every atom exactly once")
        if sum(len(item.spans) for item in self.evidence) > 72:
            raise ValueError("too many atom-evidence pairs")
        if self.documents is not None:
            document_ids = [document.id for document in self.documents]
            if len(document_ids) != len(set(document_ids)):
                raise ValueError("document IDs must be unique")
            if sum(len(document.text) for document in self.documents) > 1_000_000:
                raise ValueError("combined document text is too large")
            evidence_document_ids = {
                span.document_id for group in self.evidence for span in group.spans
            }
            if not evidence_document_ids.issubset(document_ids):
                raise ValueError("evidence references an unknown document")
        return self


class EvidenceScopeStatus(str, Enum):
    match = "MATCH"
    mismatch = "MISMATCH"
    unresolved = "UNRESOLVED"
    not_applicable = "NOT_APPLICABLE"


class EvidenceScopeCheck(APIModel):
    span_id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=100)
    status: EvidenceScopeStatus
    claim_jurisdictions: List[str] = Field(default_factory=list, max_length=12)
    evidence_jurisdictions: List[str] = Field(default_factory=list, max_length=12)
    reason: str = Field(min_length=1, max_length=300)


class IdentityAlignmentStatus(str, Enum):
    aligned = "ALIGNED"
    unresolved = "UNRESOLVED"
    not_applicable = "NOT_APPLICABLE"


class IdentityAlignmentCheck(APIModel):
    relation: Literal["SUPPORTS", "REFUTES"]
    span_ids: List[str] = Field(default_factory=list, max_length=3)
    status: IdentityAlignmentStatus
    required_entities: List[str] = Field(default_factory=list, max_length=20)
    matched_entities: List[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=1, max_length=500)


class GroundedObligationAudit(APIModel):
    atom_id: str = Field(min_length=1, max_length=100)
    support_span_ids: List[str] = Field(default_factory=list, max_length=3)
    refute_span_ids: List[str] = Field(default_factory=list, max_length=3)
    context_span_ids: List[str] = Field(default_factory=list, max_length=3)
    sufficiency: Literal["SUFFICIENT", "PARTIAL", "INSUFFICIENT"] = "INSUFFICIENT"
    missing_information: str = Field(default="", max_length=500)
    reason: str = Field(min_length=1, max_length=500)
    scope_checks: List[EvidenceScopeCheck] = Field(default_factory=list, max_length=MAX_EVIDENCE_PER_ATOM)
    identity_checks: List[IdentityAlignmentCheck] = Field(default_factory=list, max_length=2)


class MaterialOmissionCertificate(APIModel):
    detected: bool = False
    support_span_ids: List[str] = Field(default_factory=list, max_length=3)
    context_span_ids: List[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(default="No material omission was established.", min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_two_sided_grounding_when_detected(self) -> "MaterialOmissionCertificate":
        if self.detected and (not self.support_span_ids or not self.context_span_ids):
            raise ValueError("detected material omission requires support and context spans")
        if not self.detected and (self.support_span_ids or self.context_span_ids):
            raise ValueError("undetected material omission cannot retain evidence spans")
        return self


class GroundedEvidenceAssessment(APIModel):
    obligations: List[GroundedObligationAudit] = Field(min_length=1, max_length=12)
    material_omission: MaterialOmissionCertificate


class EvidenceAssessmentResponse(APIModel):
    assessment: GroundedEvidenceAssessment
    provider: Literal["ollama"] = "ollama"
    model: str


class CandidateRelation(str, Enum):
    supports = "SUPPORTS"
    refutes = "REFUTES"
    context = "CONTEXT"
    not_selected = "NOT_SELECTED"


class SymbolicOperator(str, Enum):
    set_membership = "SET_MEMBERSHIP"
    numeric_compare = "NUMERIC_COMPARE"
    temporal_compare = "TEMPORAL_COMPARE"
    attribute_compare = "ATTRIBUTE_COMPARE"
    count_distinct = "COUNT_DISTINCT"
    extremum_compare = "EXTREMUM_COMPARE"


class SymbolicStatus(str, Enum):
    proved = "PROVED"
    disproved = "DISPROVED"
    unresolved = "UNRESOLVED"
    not_applicable = "NOT_APPLICABLE"


class SymbolicPrecondition(APIModel):
    name: str = Field(min_length=1, max_length=120)
    status: Literal["PASSED", "FAILED", "UNRESOLVED"]
    detail: str = Field(min_length=1, max_length=500)


class SymbolicListItem(APIModel):
    id: str = Field(min_length=1, max_length=240)
    document_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    content_hash: str = Field(min_length=64, max_length=64)


class SymbolicPremise(APIModel):
    id: str = Field(min_length=1, max_length=240)
    document_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=5000)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    kind: Literal["EVIDENCE", "LIST_CERTIFICATE", "LIST_ITEM", "OPERAND"]
    content_hash: Optional[str] = None
    item_count: Optional[int] = Field(default=None, ge=0)
    list_items: List[SymbolicListItem] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_list_items(self) -> "SymbolicPremise":
        if self.list_items and self.kind != "LIST_CERTIFICATE":
            raise ValueError("only a list certificate may expose associated list items")
        if self.list_items:
            if self.item_count != len(self.list_items):
                raise ValueError("list certificate itemCount must match its displayed items")
            if any(item.document_id != self.document_id for item in self.list_items):
                raise ValueError("displayed list items must come from the certificate document")
            if any(item.content_hash != self.content_hash for item in self.list_items):
                raise ValueError("displayed list items must match the certificate content hash")
            if self.list_items != sorted(self.list_items, key=lambda item: (item.start, item.end, item.id)):
                raise ValueError("displayed list items must retain source order")
        return self


class ProgramStep(APIModel):
    id: str = Field(min_length=1, max_length=100)
    operation: Literal[
        "LOOKUP",
        "EQUAL",
        "NOT_EQUAL",
        "NUMERIC_COMPARE",
        "TEMPORAL_COMPARE",
        "MEMBER",
        "COUNT_DISTINCT",
        "EXTREMUM_COUNTEREXAMPLE",
    ]
    input_ids: List[str] = Field(min_length=1, max_length=20)
    output_type: Literal["FACT", "BOOLEAN", "NUMBER", "DATE", "SET"]
    description: str = Field(min_length=1, max_length=300)


class SymbolicProgram(APIModel):
    version: Literal[1] = 1
    steps: List[ProgramStep] = Field(min_length=1, max_length=12)
    output_step_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_program(self) -> "SymbolicProgram":
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("program step IDs must be unique")
        if self.output_step_id not in step_ids:
            raise ValueError("outputStepId must reference a program step")
        return self


class SymbolicExecution(APIModel):
    id: str = Field(min_length=1, max_length=200)
    atom_id: str = Field(min_length=1, max_length=100)
    operator: SymbolicOperator
    profile: str = Field(min_length=1, max_length=120)
    status: SymbolicStatus
    relation: Optional[Literal["SUPPORTS", "REFUTES"]] = None
    premise_ids: List[str] = Field(default_factory=list, max_length=20)
    premises: List[SymbolicPremise] = Field(default_factory=list, max_length=20)
    expression: str = Field(min_length=1, max_length=1000)
    conclusion: str = Field(min_length=1, max_length=1000)
    explanation: str = Field(min_length=1, max_length=1200)
    validation_warnings: List[str] = Field(default_factory=list, max_length=12)
    preconditions: List[SymbolicPrecondition] = Field(default_factory=list, max_length=12)
    program: SymbolicProgram

    @model_validator(mode="after")
    def validate_effect(self) -> "SymbolicExecution":
        if self.status in {SymbolicStatus.proved, SymbolicStatus.disproved} and self.relation is None:
            raise ValueError("resolved symbolic executions require a relation")
        if self.status in {SymbolicStatus.unresolved, SymbolicStatus.not_applicable} and self.relation is not None:
            raise ValueError("unresolved symbolic executions cannot add a relation")
        if self.premise_ids != [premise.id for premise in self.premises]:
            raise ValueError("premiseIds must match the ordered grounded premises")
        return self


class ReasoningRequest(APIModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    case_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    documents: Optional[List[RetrievalDocument]] = Field(default=None, min_length=1, max_length=8)
    claim: str = Field(min_length=1, max_length=5000)
    atoms: List[PipelineAtom] = Field(min_length=1, max_length=12)
    evidence: List[AssessmentAtomEvidence] = Field(min_length=1, max_length=12)
    assessment: GroundedEvidenceAssessment

    @model_validator(mode="after")
    def validate_reasoning_input(self) -> "ReasoningRequest":
        if (self.case_id is None) == (self.documents is None):
            raise ValueError("provide exactly one of caseId or documents")
        atom_ids = [atom.id for atom in self.atoms]
        if len(atom_ids) != len(set(atom_ids)):
            raise ValueError("atom IDs must be unique")
        evidence_ids = [item.atom_id for item in self.evidence]
        if evidence_ids != atom_ids:
            raise ValueError("evidence must follow atom order and cover every atom")
        assessment_ids = [item.atom_id for item in self.assessment.obligations]
        if set(assessment_ids) != set(atom_ids) or len(assessment_ids) != len(atom_ids):
            raise ValueError("assessment must cover every atom exactly once")
        return self


class ReasoningResponse(APIModel):
    executions: List[SymbolicExecution]
    provider: Literal["ollama+python"] = "ollama+python"
    model: str


class HealthResponse(APIModel):
    status: Literal["ready", "degraded", "unconfigured"]
    decomposition_configured: bool
    decomposition_ready: bool
    retrieval_configured: bool
    entity_alignment_ready: bool
    decomposition_model: str
    retrieval_model: str
    entity_model: str
    model_config = ConfigDict(extra="forbid")


class ObligationEvidenceState(str, Enum):
    supported = "SUPPORTED"
    refuted = "REFUTED"
    conflicting = "CONFLICTING"
    unresolved = "UNRESOLVED"


class AggregationWarning(APIModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)


class ClaimEvidencePositions(APIModel):
    support_position: bool
    refute_position: bool
    material_omission_position: bool = False
    support_obligation_ids: List[str] = Field(default_factory=list)
    refute_obligation_ids: List[str] = Field(default_factory=list)
    unresolved_obligation_ids: List[str] = Field(default_factory=list)


class ObligationEvidenceSummary(APIModel):
    obligation_id: str = Field(min_length=1)
    state: ObligationEvidenceState
    support_edge_ids: List[str] = Field(default_factory=list)
    refute_edge_ids: List[str] = Field(default_factory=list)
    unselected_candidate_count: int = Field(ge=0)
    provisional_relation_count: int = Field(default=0, ge=0)


class VerdictAggregationRequest(APIModel):
    """Validated completed pipeline inputs; the reference label is deliberately absent."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    claim_id: str = Field(min_length=1, max_length=100)
    composition: ClaimComposition
    atoms: List[DecomposedAtom] = Field(min_length=1, max_length=12)
    evidence: List[AtomEvidence] = Field(min_length=1, max_length=12)
    assessment: GroundedEvidenceAssessment
    reasoning: List[SymbolicExecution] = Field(default_factory=list, max_length=36)

    @model_validator(mode="after")
    def validate_atom_coverage(self) -> "VerdictAggregationRequest":
        atom_ids = [atom.id for atom in self.atoms]
        evidence_ids = [item.atom_id for item in self.evidence]
        if len(atom_ids) != len(set(atom_ids)):
            raise ValueError("decomposition atom IDs must be unique")
        if set(evidence_ids) != set(atom_ids) or len(evidence_ids) != len(atom_ids):
            raise ValueError("evidence must cover every decomposition atom exactly once")
        assessment_ids = [item.atom_id for item in self.assessment.obligations]
        if set(assessment_ids) != set(atom_ids) or len(assessment_ids) != len(atom_ids):
            raise ValueError("assessment must cover every decomposition atom exactly once")
        if any(item.atom_id not in atom_ids for item in self.reasoning):
            raise ValueError("symbolic executions must reference decomposition atoms")
        return self


class VerdictAggregationResult(APIModel):
    aggregation_schema_version: Literal[3] = 3
    claim_id: str
    composition: ClaimComposition
    verdict: ReferenceLabel
    positions: ClaimEvidencePositions
    obligations: List[ObligationEvidenceSummary]
    warnings: List[AggregationWarning] = Field(default_factory=list)
    rule_trace: List[str] = Field(default_factory=list)
