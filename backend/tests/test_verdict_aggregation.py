import pytest

from verigraph_backend.schemas import VerdictAggregationRequest
from verigraph_backend.verdict_aggregation import aggregate_verdict


def request(composition, relations):
    atoms = [
        {"id": f"a{index}", "text": f"Atom {index}", "sourceText": "claim", "start": 0, "end": 5, "role": "CORE"}
        for index in range(1, len(relations) + 1)
    ]
    return VerdictAggregationRequest.model_validate({
        "claimId": "case", "claim": "claim",
        "composition": composition, "atoms": atoms,
        "evidence": [{"atomId": atom["id"], "spans": [{"id": "s", "documentId": "d", "text": "evidence", "start": 0, "end": 8}]} for atom in atoms],
        "classifications": [{"atomId": atom["id"], "relations": [{"spanId": "s", "documentId": "d", "relation": relation} for relation in relation_set]} for atom, relation_set in zip(atoms, relations)],
    })


@pytest.mark.parametrize(("composition", "relations", "verdict"), [
    ("SINGLE", [["ENTAILMENT"]], "SUPPORTED"),
    ("SINGLE", [["CONTRADICTION"]], "REFUTED"),
    ("SINGLE", [["ENTAILMENT", "CONTRADICTION"]], "CONFLICTING_EVIDENCE"),
    ("SINGLE", [["NEUTRAL"]], "NOT_ENOUGH_EVIDENCE"),
    ("AND", [["ENTAILMENT"], ["CONTRADICTION"]], "REFUTED"),
    ("AND", [["ENTAILMENT"], ["NEUTRAL"]], "NOT_ENOUGH_EVIDENCE"),
    ("OR", [["ENTAILMENT"], ["CONTRADICTION"]], "SUPPORTED"),
    ("OR", [["CONTRADICTION"], ["CONTRADICTION"]], "REFUTED"),
    ("OR", [["CONTRADICTION"], ["NEUTRAL"]], "NOT_ENOUGH_EVIDENCE"),
])
def test_aggregation_truth_table(composition, relations, verdict):
    result = aggregate_verdict(request(composition, relations))
    assert result.verdict.value == verdict


def test_reference_label_is_not_an_aggregation_input_and_relations_are_deduplicated():
    result = aggregate_verdict(request("SINGLE", [["ENTAILMENT", "ENTAILMENT"]]))
    assert result.verdict.value == "SUPPORTED"
    assert len(result.obligations[0].support_edge_ids) == 1
    assert any(item.code == "DUPLICATE_ARGUMENT_RELATION" for item in result.warnings)
