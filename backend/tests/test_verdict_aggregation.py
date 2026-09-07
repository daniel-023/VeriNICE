import pytest

from verigraph_backend.schemas import VerdictAggregationRequest
from verigraph_backend.verdict_aggregation import aggregate_verdict


def request(composition, relations, proofs=None, omission=False, sufficiency="SUFFICIENT"):
    for proof in proofs or []:
        proof.setdefault("program", {
            "version": 1,
            "steps": [{"id": "result", "operation": "MEMBER", "inputIds": [proof["id"]], "outputType": "BOOLEAN", "description": "Test program."}],
            "outputStepId": "result",
        })
    atoms = [{"id": f"a{i}", "text": f"Atom {i}", "sourceText": "claim", "start": 0, "end": 5, "role": "CORE"} for i in range(1, len(relations) + 1)]
    evidence = [{"atomId": atom["id"], "spans": [{"id": f"s{i}", "documentId": "d", "text": "evidence", "start": 0, "end": 8}]} for i, atom in enumerate(atoms, 1)]
    obligations = []
    for i, (atom, relation_set) in enumerate(zip(atoms, relations), 1):
        obligations.append({
            "atomId": atom["id"],
            "supportSpanIds": [f"s{i}"] if "SUPPORTS" in relation_set else [],
            "refuteSpanIds": [f"s{i}"] if "REFUTES" in relation_set else [],
            "contextSpanIds": [], "sufficiency": sufficiency,
            "missingInformation": "", "reason": "Grounded.", "scopeChecks": [],
        })
    payload = {
        "claimId": "case", "composition": composition, "atoms": atoms, "evidence": evidence,
        "assessment": {
            "obligations": obligations,
            "materialOmission": {"detected": omission, "supportSpanIds": (["s1"] if omission else []), "contextSpanIds": (["s1"] if omission else []), "reason": "Omission." if omission else "None."},
        },
        "reasoning": proofs or [],
    }
    return VerdictAggregationRequest.model_validate(payload)


@pytest.mark.parametrize(("composition", "relations", "verdict"), [
    ("SINGLE", [["SUPPORTS"]], "SUPPORTED"),
    ("SINGLE", [["REFUTES"]], "REFUTED"),
    ("SINGLE", [["SUPPORTS", "REFUTES"]], "CONFLICTING_EVIDENCE"),
    ("SINGLE", [["NOT_SELECTED"]], "NOT_ENOUGH_EVIDENCE"),
    ("AND", [["SUPPORTS", "REFUTES"], ["REFUTES"]], "REFUTED"),
    ("AND", [["SUPPORTS", "REFUTES"], ["SUPPORTS"]], "CONFLICTING_EVIDENCE"),
    ("AND", [["SUPPORTS"], ["NOT_SELECTED"]], "NOT_ENOUGH_EVIDENCE"),
    ("OR", [["SUPPORTS"], ["REFUTES"]], "SUPPORTED"),
    ("OR", [["SUPPORTS", "REFUTES"], ["REFUTES"]], "CONFLICTING_EVIDENCE"),
    ("OR", [["REFUTES"], ["REFUTES"]], "REFUTED"),
])
def test_composition_first_truth_table(composition, relations, verdict):
    assert aggregate_verdict(request(composition, relations)).verdict.value == verdict


def test_insufficient_assessed_relation_is_provisional_and_verdict_neutral():
    result = aggregate_verdict(request("SINGLE", [["SUPPORTS"]], sufficiency="INSUFFICIENT"))
    assert result.verdict.value == "NOT_ENOUGH_EVIDENCE"
    assert result.obligations[0].support_edge_ids == []
    assert result.obligations[0].provisional_relation_count == 1


def test_proved_symbolic_execution_adds_a_relation():
    proof = {
        "id": "p1", "atomId": "a1", "operator": "SET_MEMBERSHIP", "status": "PROVED", "relation": "SUPPORTS",
        "premiseIds": [], "premises": [], "expression": "x ∉ S", "conclusion": "true", "explanation": "Validated.", "validationWarnings": [],
    }
    result = aggregate_verdict(request("SINGLE", [["NOT_SELECTED"]], proofs=[proof]))
    assert result.verdict.value == "SUPPORTED"
    assert result.obligations[0].support_edge_ids == ["edge:SUPPORTS:inference:p1:obligation:case:a1"]


def test_unresolved_symbolic_execution_does_not_change_status():
    proof = {
        "id": "p1", "atomId": "a1", "operator": "SET_MEMBERSHIP", "status": "UNRESOLVED", "relation": None,
        "premiseIds": [], "premises": [], "expression": "x ∉ S", "conclusion": "unknown", "explanation": "Incomplete.", "validationWarnings": ["INCOMPLETE_LIST_EVIDENCE"],
    }
    assert aggregate_verdict(request("SINGLE", [["NOT_SELECTED"]], proofs=[proof])).verdict.value == "NOT_ENOUGH_EVIDENCE"


def test_material_omission_can_produce_conflicting_status():
    assert aggregate_verdict(request("SINGLE", [["SUPPORTS"]], omission=True)).verdict.value == "CONFLICTING_EVIDENCE"
