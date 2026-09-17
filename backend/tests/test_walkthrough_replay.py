"""Ensure published walkthrough proofs still execute under the current operators."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from verinice_backend.schemas import (
    PipelineAtom,
    SymbolicOperator,
    SymbolicPremise,
    VerdictAggregationRequest,
)
from verinice_backend.symbolic_reasoning.operators import REGISTRY
from verinice_backend.verdict_aggregation import aggregate_verdict


ROOT = Path(__file__).resolve().parents[2]
WALKTHROUGH = ROOT / "frontend" / "public" / "walkthrough"
CASE_IDS = json.loads(
    (WALKTHROUGH / "manifest.json").read_text(encoding="utf-8")
)["caseIds"]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_published_walkthrough_replays_with_current_operators(case_id: str):
    run = json.loads(
        (WALKTHROUGH / "runs" / f"{case_id}.json").read_text(encoding="utf-8")
    )
    reference = json.loads(
        (WALKTHROUGH / "cases" / f"{case_id}.json").read_text(encoding="utf-8")
    )["label"]
    atoms = {
        item["id"]: PipelineAtom(id=item["id"], text=item["text"])
        for item in run["atoms"]
    }
    replayed_proofs = []

    for recorded in run["reasoning"]:
        proof = deepcopy(recorded)
        operator = SymbolicOperator(proof["operator"])
        profile = proof["profile"]
        proof.setdefault("preconditions", [])
        premises = [
            SymbolicPremise.model_validate(item) for item in proof["premises"]
        ]
        if operator in {SymbolicOperator.attribute_compare, SymbolicOperator.count_distinct}:
            outcome = REGISTRY[operator](atoms[proof["atomId"]], premises, profile=profile)
        else:
            outcome = REGISTRY[operator](atoms[proof["atomId"]], premises)
        replayed = (outcome["status"].value, outcome["relation"])
        recorded_effect = (proof["status"], proof["relation"])
        assert replayed == recorded_effect, proof["id"]

        proof.update(
            status=replayed[0],
            relation=replayed[1],
            expression=outcome["expression"],
            conclusion=outcome["conclusion"],
            explanation=outcome["explanation"],
            validationWarnings=outcome["validation_warnings"],
        )
        replayed_proofs.append(proof)

    request = VerdictAggregationRequest.model_validate({
        "claimId": case_id,
        "composition": run["composition"],
        "atoms": run["atoms"],
        "evidence": run["evidence"],
        "assessment": run["assessment"],
        "reasoning": replayed_proofs,
    })
    assert aggregate_verdict(request).verdict.value == reference
