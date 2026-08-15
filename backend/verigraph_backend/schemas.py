from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ReferenceLabel(str, Enum):
    supported = "SUPPORTED"
    refuted = "REFUTED"
    not_enough_evidence = "NOT_ENOUGH_EVIDENCE"
    conflicting_evidence = "CONFLICTING_EVIDENCE"


class DemoDocumentSummary(APIModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=4000)

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
            documents=[
                DemoDocumentSummary(id=document.id, title=document.title, url=document.url)
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


class DecomposedAtom(APIModel):
    id: str
    text: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class DecompositionResponse(APIModel):
    atoms: List[DecomposedAtom]
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


class EvidenceSpan(APIModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class AtomEvidence(APIModel):
    atom_id: str = Field(min_length=1)
    spans: List[EvidenceSpan] = Field(max_length=6)


class EvidenceRetrievalResponse(APIModel):
    evidence: List[AtomEvidence]
    provider: Literal["sentence-transformers"] = "sentence-transformers"
    model: str


class NLIInputSpan(APIModel):
    id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("id", "document_id", "text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value


class NLIAtomEvidence(APIModel):
    atom_id: str = Field(min_length=1, max_length=100)
    spans: List[NLIInputSpan] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def reject_duplicate_spans(self) -> "NLIAtomEvidence":
        span_ids = [(span.document_id, span.id) for span in self.spans]
        if len(span_ids) != len(set(span_ids)):
            raise ValueError("evidence spans must be unique within an atom")
        return self


class SupportClassificationRequest(APIModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )

    atoms: List[PipelineAtom] = Field(min_length=1, max_length=12)
    evidence: List[NLIAtomEvidence] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_atom_coverage(self) -> "SupportClassificationRequest":
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
        return self


class NLIRelation(str, Enum):
    entailment = "ENTAILMENT"
    contradiction = "CONTRADICTION"
    neutral = "NEUTRAL"


class EvidenceRelation(APIModel):
    span_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    relation: NLIRelation


class AtomSupportClassification(APIModel):
    atom_id: str = Field(min_length=1)
    relations: List[EvidenceRelation] = Field(max_length=6)


class SupportClassificationResponse(APIModel):
    classifications: List[AtomSupportClassification]
    provider: Literal["transformers"] = "transformers"
    model: str


class LinguisticAnalysisRequest(APIModel):
    atoms: List[PipelineAtom] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def reject_duplicate_atom_ids(self) -> "LinguisticAnalysisRequest":
        atom_ids = [atom.id for atom in self.atoms]
        if len(atom_ids) != len(set(atom_ids)):
            raise ValueError("atom IDs must be unique")
        return self


class LinguisticSpan(APIModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class LinguisticArgument(LinguisticSpan):
    role: Literal[
        "direct_object",
        "indirect_object",
        "passive_agent",
        "subject_complement",
        "object_complement",
        "clausal_complement",
    ]


class LinguisticModifier(LinguisticSpan):
    kind: Literal[
        "temporal",
        "locative",
        "manner",
        "causal",
        "conditional",
        "purpose",
    ]


class PropositionFrame(APIModel):
    id: str = Field(min_length=1)
    predicate: Optional[LinguisticSpan] = None
    subjects: List[LinguisticSpan] = Field(default_factory=list)
    core_arguments: List[LinguisticArgument] = Field(default_factory=list)
    adjuncts: List[LinguisticModifier] = Field(default_factory=list)
    other_modifiers: List[LinguisticSpan] = Field(default_factory=list)


class LinguisticCue(LinguisticSpan):
    kind: Literal[
        "negation",
        "quantifier",
        "modality",
        "attribution",
        "temporal",
        "numeric",
    ]


class LinguisticEntity(LinguisticSpan):
    label: str = Field(min_length=1)


class LinguisticToken(LinguisticSpan):
    lemma: str
    pos: str
    tag: str
    dependency: str
    head: str


class AtomLinguisticAnalysis(APIModel):
    atom_id: str = Field(min_length=1)
    frames: List[PropositionFrame]
    cues: List[LinguisticCue]
    entities: List[LinguisticEntity]
    tokens: List[LinguisticToken]
    status: Literal["complete", "partial"]
    unresolved: List[Literal["subject", "predicate"]]


class LinguisticAnalysisResponse(APIModel):
    analyses: List[AtomLinguisticAnalysis]
    provider: Literal["spacy"] = "spacy"
    model: str


class HealthResponse(APIModel):
    status: Literal["configured", "unconfigured"]
    decomposition_configured: bool
    retrieval_configured: bool
    nli_configured: bool
    linguistics_configured: bool
    decomposition_model: str
    retrieval_model: str
    nli_model: str
    linguistics_model: str
    model_config = ConfigDict(extra="forbid")
