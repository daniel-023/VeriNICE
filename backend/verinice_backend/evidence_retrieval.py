from __future__ import annotations

from collections import Counter
from math import ceil, log
import re
from typing import List, Optional, Sequence

from . import embeddings
from .errors import EvidenceRetrievalConfigurationError, EvidenceRetrievalError
from .schemas import (
    DEFAULT_EVIDENCE_PER_ATOM,
    AtomEvidence,
    EvidenceContextSpan,
    EvidenceRetrievalResponse,
    EvidenceSpan,
    RetrievalAtom,
    RetrievalDocument,
    RetrievalMethod,
)
from .segmentation import SentenceSpan, segment_document, segment_documents
from .settings import settings
from .text_offsets import utf16_offset


MAX_CANDIDATE_CHARACTERS = 1_000
MIN_HEADING_WORDS = 5
_LEXICAL_WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
_LIST_PREFIX = re.compile(r"^(?:[-*•]|\d+[.)])\s+")
_LEXICAL_TOKEN = re.compile(
    r"\d+(?:[.,]\d+)*(?:%|\b)|[^\W_]+(?:[’'-][^\W_]+)*",
    re.UNICODE,
)
_NUMBER = re.compile(r"^\d+(?:[.,]\d+)*%?$")
_LIST_RELEVANT = re.compile(
    r"(?ix)\b(?:"
    r"list(?:ed|s|ing)?|"
    r"member(?:s|ship)?\s+of|"
    r"included\s+(?:in|on|among)|"
    r"designated\s+(?:as|by)|"
    r"belongs?\s+to|"
    r"on\s+(?:the\s+)?(?:[\w'-]+\s+){0,6}"
    r"(?:board|committee|council|register|roster)"
    r")\b"
)
BM25_K1 = 1.5
BM25_B = 0.75
BM25_MODEL = "bm25-v1"


def _normalize_number(token: str) -> str:
    """Canonicalize grouping, decimal, and percent formatting."""
    percent = token.endswith("%")
    value = token[:-1] if percent else token
    if "," in value and "." in value:
        decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        value = value.replace(grouping_separator, "").replace(
            decimal_separator, "."
        )
    elif "," in value:
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", value):
            value = value.replace(",", "")
        elif value.count(",") == 1:
            value = value.replace(",", ".")
    integer, dot, fraction = value.partition(".")
    integer = integer.lstrip("0") or "0"
    if dot:
        fraction = fraction.rstrip("0")
        value = f"{integer}.{fraction}" if fraction else integer
    else:
        value = integer
    return f"#number:{value}{'%' if percent else ''}"


def _lexical_tokens(text: str) -> List[str]:
    tokens: List[str] = []
    for raw_token in _LEXICAL_TOKEN.findall(text):
        token = raw_token.casefold()
        if _NUMBER.fullmatch(token):
            tokens.append(_normalize_number(token))
        elif len(token) > 2:
            tokens.append(token)
    return tokens


class _BM25Index:
    """Reusable token and corpus statistics for a fixed passage collection."""

    def __init__(self, passages: Sequence[str]) -> None:
        self.passages = tuple(passages)
        self.passage_tokens = tuple(
            tuple(_lexical_tokens(passage)) for passage in self.passages
        )
        self.frequencies = tuple(Counter(tokens) for tokens in self.passage_tokens)
        self.average_length = (
            sum(map(len, self.passage_tokens)) / len(self.passage_tokens)
            if self.passage_tokens
            else 0.0
        )
        self.document_frequency = Counter(
            term for tokens in self.passage_tokens for term in set(tokens)
        )

    def scores(self, query: str) -> List[float]:
        """Score this index with Okapi BM25 and small structural cues.

        Dense retrieval handles paraphrases well but can miss names, dates,
        numbers, and terse list entries. BM25 supplies the lexical signal
        without treating every query term as equally informative.
        """
        query_terms = set(_lexical_tokens(query))
        list_relevant = bool(
            _LIST_PREFIX.match(query.strip()) or _LIST_RELEVANT.search(query)
        )
        scores: List[float] = []
        for passage, tokens, frequencies in zip(
            self.passages, self.passage_tokens, self.frequencies
        ):
            length_normalizer = 1 - BM25_B
            if self.average_length:
                length_normalizer += BM25_B * len(tokens) / self.average_length
            score = 0.0
            for term in query_terms:
                frequency = frequencies[term]
                if not frequency:
                    continue
                inverse_document_frequency = log(
                    1
                    + (len(self.passages) - self.document_frequency[term] + 0.5)
                    / (self.document_frequency[term] + 0.5)
                )
                score += inverse_document_frequency * (
                    frequency * (BM25_K1 + 1)
                    / (frequency + BM25_K1 * length_normalizer)
                )
            if score > 0 and list_relevant and _LIST_PREFIX.match(passage.strip()):
                score += 0.15
            scores.append(score)
        return scores


def _bm25_scores(query: str, passages: Sequence[str]) -> List[float]:
    """Convenience wrapper for scoring a standalone passage collection."""
    return _BM25Index(passages).scores(query)


def _tie_aware_ranks(scores: Sequence[float]) -> dict[int, int]:
    """Return competition ranks, so equal scores receive the same rank."""
    ordered = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
    ranks: dict[int, int] = {}
    previous_score: Optional[float] = None
    previous_rank = 0
    for position, index in enumerate(ordered, start=1):
        if previous_score is None or scores[index] != previous_score:
            previous_rank = position
            previous_score = scores[index]
        ranks[index] = previous_rank
    return ranks


def _reciprocal_rank_fusion(
    dense_scores: Sequence[float], lexical_scores: Sequence[float]
) -> List[float]:
    if len(dense_scores) != len(lexical_scores):
        raise EvidenceRetrievalError(
            "The embedding model returned an invalid evidence score matrix."
        )
    dense_rank = _tie_aware_ranks(dense_scores)
    lexical_rank = _tie_aware_ranks(lexical_scores)
    return [
        1 / (60 + dense_rank[index])
        + (1 / (60 + lexical_rank[index]) if lexical_scores[index] > 0 else 0)
        for index in range(len(dense_scores))
    ]


def _rank_hybrid_sentences(
    sentences: Sequence[SentenceSpan],
    dense_scores: Sequence[float],
    query: str,
    budget: int,
    bm25_index: Optional[_BM25Index] = None,
) -> List[SentenceSpan]:
    """Fuse semantic and lexical ranks, then apply diversity as a soft guard."""
    index = bm25_index or _BM25Index(
        [sentence.text for sentence in sentences]
    )
    lexical_scores = index.scores(query)
    fused = _reciprocal_rank_fusion(dense_scores, lexical_scores)
    # Equal-weight RRF frequently creates symmetric ties (for example, ranks
    # 1/2 versus 2/1). Exact lexical anchors are the deterministic tie-breaker;
    # document order and sentence offset remain the final stable ordering.
    ranked = sorted(
        range(len(sentences)),
        key=lambda index: (-fused[index], -lexical_scores[index], index),
    )
    document_count = len({sentence.document_id for sentence in sentences})
    # Preserve Hybrid's soft diversity for small budgets, while allowing a
    # user-selected budget above six to expand beyond the former 3-per-source
    # ceiling. The replacement pass below may still introduce another source
    # when its best lexical anchor is competitive.
    per_document_limit = budget if document_count <= 1 else max(
        3, _per_document_limit(budget, document_count)
    )
    selected: List[int] = []
    counts: Counter[str] = Counter()
    for index in ranked:
        document_id = sentences[index].document_id
        if counts[document_id] >= per_document_limit:
            continue
        selected.append(index)
        counts[document_id] += 1
        if len(selected) >= budget:
            break
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
    # A labelled myth heading quotes a proposition but does not assert it.
    # Keep the accompanying explanatory sentence, which is the evidence unit.
    if re.match(r"(?i)^myth\s*:", stripped):
        return False
    word_count = len(_LEXICAL_WORD.findall(stripped))
    if word_count >= MIN_HEADING_WORDS or stripped.endswith((".", "?", "!")):
        return True
    # Compact source fact rows can be complete evidence units even without
    # sentence punctuation (for example, an award, place, and year). Require
    # both a typed fact cue and a number so ordinary navigation headings stay
    # excluded.
    if (
        word_count >= 3
        and re.search(r"\d", stripped)
        and re.search(r"(?i)\b(?:awarded|award|born|date|died|joined|member|population|prize|sale)\b", stripped)
    ):
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


#: Bound assembled reading context while keeping the highlighted anchor intact.
#: Adjacent sentences are added only when an anaphoric or forward-introduction
#: cue makes the anchor dependent on them.
MAX_CONTEXT_CHARACTERS = 4000

_BACKWARD_CONTEXT = re.compile(
    r"^(?:however|but|and|also|instead|meanwhile|therefore|thus|accordingly|"
    r"consequently|similarly|this|that|these|those|such|he|she|it|they|his|"
    r"her|its|their|the former|the latter)\b",
    re.IGNORECASE,
)
_FORWARD_CONTEXT = re.compile(
    r"(?:as follows|the following|these are|listed below)\s*[:.]?$",
    re.IGNORECASE,
)
_REFERENCE_DEPENDENT = re.compile(
    r"\b(?:he|she|it|they|this|that|these|those|former|latter|above|below)\b",
    re.IGNORECASE,
)


def _same_paragraph(left: SentenceSpan, right: SentenceSpan) -> bool:
    boundary = f"{left.text[-4:]}{right.text[:4]}"
    return re.search(r"\n\s*\n", boundary) is None


def _context_sentences(
    sentence: SentenceSpan, ordered: Sequence[SentenceSpan]
) -> List[tuple[SentenceSpan, str]]:
    """Select only context signalled by the anchor's language.

    Context never crosses a document or paragraph boundary. The exact anchor
    remains the evidence unit; these sentences only resolve references or an
    explicit forward introduction.
    """
    same_document = [item for item in ordered if item.document_id == sentence.document_id]
    position = next(
        (index for index, item in enumerate(same_document) if item.id == sentence.id),
        None,
    )
    if position is None:
        return []
    stripped = sentence.text.strip()
    selected: List[tuple[SentenceSpan, str]] = []
    needs_previous = bool(
        _BACKWARD_CONTEXT.match(stripped)
        or _REFERENCE_DEPENDENT.search(stripped)
        or stripped.startswith(('"', "“", "'"))
    )
    if needs_previous and position > 0:
        previous = same_document[position - 1]
        if (
            len(previous.text) <= MAX_CANDIDATE_CHARACTERS
            and _same_paragraph(previous, sentence)
        ):
            selected.append((previous, "PREVIOUS"))
    if _FORWARD_CONTEXT.search(stripped) and position + 1 < len(same_document):
        following = same_document[position + 1]
        if (
            len(following.text) <= MAX_CANDIDATE_CHARACTERS
            and _same_paragraph(sentence, following)
        ):
            selected.append((following, "NEXT"))
    elif position + 1 < len(same_document):
        following = same_document[position + 1]
        if (
            _BACKWARD_CONTEXT.match(following.text.strip())
            and len(following.text) <= MAX_CANDIDATE_CHARACTERS
            and _same_paragraph(sentence, following)
        ):
            selected.append((following, "NEXT"))
    return selected


def _context(sentence: SentenceSpan, ordered: Sequence[SentenceSpan]) -> str:
    """Assemble the anchor and only its explicitly selected reading context."""
    context_items = [item for item, _direction in _context_sentences(sentence, ordered)]
    context_items.append(sentence)
    context_items.sort(key=lambda item: item.ordinal)
    return " ".join(item.text.strip() for item in context_items)[:MAX_CONTEXT_CHARACTERS]


def _context_span(
    sentence: SentenceSpan,
    direction: str,
    documents_by_id: dict[str, str],
) -> EvidenceContextSpan:
    document = documents_by_id[sentence.document_id]
    if document[sentence.start : sentence.end] != sentence.text:
        raise EvidenceRetrievalError("A context sentence no longer matches its source document.")
    return EvidenceContextSpan(
        id=sentence.id,
        document_id=sentence.document_id,
        text=sentence.text,
        start=utf16_offset(document, sentence.start),
        end=utf16_offset(document, sentence.end),
        direction=direction,
    )


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
        context_spans=[
            _context_span(item, direction, documents_by_id)
            for item, direction in _context_sentences(sentence, ordered)
        ],
        context=_context(sentence, ordered),
    )


async def retrieve_evidence(
    documents: Sequence[RetrievalDocument],
    atoms: Sequence[RetrievalAtom],
    *,
    prepared_cache_key: Optional[str] = None,
    evidence_per_atom: int = DEFAULT_EVIDENCE_PER_ATOM,
    retrieval_method: RetrievalMethod = RetrievalMethod.hybrid,
) -> EvidenceRetrievalResponse:
    uses_embeddings = retrieval_method != RetrievalMethod.lexical
    if uses_embeddings and not settings.embedding_model_path.is_dir():
        raise EvidenceRetrievalConfigurationError(
            "The local evidence embedding model is missing. Run ./run-verinice --prepare."
        )

    all_sentences = segment_documents(documents)
    sentences = _eligible_sentences(all_sentences)
    provider = "sentence-transformers" if uses_embeddings else "python"
    model = settings.embedding_model if uses_embeddings else BM25_MODEL
    if not sentences:
        return EvidenceRetrievalResponse(
            evidence=[AtomEvidence(atom_id=atom.id, spans=[]) for atom in atoms],
            provider=provider,
            model=model,
            retrieval_method=retrieval_method,
        )

    passage_texts = [sentence.text for sentence in sentences]
    bm25_index = (
        _BM25Index(passage_texts)
        if retrieval_method != RetrievalMethod.semantic
        else None
    )
    if retrieval_method == RetrievalMethod.lexical:
        assert bm25_index is not None
        score_matrix = [bm25_index.scores(atom.text) for atom in atoms]
    else:
        score_matrix = await embeddings.similarity_matrix(
            [atom.text for atom in atoms],
            passage_texts,
            cache_key=prepared_cache_key,
        )
    if len(score_matrix) != len(atoms):
        raise EvidenceRetrievalError(
            "The embedding model returned an invalid evidence score matrix."
        )

    documents_by_id = {document.id: document.text for document in documents}
    evidence: List[AtomEvidence] = []
    for atom, scores in zip(atoms, score_matrix):
        if retrieval_method == RetrievalMethod.hybrid:
            ranked = _rank_hybrid_sentences(
                sentences,
                scores,
                atom.text,
                evidence_per_atom,
                bm25_index=bm25_index,
            )
        else:
            ranked = _rank_sentences(sentences, scores, evidence_per_atom)
        evidence.append(
            AtomEvidence(
                atom_id=atom.id,
                spans=[
                    _span(sentence, documents_by_id, all_sentences)
                    for sentence in ranked
                ],
            )
        )
    return EvidenceRetrievalResponse(
        evidence=evidence,
        provider=provider,
        model=model,
        retrieval_method=retrieval_method,
    )
