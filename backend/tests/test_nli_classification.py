from __future__ import annotations

import inspect
import os
from types import SimpleNamespace

import pytest
import torch

from verigraph_backend import nli_classification as nli
from verigraph_backend.schemas import NLIAtomEvidence, NLIInputSpan, NLIRelation, PipelineAtom


class FakeTokenizer:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, premises, hypotheses, **options):
        self.calls.append((list(premises), list(hypotheses), options))
        return {"input_ids": torch.ones((len(premises), 2), dtype=torch.long)}


class FakeModel:
    def __init__(self, predictions) -> None:
        self.predictions = list(predictions)
        self.offset = 0

    def __call__(self, **_encoded):
        batch_size = len(_encoded["input_ids"])
        indices = self.predictions[self.offset : self.offset + batch_size]
        self.offset += batch_size
        logits = torch.full((batch_size, 3), -5.0)
        for row, index in enumerate(indices):
            logits[row, index] = 5.0
        return SimpleNamespace(logits=logits)


def span(span_id: str, document_id: str, text: str) -> NLIInputSpan:
    return NLIInputSpan(id=span_id, document_id=document_id, text=text)


def test_batches_pairs_in_premise_hypothesis_order_and_preserves_order(monkeypatch) -> None:
    atoms = [
        PipelineAtom(id="atom-2", text="The bridge is open."),
        PipelineAtom(id="atom-1", text="The archive opened in 2019."),
    ]
    evidence = [
        NLIAtomEvidence(
            atom_id="atom-1",
            spans=[span("sentence-3", "doc-b", "The archive opened in 2021.")],
        ),
        NLIAtomEvidence(
            atom_id="atom-2",
            spans=[
                span("sentence-1", "doc-a", "The bridge is open."),
                span("sentence-2", "doc-a", "Traffic uses another route."),
            ],
        ),
    ]
    tokenizer = FakeTokenizer()
    model = FakeModel([0, 2])
    labels = {
        0: NLIRelation.entailment,
        1: NLIRelation.neutral,
        2: NLIRelation.contradiction,
    }
    monkeypatch.setattr(nli, "_load_components", lambda: (tokenizer, model, labels))

    response = nli.classify_support(atoms, evidence)

    assert tokenizer.calls[0][0] == [
        "The bridge is open.",
        "The archive opened in 2021.",
    ]
    assert tokenizer.calls[0][1] == [
        "The bridge is open.",
        "The archive opened in 2019.",
    ]
    assert tokenizer.calls[0][2]["max_length"] == 512
    assert [item.atom_id for item in response.classifications] == ["atom-2", "atom-1"]
    assert [relation.relation for relation in response.classifications[0].relations] == [
        NLIRelation.entailment,
        NLIRelation.neutral,
    ]
    assert response.classifications[0].relations[1].relevance_filtered is True
    assert response.classifications[1].relations[0].relation == NLIRelation.contradiction
    assert "score" not in response.model_dump_json().lower()


@pytest.mark.parametrize(
    ("sentence", "obligation"),
    [
        (
            "Ivermectin is highly effective against strongyloides, scabies, ticks, and malaria transmission.",
            "Ivermectin is a treatment for coronavirus.",
        ),
        (
            "The technique is already in wide use for treating a range of illnesses.",
            "The treatment was developed from the use of fetal tissue.",
        ),
        (
            "Igbo are predominantly Christian.",
            "Igbo people are the richest people per capita in Africa.",
        ),
    ],
)
def test_diagnosed_unrelated_false_contradictions_are_filtered(sentence, obligation) -> None:
    assert nli._is_topically_relevant(sentence, obligation) is False


def test_context_rescues_a_pronoun_dependent_candidate() -> None:
    assert nli._is_topically_relevant(
        "She denied it.",
        "The minister denied the corruption report.",
        "The minister discussed the corruption report. She denied it.",
    ) is True


def test_neighbor_context_does_not_rescue_an_unrelated_self_contained_sentence() -> None:
    assert nli._is_topically_relevant(
        "Ivermectin is also effective against scabies, and it can reduce malaria transmission.",
        "Ivermectin is a treatment for coronavirus.",
        "COVID-19 treatment is under study. Ivermectin is also effective against scabies, and it can reduce malaria transmission.",
    ) is False


def test_contradiction_requires_an_inspectable_conflict_anchor() -> None:
    assert nli._has_explicit_contradiction_anchor(
        "The archive opened in 2021.",
        "The archive opened in 2019.",
    ) is True
    assert nli._has_explicit_contradiction_anchor(
        "Officials discussed airport remarks during the event.",
        "The president said airports were the biggest Revolutionary War problem.",
    ) is False


def test_low_confidence_non_neutral_prediction_becomes_neutral(monkeypatch) -> None:
    atoms = [PipelineAtom(id="atom-1", text="The bridge is open.")]
    evidence = [
        NLIAtomEvidence(
            atom_id="atom-1",
            spans=[span("sentence-1", "doc-a", "The bridge is open.")],
        )
    ]
    monkeypatch.setattr(nli, "_load_components", lambda: (object(), object(), {}))
    monkeypatch.setattr(
        nli,
        "_predict_with_confidence",
        lambda _pairs: [(NLIRelation.entailment, 0.51)],
    )
    result = nli.classify_support(atoms, evidence)
    assert result.classifications[0].relations[0].relation == NLIRelation.neutral


def test_empty_evidence_returns_ordered_empty_relations(monkeypatch) -> None:
    atoms = [PipelineAtom(id="atom-1", text="A claim.")]
    evidence = [NLIAtomEvidence(atom_id="atom-1", spans=[])]
    tokenizer = FakeTokenizer()
    monkeypatch.setattr(
        nli,
        "_load_components",
        lambda: (
            tokenizer,
            FakeModel([]),
            {
                0: NLIRelation.entailment,
                1: NLIRelation.neutral,
                2: NLIRelation.contradiction,
            },
        ),
    )
    response = nli.classify_support(atoms, evidence)
    assert response.classifications[0].relations == []
    assert tokenizer.calls == []


def test_label_mapping_uses_model_configuration_not_index_order() -> None:
    config = SimpleNamespace(
        id2label={0: "contradiction", 1: "entailment", 2: "neutral"}
    )
    assert nli._label_mapping(config) == {
        0: NLIRelation.contradiction,
        1: NLIRelation.entailment,
        2: NLIRelation.neutral,
    }


def test_model_absence_has_actionable_prepare_message(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(nli, "_tokenizer", None)
    monkeypatch.setattr(nli, "_model", None)
    monkeypatch.setattr(nli, "_labels", None)
    monkeypatch.setattr(
        nli,
        "settings",
        SimpleNamespace(nli_model_path=tmp_path / "missing", nli_model="test-nli"),
    )
    with pytest.raises(nli.NLIClassificationConfigurationError, match="--prepare"):
        nli.warm()


def test_warm_runs_one_content_free_local_inference(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(nli, "_load_error", "previous failure")
    monkeypatch.setattr(
        nli,
        "_predict",
        lambda pairs: seen.extend(pairs) or [NLIRelation.entailment],
    )
    nli.warm()
    assert seen == [("A source states a fact.", "A source states a fact.")]
    assert nli._load_error is None


def test_inference_failure_is_content_free_and_no_network_client_is_imported(monkeypatch) -> None:
    class BrokenModel:
        def __call__(self, **_encoded):
            raise RuntimeError("private premise")

    monkeypatch.setattr(
        nli,
        "_load_components",
        lambda: (
            FakeTokenizer(),
            BrokenModel(),
            {
                0: NLIRelation.entailment,
                1: NLIRelation.neutral,
                2: NLIRelation.contradiction,
            },
        ),
    )
    with pytest.raises(nli.NLIClassificationError, match="Local NLI inference failed"):
        nli._predict([("private premise", "private hypothesis")])
    source = inspect.getsource(nli)
    assert "httpx" not in source
    assert "ollama" not in source.lower()


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("VERIGRAPH_RUN_NLI_INTEGRATION") != "1",
    reason="set VERIGRAPH_RUN_NLI_INTEGRATION=1 to load the packaged NLI model",
)
def test_packaged_model_audit() -> None:
    atoms = [
        PipelineAtom(id="entailed", text="The proposal was approved by the board."),
        PipelineAtom(id="contradicted", text="The archive opened in 2019."),
        PipelineAtom(id="neutral", text="The fund invested in coal."),
    ]
    evidence = [
        NLIAtomEvidence(
            atom_id="entailed",
            spans=[span("s1", "doc", "The board approved the proposal.")],
        ),
        NLIAtomEvidence(
            atom_id="contradicted",
            spans=[span("s2", "doc", "The archive opened in 2021.")],
        ),
        NLIAtomEvidence(
            atom_id="neutral",
            spans=[span("s3", "doc", "The report discusses economic forecasts.")],
        ),
    ]
    response = nli.classify_support(atoms, evidence)
    assert [item.relations[0].relation for item in response.classifications] == [
        NLIRelation.entailment,
        NLIRelation.contradiction,
        NLIRelation.neutral,
    ]
