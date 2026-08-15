from __future__ import annotations

from dataclasses import replace
from typing import List

import numpy as np
import pytest

from verigraph_backend import embeddings, evidence_retrieval
from verigraph_backend.errors import (
    EvidenceRetrievalConfigurationError,
    EvidenceRetrievalError,
)
from verigraph_backend.evidence_retrieval import (
    MAX_CANDIDATE_CHARACTERS,
    _eligible_sentences,
    _rank_sentences,
    retrieve_evidence,
)
from verigraph_backend.schemas import RetrievalAtom, RetrievalDocument
from verigraph_backend.segmentation import SentenceSpan, segment_document, segment_documents


@pytest.fixture
def configured_retrieval(monkeypatch, tmp_path):
    model_path = tmp_path / "embedding-model"
    model_path.mkdir()
    monkeypatch.setattr(
        evidence_retrieval,
        "settings",
        replace(
            evidence_retrieval.settings,
            embedding_model="test-embedding",
            embedding_model_path=model_path,
        ),
    )
    return model_path


def test_segmentation_preserves_offsets_paragraphs_repetition_and_unicode() -> None:
    document = "Dr. Rao arrived at 5 p.m.\n\nThe archive opened. The archive opened. 🚀"
    sentences = segment_document(document, "doc-a")
    assert "".join(sentence.text for sentence in sentences) == document
    assert all(document[sentence.start : sentence.end] == sentence.text for sentence in sentences)
    assert len({sentence.id for sentence in sentences}) == len(sentences)
    assert sentences[0].text.endswith("\n\n")


def test_repeated_sentences_across_documents_keep_document_scoped_ids() -> None:
    sentences = segment_documents(
        [
            RetrievalDocument(id="doc-a", text="The archive opened. The archive opened."),
            RetrievalDocument(id="doc-b", text="The archive opened."),
        ]
    )
    assert len({sentence.id for sentence in sentences}) == 3
    assert [sentence.document_id for sentence in sentences] == ["doc-a", "doc-a", "doc-b"]


def test_ranking_returns_six_globally_and_caps_each_document_at_three() -> None:
    sentences = [
        SentenceSpan(
            id=f"doc-a::sentence-{index + 1}",
            text=f"A{index}.",
            start=index * 4,
            end=index * 4 + 3,
            document_id="doc-a",
            ordinal=index,
        )
        for index in range(5)
    ] + [
        SentenceSpan(
            id=f"doc-b::sentence-{index + 1}",
            text=f"B{index}.",
            start=index * 4,
            end=index * 4 + 3,
            document_id="doc-b",
            ordinal=index,
        )
        for index in range(5)
    ]
    scores = [1.0 - index * 0.01 for index in range(10)]
    selected = _rank_sentences(sentences, scores)
    assert len(selected) == 6
    assert [sentence.document_id for sentence in selected].count("doc-a") == 3
    assert [sentence.document_id for sentence in selected].count("doc-b") == 3


def test_single_document_can_supply_six_and_ties_use_source_order() -> None:
    sentences = [
        SentenceSpan(
            id=f"doc-a::sentence-{index + 1}",
            text=f"Sentence {index}.",
            start=index * 12,
            end=index * 12 + 11,
            document_id="doc-a",
            ordinal=index,
        )
        for index in range(8)
    ]
    selected = _rank_sentences(sentences, [0.5] * len(sentences))
    assert [sentence.id for sentence in selected] == [
        f"doc-a::sentence-{index}" for index in range(1, 7)
    ]


def test_fewer_than_six_candidates_returns_every_candidate() -> None:
    sentences = [
        SentenceSpan("one", "One.", 0, 4, "doc-a", 0),
        SentenceSpan("two", "Two.", 4, 8, "doc-a", 1),
    ]
    assert _rank_sentences(sentences, [-1.0, -2.0]) == sentences


def test_blank_and_overlong_extraction_artifacts_are_not_candidates() -> None:
    sentences = [
        SentenceSpan("blank", " \n", 0, 2, "doc-a", 0),
        SentenceSpan(
            "long",
            "x" * (MAX_CANDIDATE_CHARACTERS + 1),
            2,
            MAX_CANDIDATE_CHARACTERS + 3,
            "doc-a",
            1,
        ),
        SentenceSpan("valid", "Useful evidence.", 10, 26, "doc-a", 2),
    ]
    assert _eligible_sentences(sentences) == [sentences[-1]]


def test_short_headings_are_excluded_but_explicit_list_entries_remain() -> None:
    sentences = [
        SentenceSpan("heading", "Designated Foreign Terrorist Organizations | ", 0, 45, "doc-a", 0),
        SentenceSpan("list", "- NDF", 45, 50, "doc-a", 1),
        SentenceSpan("sentence", "The official list contains multiple organizations.", 50, 100, "doc-a", 2),
    ]
    assert _eligible_sentences(sentences) == sentences[1:]


async def test_retrieval_batches_all_atoms_and_returns_exact_utf16_spans(
    monkeypatch, configured_retrieval
) -> None:
    documents = [
        RetrievalDocument(
            id="doc-a",
            text="🚀 Aurora launched. It landed safely. Observers celebrated.",
        )
    ]
    atoms = [
        RetrievalAtom(id="atom-1", text="Aurora launched."),
        RetrievalAtom(id="atom-2", text="Aurora landed safely."),
    ]
    captured = {}

    async def similarity_matrix(queries, passages, *, cache_key=None):
        captured.update(queries=list(queries), passages=list(passages), cache_key=cache_key)
        return [[0.9, 0.2, 0.1], [0.1, 0.9, 0.2]]

    monkeypatch.setattr(embeddings, "similarity_matrix", similarity_matrix)
    result = await retrieve_evidence(
        documents, atoms, prepared_cache_key="prepared-case"
    )
    assert captured["queries"] == [atom.text for atom in atoms]
    assert len(captured["passages"]) == 3
    assert captured["cache_key"] == "prepared-case"
    first = result.evidence[0].spans[0]
    assert first.text == "🚀 Aurora launched. "
    assert first.start == 0
    assert first.end == len(first.text) + 1
    assert result.provider == "sentence-transformers"


async def test_unrelated_negative_scores_still_return_nearest_candidates(
    monkeypatch, configured_retrieval
) -> None:
    documents = [RetrievalDocument(id="doc-a", text="One sentence. Another sentence.")]
    atoms = [RetrievalAtom(id="atom-1", text="An unrelated query.")]

    async def similarity_matrix(queries, passages, *, cache_key=None):
        return [[-0.4, -0.7]]

    monkeypatch.setattr(embeddings, "similarity_matrix", similarity_matrix)
    result = await retrieve_evidence(documents, atoms)
    assert [span.text.strip() for span in result.evidence[0].spans] == [
        "One sentence.",
        "Another sentence.",
    ]


async def test_custom_documents_do_not_receive_a_passage_cache_key(
    monkeypatch, configured_retrieval
) -> None:
    seen: List[object] = []

    async def similarity_matrix(queries, passages, *, cache_key=None):
        seen.append(cache_key)
        return [[0.5 for _ in passages]]

    monkeypatch.setattr(embeddings, "similarity_matrix", similarity_matrix)
    await retrieve_evidence(
        [RetrievalDocument(id="doc-a", text="A sentence.")],
        [RetrievalAtom(id="atom-1", text="A query.")],
    )
    assert seen == [None]


def test_only_prepared_passage_vectors_are_cached(monkeypatch) -> None:
    calls: List[tuple] = []

    def encode(texts, instruction=""):
        calls.append((tuple(texts), instruction))
        return object()

    monkeypatch.setattr(embeddings, "_encode", encode)
    embeddings._cached_passage_vectors.cache_clear()
    passages = ("One.", "Two.")
    assert embeddings._passage_vectors(passages, "case-1") is embeddings._passage_vectors(
        passages, "case-1"
    )
    assert len(calls) == 1
    embeddings._passage_vectors(passages, None)
    embeddings._passage_vectors(passages, None)
    assert len(calls) == 3
    embeddings._cached_passage_vectors.cache_clear()


def test_warm_runs_one_content_free_local_inference(monkeypatch) -> None:
    seen: List[tuple] = []

    def encode(texts, instruction=""):
        seen.append((tuple(texts), instruction))
        return np.ones((len(texts), 2), dtype="float32")

    monkeypatch.setattr(embeddings, "_encode", encode)
    embeddings.warm()
    assert seen == [(("A source contains relevant evidence.",), "")]


async def test_invalid_score_dimensions_fail_cleanly(
    monkeypatch, configured_retrieval
) -> None:
    async def similarity_matrix(queries, passages, *, cache_key=None):
        return [[]]

    monkeypatch.setattr(embeddings, "similarity_matrix", similarity_matrix)
    with pytest.raises(EvidenceRetrievalError, match="score matrix"):
        await retrieve_evidence(
            [RetrievalDocument(id="doc-a", text="A sentence.")],
            [RetrievalAtom(id="atom-1", text="A query.")],
        )


async def test_non_finite_embedding_vectors_fail_cleanly(monkeypatch) -> None:
    monkeypatch.setattr(
        embeddings,
        "_passage_vectors",
        lambda _passages, _cache_key: np.array([[np.nan, 0.0]], dtype="float32"),
    )
    monkeypatch.setattr(
        embeddings,
        "_encode",
        lambda _texts, _instruction="": np.array([[1.0, 0.0]], dtype="float32"),
    )
    with pytest.raises(EvidenceRetrievalError, match="non-finite evidence vectors"):
        await embeddings.similarity_matrix(["Query"], ["Passage"])


async def test_missing_local_model_returns_configuration_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        evidence_retrieval,
        "settings",
        replace(
            evidence_retrieval.settings,
            embedding_model_path=tmp_path / "missing",
        ),
    )
    with pytest.raises(EvidenceRetrievalConfigurationError, match="--prepare"):
        await retrieve_evidence(
            [RetrievalDocument(id="doc-a", text="A sentence.")],
            [RetrievalAtom(id="atom-1", text="A query.")],
        )
