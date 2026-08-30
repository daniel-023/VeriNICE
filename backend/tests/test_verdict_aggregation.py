import pytest

from verigraph_backend.schemas import VerdictAggregationRequest
from verigraph_backend.verdict_aggregation import aggregate_verdict


def request(composition, relations, material_omission=None, claim_audit=None):
    atoms = [
        {"id": f"a{index}", "text": f"Atom {index}", "sourceText": "claim", "start": 0, "end": 5, "role": "CORE"}
        for index in range(1, len(relations) + 1)
    ]
    payload = {
        "claimId": "case",
        "composition": composition, "atoms": atoms,
        "evidence": [{"atomId": atom["id"], "spans": [{"id": "s", "documentId": "d", "text": "evidence", "start": 0, "end": 8}]} for atom in atoms],
        "classifications": [{"atomId": atom["id"], "relations": [{"spanId": "s", "documentId": "d", "relation": relation} for relation in relation_set]} for atom, relation_set in zip(atoms, relations)],
    }
    if material_omission is not None:
        payload["materialOmission"] = material_omission
    if claim_audit is not None:
        payload["claimAudit"] = claim_audit
    return VerdictAggregationRequest.model_validate(payload)


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


def test_grounded_material_omission_produces_conflict_without_an_attack_edge():
    result = aggregate_verdict(
        request(
            "SINGLE",
            [["ENTAILMENT"]],
            {
                "detected": True,
                "supportSpanIds": ["s"],
                "contextSpanIds": ["s"],
                "reason": "The source supplies a materially omitted eligibility condition.",
            },
        )
    )

    assert result.verdict.value == "CONFLICTING_EVIDENCE"
    assert result.positions.material_omission_position is True
    assert "Material-omission position: yes" in result.rule_trace[-2]


def test_material_omission_certificate_must_reference_a_support_relation():
    with pytest.raises(ValueError, match="support spans"):
        aggregate_verdict(
            request(
                "SINGLE",
                [["NEUTRAL"]],
                {
                    "detected": True,
                    "supportSpanIds": ["s"],
                    "contextSpanIds": ["s"],
                    "reason": "Purported omission.",
                },
            )
        )


@pytest.mark.parametrize(
    ("position", "support_ids", "attack_ids", "verdict"),
    [
        ("SUPPORT_ONLY", ["s"], [], "SUPPORTED"),
        ("ATTACK_ONLY", [], ["s"], "REFUTED"),
        ("MIXED_OR_MISLEADING", ["s"], ["s"], "CONFLICTING_EVIDENCE"),
        ("INSUFFICIENT", [], [], "NOT_ENOUGH_EVIDENCE"),
    ],
)
def test_grounded_claim_position_overrides_noisy_obligation_truth_table(
    position, support_ids, attack_ids, verdict
):
    result = aggregate_verdict(
        request(
            "SINGLE",
            [["NEUTRAL"]],
            claim_audit={
                "position": position,
                "supportSpanIds": support_ids,
                "attackSpanIds": attack_ids,
                "contextSpanIds": [],
                "reason": "Validated overall evidence position.",
            },
        )
    )

    assert result.verdict.value == verdict
    assert result.positions.grounded_claim_position.value == position
