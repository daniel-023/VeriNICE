from __future__ import annotations

import inspect
import os

import pytest
from spacy.tokens import Doc, Span
from spacy.vocab import Vocab

from verigraph_backend import linguistic_analysis as linguistic
from verigraph_backend.schemas import PipelineAtom


def make_doc(
    words,
    spaces,
    heads,
    deps,
    pos,
    tags,
    lemmas,
    entities=(),
):
    doc = Doc(
        Vocab(),
        words=words,
        spaces=spaces,
        heads=heads,
        deps=deps,
        pos=pos,
        tags=tags,
        lemmas=lemmas,
    )
    doc.ents = [Span(doc, start, end, label=label) for start, end, label in entities]
    return doc


def test_active_frame_and_verification_cues() -> None:
    text = "Mara did not buy three cars in 2024."
    doc = make_doc(
        ["Mara", "did", "not", "buy", "three", "cars", "in", "2024", "."],
        [True, True, True, True, True, True, True, False, False],
        [3, 3, 3, 3, 5, 3, 3, 6, 3],
        ["nsubj", "aux", "neg", "ROOT", "nummod", "dobj", "prep", "pobj", "punct"],
        ["PROPN", "AUX", "PART", "VERB", "NUM", "NOUN", "ADP", "NUM", "PUNCT"],
        ["NNP", "VBD", "RB", "VB", "CD", "NNS", "IN", "CD", "."],
        ["Mara", "do", "not", "buy", "three", "car", "in", "2024", "."],
        entities=[(0, 1, "PERSON"), (4, 5, "CARDINAL"), (7, 8, "DATE")],
    )
    result = linguistic.analysis_from_doc(PipelineAtom(id="atom-1", text=text), doc)

    assert result.status == "complete"
    assert result.frames[0].predicate.text == "buy"
    assert [span.text for span in result.frames[0].subjects] == ["Mara"]
    assert [span.text for span in result.frames[0].core_arguments] == ["three cars"]
    assert result.frames[0].core_arguments[0].role == "direct_object"
    assert [(span.kind, span.text) for span in result.frames[0].adjuncts] == [
        ("temporal", "in 2024")
    ]
    assert result.frames[0].other_modifiers == []
    assert {(cue.kind, cue.text) for cue in result.cues} >= {
        ("negation", "not"),
        ("numeric", "three"),
        ("temporal", "2024"),
    }
    assert [(entity.text, entity.label) for entity in result.entities] == [("Mara", "PERSON")]


def test_passive_and_coordinated_predicates_inherit_subjects() -> None:
    text = "The proposal was approved and published."
    doc = make_doc(
        ["The", "proposal", "was", "approved", "and", "published", "."],
        [True, True, True, True, True, False, False],
        [1, 3, 3, 3, 5, 3, 3],
        ["det", "nsubjpass", "auxpass", "ROOT", "cc", "conj", "punct"],
        ["DET", "NOUN", "AUX", "VERB", "CCONJ", "VERB", "PUNCT"],
        ["DT", "NN", "VBD", "VBN", "CC", "VBN", "."],
        ["the", "proposal", "be", "approve", "and", "publish", "."],
    )
    result = linguistic.analysis_from_doc(PipelineAtom(id="atom-passive", text=text), doc)

    assert [frame.predicate.text for frame in result.frames] == ["approved", "published"]
    assert [[subject.text for subject in frame.subjects] for frame in result.frames] == [
        ["The proposal"],
        ["The proposal"],
    ]
    assert result.status == "complete"


def test_nested_clause_predicates_receive_their_own_frames() -> None:
    text = "Alice said the team may win."
    doc = make_doc(
        ["Alice", "said", "the", "team", "may", "win", "."],
        [True, True, True, True, True, False, False],
        [1, 1, 3, 5, 5, 1, 1],
        ["nsubj", "ROOT", "det", "nsubj", "aux", "ccomp", "punct"],
        ["PROPN", "VERB", "DET", "NOUN", "AUX", "VERB", "PUNCT"],
        ["NNP", "VBD", "DT", "NN", "MD", "VB", "."],
        ["Alice", "say", "the", "team", "may", "win", "."],
    )

    result = linguistic.analysis_from_doc(PipelineAtom(id="atom-nested", text=text), doc)

    assert [(frame.predicate.text, [subject.text for subject in frame.subjects]) for frame in result.frames] == [
        ("said", ["Alice"]),
        ("win", ["the team"]),
    ]
    assert result.status == "complete"


def test_controlled_nested_clause_is_partial() -> None:
    text = "Mara wants to leave."
    doc = make_doc(
        ["Mara", "wants", "to", "leave", "."],
        [True, True, True, False, False],
        [1, 1, 3, 1, 1],
        ["nsubj", "ROOT", "mark", "xcomp", "punct"],
        ["PROPN", "VERB", "PART", "VERB", "PUNCT"],
        ["NNP", "VBZ", "TO", "VB", "."],
        ["Mara", "want", "to", "leave", "."],
    )

    result = linguistic.analysis_from_doc(PipelineAtom(id="atom-controlled", text=text), doc)

    assert [frame.predicate.text for frame in result.frames] == ["wants", "leave"]
    assert result.status == "partial"
    assert result.unresolved == ["subject"]


def test_copular_frame_and_partial_parse() -> None:
    text = "Mara is the CTO."
    doc = make_doc(
        ["Mara", "is", "the", "CTO", "."],
        [True, True, True, False, False],
        [3, 3, 3, 3, 3],
        ["nsubj", "cop", "det", "ROOT", "punct"],
        ["PROPN", "AUX", "DET", "NOUN", "PUNCT"],
        ["NNP", "VBZ", "DT", "NNP", "."],
        ["Mara", "be", "the", "CTO", "."],
    )
    result = linguistic.analysis_from_doc(PipelineAtom(id="atom-copular", text=text), doc)
    assert result.frames[0].predicate.text == "is"
    assert result.frames[0].subjects[0].text == "Mara"
    assert result.frames[0].core_arguments[0].text == "the CTO"
    assert result.frames[0].core_arguments[0].role == "subject_complement"
    assert result.status == "complete"

    fragment = make_doc(
        ["Mara", "."],
        [False, False],
        [0, 0],
        ["ROOT", "punct"],
        ["PROPN", "PUNCT"],
        ["NNP", "."],
        ["Mara", "."],
    )
    partial = linguistic.analysis_from_doc(PipelineAtom(id="atom-fragment", text="Mara."), fragment)
    assert partial.status == "partial"
    assert partial.frames == []
    assert partial.unresolved == ["subject", "predicate"]


def test_core_arguments_passive_agent_and_ambiguous_preposition() -> None:
    active_text = "Mara gave Lee a report with charts."
    active = make_doc(
        ["Mara", "gave", "Lee", "a", "report", "with", "charts", "."],
        [True, True, True, True, True, True, False, False],
        [1, 1, 1, 4, 1, 1, 5, 1],
        ["nsubj", "ROOT", "dative", "det", "dobj", "prep", "pobj", "punct"],
        ["PROPN", "VERB", "PROPN", "DET", "NOUN", "ADP", "NOUN", "PUNCT"],
        ["NNP", "VBD", "NNP", "DT", "NN", "IN", "NNS", "."],
        ["Mara", "give", "Lee", "a", "report", "with", "chart", "."],
    )
    active_result = linguistic.analysis_from_doc(
        PipelineAtom(id="atom-active", text=active_text), active
    )
    assert [item.role for item in active_result.frames[0].core_arguments] == [
        "indirect_object",
        "direct_object",
    ]
    assert [item.text for item in active_result.frames[0].core_arguments] == [
        "Lee",
        "a report",
    ]
    assert [item.text for item in active_result.frames[0].other_modifiers] == [
        "with charts"
    ]

    passive_text = "The proposal was approved by the board."
    passive = make_doc(
        ["The", "proposal", "was", "approved", "by", "the", "board", "."],
        [True, True, True, True, True, True, False, False],
        [1, 3, 3, 3, 3, 6, 4, 3],
        ["det", "nsubjpass", "auxpass", "ROOT", "agent", "det", "pobj", "punct"],
        ["DET", "NOUN", "AUX", "VERB", "ADP", "DET", "NOUN", "PUNCT"],
        ["DT", "NN", "VBD", "VBN", "IN", "DT", "NN", "."],
        ["the", "proposal", "be", "approve", "by", "the", "board", "."],
    )
    passive_result = linguistic.analysis_from_doc(
        PipelineAtom(id="atom-passive-agent", text=passive_text), passive
    )
    assert [(item.role, item.text) for item in passive_result.frames[0].core_arguments] == [
        ("passive_agent", "by the board")
    ]


def test_argument_internal_preposition_stays_in_core_argument() -> None:
    text = "Mara appointed the president of France."
    doc = make_doc(
        ["Mara", "appointed", "the", "president", "of", "France", "."],
        [True, True, True, True, True, False, False],
        [1, 1, 3, 1, 3, 4, 1],
        ["nsubj", "ROOT", "det", "dobj", "prep", "pobj", "punct"],
        ["PROPN", "VERB", "DET", "NOUN", "ADP", "PROPN", "PUNCT"],
        ["NNP", "VBD", "DT", "NN", "IN", "NNP", "."],
        ["Mara", "appoint", "the", "president", "of", "France", "."],
    )
    result = linguistic.analysis_from_doc(PipelineAtom(id="atom-nominal-pp", text=text), doc)

    frame = result.frames[0]
    assert [(item.role, item.text) for item in frame.core_arguments] == [
        ("direct_object", "the president of France")
    ]
    assert frame.other_modifiers == []


def test_copular_complement_separates_only_clear_adjuncts() -> None:
    text = "Mara is the president of France in 2024."
    doc = make_doc(
        ["Mara", "is", "the", "president", "of", "France", "in", "2024", "."],
        [True, True, True, True, True, True, True, False, False],
        [3, 3, 3, 3, 3, 4, 3, 6, 3],
        ["nsubj", "cop", "det", "ROOT", "prep", "pobj", "prep", "pobj", "punct"],
        ["PROPN", "AUX", "DET", "NOUN", "ADP", "PROPN", "ADP", "NUM", "PUNCT"],
        ["NNP", "VBZ", "DT", "NN", "IN", "NNP", "IN", "CD", "."],
        ["Mara", "be", "the", "president", "of", "France", "in", "2024", "."],
        entities=[(7, 8, "DATE")],
    )
    result = linguistic.analysis_from_doc(PipelineAtom(id="atom-copular-adjunct", text=text), doc)

    frame = result.frames[0]
    assert [(item.role, item.text) for item in frame.core_arguments] == [
        ("subject_complement", "the president of France")
    ]
    assert [(item.kind, item.text) for item in frame.adjuncts] == [("temporal", "in 2024")]
    assert frame.other_modifiers == []


def test_clear_conditional_and_locative_adjuncts() -> None:
    text = "Mara waits here if rain starts."
    doc = make_doc(
        ["Mara", "waits", "here", "if", "rain", "starts", "."],
        [True, True, True, True, True, False, False],
        [1, 1, 1, 5, 5, 1, 1],
        ["nsubj", "ROOT", "advmod", "mark", "nsubj", "advcl", "punct"],
        ["PROPN", "VERB", "ADV", "SCONJ", "NOUN", "VERB", "PUNCT"],
        ["NNP", "VBZ", "RB", "IN", "NN", "VBZ", "."],
        ["Mara", "wait", "here", "if", "rain", "start", "."],
    )
    result = linguistic.analysis_from_doc(PipelineAtom(id="atom-adjuncts", text=text), doc)
    assert [(item.kind, item.text) for item in result.frames[0].adjuncts] == [
        ("locative", "here"),
        ("conditional", "if rain starts"),
    ]


def test_attribution_modality_quantifier_and_exact_utf16_offsets() -> None:
    text = "😀 Alice reportedly said every team may win."
    doc = make_doc(
        ["😀", "Alice", "reportedly", "said", "every", "team", "may", "win", "."],
        [True, True, True, True, True, True, True, False, False],
        [3, 3, 3, 3, 5, 7, 7, 3, 3],
        ["dep", "nsubj", "advmod", "ROOT", "det", "nsubj", "aux", "ccomp", "punct"],
        ["PUNCT", "PROPN", "ADV", "VERB", "DET", "NOUN", "AUX", "VERB", "PUNCT"],
        ["SYM", "NNP", "RB", "VBD", "DT", "NN", "MD", "VB", "."],
        ["😀", "Alice", "reportedly", "say", "every", "team", "may", "win", "."],
        entities=[(1, 2, "PERSON")],
    )
    result = linguistic.analysis_from_doc(PipelineAtom(id="atom-unicode", text=text), doc)
    cues = {(cue.kind, cue.text): cue for cue in result.cues}
    assert ("attribution", "said") in cues
    assert ("modality", "reportedly") in cues
    assert ("quantifier", "every") in cues
    assert ("modality", "may") in cues
    alice = result.entities[0]
    assert text.encode("utf-16-le")[: alice.start * 2].decode("utf-16-le") == "😀 "
    assert alice.end - alice.start == len("Alice")


def test_batching_order_is_stable_and_no_network_client_is_imported(monkeypatch) -> None:
    atoms = [
        PipelineAtom(id="atom-2", text="Birds fly."),
        PipelineAtom(id="atom-1", text="Fish swim."),
    ]
    docs = [
        make_doc(["Birds", "fly", "."], [True, False, False], [1, 1, 1], ["nsubj", "ROOT", "punct"], ["NOUN", "VERB", "PUNCT"], ["NNS", "VBP", "."], ["bird", "fly", "."]),
        make_doc(["Fish", "swim", "."], [True, False, False], [1, 1, 1], ["nsubj", "ROOT", "punct"], ["NOUN", "VERB", "PUNCT"], ["NNS", "VBP", "."], ["fish", "swim", "."]),
    ]

    class FakeNLP:
        def pipe(self, texts, batch_size):
            assert list(texts) == [atom.text for atom in atoms]
            assert batch_size == 2
            return docs

    monkeypatch.setattr(linguistic, "_load_model", lambda: FakeNLP())
    response = linguistic.analyze_atoms(atoms)
    assert [analysis.atom_id for analysis in response.analyses] == ["atom-2", "atom-1"]
    source = inspect.getsource(linguistic)
    assert "httpx" not in source
    assert "ollama" not in source.lower()


def test_batching_rejects_extra_parser_documents(monkeypatch) -> None:
    atoms = [PipelineAtom(id="atom-1", text="Fish swim.")]
    doc = make_doc(
        ["Fish", "swim", "."],
        [True, False, False],
        [1, 1, 1],
        ["nsubj", "ROOT", "punct"],
        ["NOUN", "VERB", "PUNCT"],
        ["NNS", "VBP", "."],
        ["fish", "swim", "."],
    )

    class FakeNLP:
        def pipe(self, texts, batch_size):
            return [doc, doc]

    monkeypatch.setattr(linguistic, "_load_model", lambda: FakeNLP())
    with pytest.raises(linguistic.LinguisticAnalysisError, match="incomplete analysis batch"):
        linguistic.analyze_atoms(atoms)


def test_model_absence_has_actionable_setup_message(monkeypatch) -> None:
    monkeypatch.setattr(linguistic, "_nlp", None)
    monkeypatch.setattr(
        linguistic.importlib,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("missing")),
    )
    with pytest.raises(linguistic.LinguisticAnalysisConfigurationError, match="run-verigraph --setup"):
        linguistic.warm()


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("VERIGRAPH_RUN_LINGUISTICS_INTEGRATION") != "1",
    reason="set VERIGRAPH_RUN_LINGUISTICS_INTEGRATION=1 to load the packaged parser",
)
def test_packaged_model_audit_over_representative_claims() -> None:
    atoms = [
        PipelineAtom(id="supported", text="The council approved the proposal in March 2022."),
        PipelineAtom(id="refuted", text="The report did not list the organization as a member."),
        PipelineAtom(id="nei", text="Officials may announce a second project next year."),
        PipelineAtom(id="conflicting", text="One agency said the bridge was open, but another reported it was closed."),
    ]
    response = linguistic.analyze_atoms(atoms)
    assert [item.atom_id for item in response.analyses] == [atom.id for atom in atoms]
    assert all(item.tokens for item in response.analyses)
    assert all(item.frames for item in response.analyses)
