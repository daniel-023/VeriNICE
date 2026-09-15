from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "record_walkthrough", ROOT / "scripts" / "record_walkthrough.py"
)
assert SPEC is not None and SPEC.loader is not None
record_walkthrough = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(record_walkthrough)


def openapi_schema(*, properties: dict[str, object], required: list[str]) -> dict[str, object]:
    return {
        "components": {
            "schemas": {
                "VerdictAggregationRequest": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
                "EvidenceAssessmentResponse": {
                    "type": "object",
                    "properties": {"assessment": {}},
                },
                "EvidenceAssessmentRequest": {
                    "type": "object",
                    "properties": {"caseId": {}, "documents": {}, "claim": {}, "atoms": {}, "evidence": {}},
                },
            }
        }
    }


def test_current_aggregation_contract_is_accepted() -> None:
    record_walkthrough.validate_api_contract(
        openapi_schema(
            properties={"claimId": {}, "assessment": {}, "reasoning": {}},
            required=["claimId"],
        )
    )


def test_stale_aggregation_contract_explains_how_to_restart() -> None:
    with pytest.raises(RuntimeError, match=r"running backend is stale.*run-verinice --start"):
        record_walkthrough.validate_api_contract(
            openapi_schema(
                properties={"claimId": {}, "claim": {}},
                required=["claimId", "claim"],
            )
        )


def test_missing_aggregation_contract_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="does not expose"):
        record_walkthrough.validate_api_contract({"components": {"schemas": {}}})
