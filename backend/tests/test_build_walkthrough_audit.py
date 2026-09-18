from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "build_walkthrough", ROOT / "scripts" / "build_walkthrough.py"
)
assert SPEC is not None and SPEC.loader is not None
build_walkthrough = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_walkthrough)


def presentation_inputs(
    *,
    text: str,
    role: str = "CORE",
    verdict: str = "SUPPORTED",
    required_terms: list[str] | None = None,
    allowed_roles: list[str] | None = None,
) -> tuple[dict, dict, dict]:
    case = {
        "id": "example-case",
        "claim": text,
        "label": "SUPPORTED",
        "documents": [],
    }
    run = {
        "atoms": [
            {
                "id": "atom-1",
                "text": text,
                "sourceText": "first client and server",
                "role": role,
            }
        ],
        "warnings": [],
        "assessment": {
            "obligations": [
                {
                    "atomId": "atom-1",
                    "sufficiency": "INSUFFICIENT",
                    "supportSpanIds": [],
                    "refuteSpanIds": [],
                    "scopeChecks": [],
                    "missingInformation": "",
                }
            ]
        },
        "reasoning": [],
        "verdict": {"verdict": verdict},
    }
    audit = {
        "approved": True,
        "atomChecks": [
            {
                "requiredTerms": required_terms
                or ["World Wide Web", "first client", "server", "1990"],
                "allowedRoles": allowed_roles or ["CORE", "TEMPORAL_CONSTRAINT"],
            }
        ],
        "requiredOperators": [],
        "prohibitedDecisiveOperators": [],
        "referenceVerdict": "SUPPORTED",
        "maxDefaultGraphNodes": 9,
    }
    return case, run, audit


def test_semantically_equivalent_atom_copy_and_ambiguous_role_are_accepted() -> None:
    case, run, audit = presentation_inputs(
        text=(
            "Tim Berners-Lee created the first client and server for the "
            "World Wide Web in 1990."
        )
    )

    assert build_walkthrough.presentation_run_errors(case, run, audit) == []


def test_missing_semantic_commitment_is_rejected_without_exact_text_matching() -> None:
    case, run, audit = presentation_inputs(
        text="The prize was awarded for Albert Einstein's theory of relativity.",
        required_terms=["Nobel Prize", "Physics", "1921", "Albert Einstein"],
        allowed_roles=["CORE"],
    )

    errors = build_walkthrough.presentation_run_errors(case, run, audit)

    assert len(errors) == 1
    assert "Nobel Prize, Physics, 1921" in errors[0]


def test_audit_collects_semantic_role_and_verdict_failures() -> None:
    case, run, audit = presentation_inputs(
        text="A related statement.",
        role="ATTRIBUTION",
        verdict="NOT_ENOUGH_EVIDENCE",
        required_terms=["required fact"],
        allowed_roles=["CORE"],
    )

    errors = build_walkthrough.presentation_run_errors(case, run, audit)

    assert len(errors) == 3
    assert any("semantic commitments" in error for error in errors)
    assert any("role ATTRIBUTION" in error for error in errors)
    assert any("verdict NOT_ENOUGH_EVIDENCE" in error for error in errors)


def test_presentation_audit_rejects_wrong_atomic_states() -> None:
    case, run, audit = presentation_inputs(
        text=(
            "Tim Berners-Lee created the first client and server for the "
            "World Wide Web in 1990."
        )
    )
    run["verdict"]["obligations"] = [
        {"obligationId": "atom-1", "state": "CONFLICTING"}
    ]
    audit["expectedObligationStates"] = ["SUPPORTED"]

    errors = build_walkthrough.presentation_run_errors(case, run, audit)

    assert len(errors) == 1
    assert "atomic states" in errors[0]
