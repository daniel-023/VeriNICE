from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import List, Sequence, Tuple

import pysbd

from .errors import EvidenceRetrievalOutputError
from .schemas import RetrievalDocument


ANNOTATED_EVIDENCE_LINE = re.compile(r"(?m)^Evidence \d+:[^\n]*")
QUESTION_MARK_PLACEHOLDER = "\ue000"


@dataclass(frozen=True)
class SentenceSpan:
    id: str
    text: str
    start: int
    end: int
    document_id: str = "document-1"
    ordinal: int = 0


# Segmentation is deterministic, so an unchanged document is segmented once
# across retries and across the per-atom requests of a single retrieval.
def _protect_annotated_evidence_questions(document: str) -> str:
    """Keep a benchmark evidence question and its answer in one candidate.

    AVeriTeC evidence cards store each question and its first answer sentence on
    the same physical line. Generic sentence splitting otherwise stops at the
    question mark, leaving the highlighted/retrieved span as a question while
    the decisive yes/no or short answer sits in its neighbour context. Replacing
    only those question marks in a same-length working copy preserves every
    source offset while allowing the answer punctuation to end the candidate.
    """

    protected = list(document)
    for match in ANNOTATED_EVIDENCE_LINE.finditer(document):
        for index in range(match.start(), match.end()):
            if protected[index] == "?":
                protected[index] = QUESTION_MARK_PLACEHOLDER
    return "".join(protected)


@lru_cache(maxsize=32)
def _segmented(document: str, document_id: str) -> Tuple[SentenceSpan, ...]:
    segmenter = pysbd.Segmenter(language="en", clean=False, char_span=True)
    protected_document = _protect_annotated_evidence_questions(document)
    sentences: List[SentenceSpan] = []
    for ordinal, raw_span in enumerate(segmenter.segment(protected_document)):
        start = raw_span.start
        end = raw_span.end
        if (
            start < 0
            or end <= start
            or protected_document[start:end] != raw_span.sent
        ):
            raise EvidenceRetrievalOutputError(
                f"Document {document_id} could not be segmented with exact offsets."
            )
        text = document[start:end]
        sentences.append(
            SentenceSpan(
                id=f"{document_id}::sentence-{ordinal + 1}",
                text=text,
                start=start,
                end=end,
                document_id=document_id,
                ordinal=ordinal,
            )
        )
    if not sentences:
        raise EvidenceRetrievalOutputError(
            f"Document {document_id} contains no sentences to search."
        )
    return tuple(sentences)


def segment_document(document: str, document_id: str = "document-1") -> List[SentenceSpan]:
    return list(_segmented(document, document_id))


def segment_documents(documents: Sequence[RetrievalDocument]) -> List[SentenceSpan]:
    sentences: List[SentenceSpan] = []
    for document in documents:
        sentences.extend(segment_document(document.text, document.id))
    return sentences
