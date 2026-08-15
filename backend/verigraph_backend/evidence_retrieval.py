from __future__ import annotations

from collections import Counter
import re
from typing import List, Optional, Sequence

from . import embeddings
from .errors import EvidenceRetrievalConfigurationError, EvidenceRetrievalError
from .schemas import (
    AtomEvidence,
    EvidenceRetrievalResponse,
    EvidenceSpan,
    RetrievalAtom,
    RetrievalDocument,
)
from .segmentation import SentenceSpan, segment_document, segment_documents
from .settings import settings
from .text_offsets import utf16_offset


MAX_EVIDENCE_PER_ATOM = 6
MAX_EVIDENCE_PER_DOCUMENT = 3
MAX_CANDIDATE_CHARACTERS = 1_000
MIN_HEADING_WORDS = 5
_LEXICAL_WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
_LIST_PREFIX = re.compile(r"^(?:[-*•]|\d+[.)])\s+")


def _is_sentence_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    word_count = len(_LEXICAL_WORD.findall(stripped))
    if word_count >= MIN_HEADING_WORDS or stripped.endswith((".", "?", "!")):
        return True
    # Short explicit list entries remain available for the future symbolic stage.
    return bool(_LIST_PREFIX.match(stripped))


def _eligible_sentences(sentences: Sequence[SentenceSpan]) -> List[SentenceSpan]:
    """Remove blank and pathological extraction fragments before embedding."""
    return [
        sentence
        for sentence in sentences
        if len(sentence.text) <= MAX_CANDIDATE_CHARACTERS
        and _is_sentence_like(sentence.text)
    ]


def _rank_sentences(
    sentences: Sequence[SentenceSpan], scores: Sequence[float]
) -> List[SentenceSpan]:
    if len(scores) != len(sentences):
        raise EvidenceRetrievalError(
            "The embedding model returned an invalid evidence score matrix."
        )

    document_count = len({sentence.document_id for sentence in sentences})
    per_document_limit = (
        MAX_EVIDENCE_PER_ATOM
        if document_count <= 1
        else MAX_EVIDENCE_PER_DOCUMENT
    )
    ranked_indices = sorted(
        range(len(sentences)), key=lambda index: (-scores[index], index)
    )
    selected: List[SentenceSpan] = []
    counts: Counter[str] = Counter()
    for index in ranked_indices:
        sentence = sentences[index]
        if counts[sentence.document_id] >= per_document_limit:
            continue
        selected.append(sentence)
        counts[sentence.document_id] += 1
        if len(selected) >= MAX_EVIDENCE_PER_ATOM:
            break
    return selected


def _span(sentence: SentenceSpan, documents_by_id: dict[str, str]) -> EvidenceSpan:
    document = documents_by_id.get(sentence.document_id)
    if document is None or document[sentence.start : sentence.end] != sentence.text:
        raise EvidenceRetrievalError(
            "A selected evidence sentence no longer matches its source document."
        )
    return EvidenceSpan(
        id=sentence.id,
        document_id=sentence.document_id,
        text=sentence.text,
        start=utf16_offset(document, sentence.start),
        end=utf16_offset(document, sentence.end),
    )


async def retrieve_evidence(
    documents: Sequence[RetrievalDocument],
    atoms: Sequence[RetrievalAtom],
    *,
    prepared_cache_key: Optional[str] = None,
) -> EvidenceRetrievalResponse:
    if not settings.embedding_model_path.is_dir():
        raise EvidenceRetrievalConfigurationError(
            "The local evidence embedding model is missing. Run ./run-verigraph --prepare."
        )

    sentences = _eligible_sentences(segment_documents(documents))
    if not sentences:
        return EvidenceRetrievalResponse(
            evidence=[AtomEvidence(atom_id=atom.id, spans=[]) for atom in atoms],
            model=settings.embedding_model,
        )

    score_matrix = await embeddings.similarity_matrix(
        [atom.text for atom in atoms],
        [sentence.text for sentence in sentences],
        cache_key=prepared_cache_key,
    )
    if len(score_matrix) != len(atoms):
        raise EvidenceRetrievalError(
            "The embedding model returned an invalid evidence score matrix."
        )

    documents_by_id = {document.id: document.text for document in documents}
    evidence: List[AtomEvidence] = []
    for atom, scores in zip(atoms, score_matrix):
        evidence.append(
            AtomEvidence(
                atom_id=atom.id,
                spans=[
                    _span(sentence, documents_by_id)
                    for sentence in _rank_sentences(sentences, scores)
                ],
            )
        )
    return EvidenceRetrievalResponse(
        evidence=evidence,
        model=settings.embedding_model,
    )
