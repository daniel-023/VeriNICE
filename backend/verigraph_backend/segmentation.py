from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import List, Sequence, Tuple

import pysbd

from .errors import EvidenceRetrievalOutputError
from .schemas import RetrievalDocument


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
@lru_cache(maxsize=32)
def _segmented(document: str, document_id: str) -> Tuple[SentenceSpan, ...]:
    segmenter = pysbd.Segmenter(language="en", clean=False, char_span=True)
    sentences: List[SentenceSpan] = []
    for ordinal, raw_span in enumerate(segmenter.segment(document)):
        text = raw_span.sent
        start = raw_span.start
        end = raw_span.end
        if start < 0 or end <= start or document[start:end] != text:
            raise EvidenceRetrievalOutputError(
                f"Document {document_id} could not be segmented with exact offsets."
            )
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
