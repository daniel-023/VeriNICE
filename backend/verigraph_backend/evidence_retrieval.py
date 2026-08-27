from __future__ import annotations

from collections import Counter
from math import ceil
import re
from typing import List, Optional, Sequence

from . import embeddings
from .errors import EvidenceRetrievalConfigurationError, EvidenceRetrievalError
from .schemas import (
    DEFAULT_EVIDENCE_PER_ATOM,
    AtomEvidence,
    EvidenceRetrievalResponse,
    EvidenceSpan,
    RetrievalAtom,
    RetrievalDocument,
)
from .segmentation import SentenceSpan, segment_document, segment_documents
from .settings import settings
from .text_offsets import utf16_offset


MAX_CANDIDATE_CHARACTERS = 1_000
MIN_HEADING_WORDS = 5
_LEXICAL_WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
_LIST_PREFIX = re.compile(r"^(?:[-*•]|\d+[.)])\s+")
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)*(?:%|\b)")


def _lexical_terms(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _LEXICAL_WORD.findall(text)
        if len(token) > 2
    }


def _lexical_score(query: str, passage: str) -> float:
    """Return an auditable exact-match signal alongside dense similarity.

    Dense retrieval handles paraphrases well but can miss names, dates, numbers,
    and terse list entries.  This score deliberately rewards those anchors and
    does not attempt to make a truth judgment.
    """
    query_terms = _lexical_terms(query)
    passage_terms = _lexical_terms(passage)
    overlap = query_terms & passage_terms
    coverage = len(overlap) / max(1, len(query_terms))
    exact_numbers = set(_NUMBER.findall(query)) & set(_NUMBER.findall(passage))
    list_bonus = 0.15 if _LIST_PREFIX.match(passage.strip()) and overlap else 0.0
    return coverage + min(0.3, 0.1 * len(exact_numbers)) + list_bonus


def _reciprocal_rank_fusion(primary: Sequence[float], secondary: Sequence[float]) -> List[float]:
    if len(primary) != len(secondary):
        raise EvidenceRetrievalError("The embedding model returned an invalid evidence score matrix.")
    primary_order = sorted(range(len(primary)), key=lambda index: (-primary[index], index))
    secondary_order = sorted(range(len(secondary)), key=lambda index: (-secondary[index], index))
    primary_rank = {index: rank for rank, index in enumerate(primary_order, start=1)}
    secondary_rank = {index: rank for rank, index in enumerate(secondary_order, start=1)}
    return [
        1 / (60 + primary_rank[index]) + 1.2 / (60 + secondary_rank[index])
        for index in range(len(primary))
    ]


def _rank_hybrid_sentences(
    sentences: Sequence[SentenceSpan],
    dense_scores: Sequence[float],
    query: str,
    budget: int,
) -> List[SentenceSpan]:
    """Fuse semantic and lexical ranks, then apply diversity as a soft guard."""
    lexical_scores = [_lexical_score(query, sentence.text) for sentence in sentences]
    fused = _reciprocal_rank_fusion(dense_scores, lexical_scores)
    ranked = sorted(range(len(sentences)), key=lambda index: (-fused[index], index))
    selected = ranked[:budget]
    if not selected:
        return []

    # A missing source may contain the decisive evidence.  Replace the weakest
    # over-represented result only when the best result from that source remains
    # close to the current cutoff; diversity never forces a clearly weak span.
    selected_documents = Counter(sentences[index].document_id for index in selected)
    all_documents = {sentence.document_id for sentence in sentences}
    cutoff = fused[selected[-1]]
    for document_id in sorted(all_documents - set(selected_documents)):
        candidate = next(
            (index for index in ranked if sentences[index].document_id == document_id),
            None,
        )
        if (
            candidate is None
            or lexical_scores[candidate] <= 0
            or fused[candidate] < cutoff * 0.9
        ):
            continue
        replace_position = next(
            (
                position
                for position in range(len(selected) - 1, -1, -1)
                if selected_documents[sentences[selected[position]].document_id] > 1
            ),
            None,
        )
        if replace_position is None:
            break
        removed = selected[replace_position]
        selected_documents[sentences[removed].document_id] -= 1
        selected[replace_position] = candidate
        selected_documents[document_id] += 1
    return [sentences[index] for index in sorted(selected, key=lambda index: (-fused[index], index))]


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


def _per_document_limit(budget: int, document_count: int) -> int:
    """Share the budget across sources instead of capping every source alike.

    A flat cap made whole sources unreachable: with a budget of six and a cap of
    three, only the two strongest documents could ever contribute, no matter how
    many were supplied. Scaling the cap with the budget lets the remaining
    documents into the ranking without forcing an unranked sentence in — a
    source with nothing relevant still contributes nothing.
    """
    if document_count <= 1:
        return budget
    return max(1, ceil(budget / document_count))


def _rank_sentences(
    sentences: Sequence[SentenceSpan], scores: Sequence[float], budget: int
) -> List[SentenceSpan]:
    if len(scores) != len(sentences):
        raise EvidenceRetrievalError(
            "The embedding model returned an invalid evidence score matrix."
        )

    document_count = len({sentence.document_id for sentence in sentences})
    per_document_limit = _per_document_limit(budget, document_count)
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
        if len(selected) >= budget:
            break
    return selected


#: Neighbouring sentences included in the NLI premise on each side. One is
#: enough to resolve the pronouns and ellipsis that strand an isolated sentence;
#: this is a fixed reading window, not a value to search over.
CONTEXT_NEIGHBOURS = 1


def _context(sentence: SentenceSpan, ordered: Sequence[SentenceSpan]) -> str:
    """The sentence plus its immediate neighbours from the same document."""
    same_document = [item for item in ordered if item.document_id == sentence.document_id]
    position = next(
        (index for index, item in enumerate(same_document) if item.id == sentence.id),
        None,
    )
    if position is None:
        return sentence.text
    window = same_document[
        max(0, position - CONTEXT_NEIGHBOURS) : position + CONTEXT_NEIGHBOURS + 1
    ]
    return " ".join(item.text for item in window)


def _span(
    sentence: SentenceSpan,
    documents_by_id: dict[str, str],
    ordered: Sequence[SentenceSpan],
) -> EvidenceSpan:
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
        context=_context(sentence, ordered),
    )


async def retrieve_evidence(
    documents: Sequence[RetrievalDocument],
    atoms: Sequence[RetrievalAtom],
    *,
    prepared_cache_key: Optional[str] = None,
    evidence_per_atom: int = DEFAULT_EVIDENCE_PER_ATOM,
) -> EvidenceRetrievalResponse:
    if not settings.embedding_model_path.is_dir():
        raise EvidenceRetrievalConfigurationError(
            "The local evidence embedding model is missing. Run ./run-verigraph --prepare."
        )

    all_sentences = segment_documents(documents)
    sentences = _eligible_sentences(all_sentences)
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
                    _span(sentence, documents_by_id, all_sentences)
                    for sentence in _rank_hybrid_sentences(
                        sentences, scores, atom.text, evidence_per_atom
                    )
                ],
            )
        )
    return EvidenceRetrievalResponse(
        evidence=evidence,
        model=settings.embedding_model,
    )
