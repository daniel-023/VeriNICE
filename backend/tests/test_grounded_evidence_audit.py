from __future__ import annotations

import json

import pytest

from verinice_backend.grounded_evidence_audit import GroundedEvidenceAuditOutputError, _audit_input, _parse_audit
from verinice_backend.schemas import AssessmentAtomEvidence, AssessmentInputSpan, DemoDocument, EvidenceContextSpan, EvidenceScopeCheck, PipelineAtom


def fixtures():
    atoms = [PipelineAtom(id="a1", text="The US archive opened in 2021.")]
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[
        AssessmentInputSpan(id="s1", document_id="d1", text="The US archive opened in 2021.", start=0, end=30),
        AssessmentInputSpan(id="s2", document_id="d2", text="The Australian archive opened in 2021.", start=0, end=39),
    ])]
    documents = [
        DemoDocument(id="d1", title="US archive", url="https://state.gov/archive", text="The US archive opened in 2021."),
        DemoDocument(id="d2", title="Australia archive", url="https://example.au/archive", text="The Australian archive opened in 2021."),
    ]
    checks = {"a1": [
        EvidenceScopeCheck(spanId="s1", documentId="d1", status="MATCH", claimJurisdictions=["US"], evidenceJurisdictions=["US"], reason="Same jurisdiction."),
        EvidenceScopeCheck(spanId="s2", documentId="d2", status="MISMATCH", claimJurisdictions=["US"], evidenceJurisdictions=["AU"], reason="Different jurisdiction."),
    ]}
    return atoms, evidence, documents, checks


def envelope(obligations, omission=None):
    return {"done": True, "message": {"content": json.dumps({
        "obligations": obligations,
        "materialOmission": omission or {"detected": False, "supportIds": [], "contextIds": [], "reason": "No material omission."},
    })}}


def assessment_item(**changes):
    item = {"obligationId": "O1", "atomTrueIds": ["O1-E1"], "atomFalseIds": [], "contextIds": [], "sufficiency": "SUFFICIENT", "missingInformation": "", "reason": "The sentence establishes the atomic claim."}
    item.update(changes)
    return item


def test_input_excludes_explicit_jurisdiction_mismatch_from_model_candidates() -> None:
    atoms, evidence, documents, checks = fixtures()
    prompt, mapped, schema = _audit_input("claim", atoms, evidence, documents, checks)
    assert "O1-E1 | US archive" in prompt
    assert "Australian archive" not in prompt
    assert list(mapped["O1"][1]) == ["O1-E1"]
    obligation_schema = schema["properties"]["obligations"]["properties"]["O1"]
    assert obligation_schema["properties"]["atomTrueIds"]["items"]["enum"] == ["O1-E1"]


def test_input_keeps_reading_context_separate() -> None:
    atoms, evidence, documents, checks = fixtures()
    evidence[0].spans[0].context_spans = [EvidenceContextSpan(id="c1", documentId="d1", text="Officials discussed the archive.", start=31, end=63, direction="PREVIOUS")]
    prompt, _, _ = _audit_input("claim", atoms, evidence, documents, checks)
    assert "READING CONTEXT (not independent evidence)" in prompt


def test_parse_returns_atom_scoped_relations_sufficiency_and_scope_checks() -> None:
    atoms, evidence, documents, checks = fixtures()
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    result = _parse_audit(envelope([assessment_item()]), mapped, checks)
    assert result.obligations[0].support_span_ids == ["s1"]
    assert result.obligations[0].sufficiency == "SUFFICIENT"
    assert result.obligations[0].scope_checks[1].status == "MISMATCH"
    assert not hasattr(result, "claim_position")


def test_parse_rejects_excluded_or_unknown_candidate_id() -> None:
    atoms, evidence, documents, checks = fixtures()
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    with pytest.raises(GroundedEvidenceAuditOutputError, match="unavailable evidence"):
        _parse_audit(envelope([assessment_item(atomTrueIds=["O1-E2"])]), mapped, checks)


def test_parse_demotes_support_refute_overlap_to_context() -> None:
    atoms, evidence, documents, checks = fixtures()
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    result = _parse_audit(
        envelope([assessment_item(atomTrueIds=["O1-E1"], atomFalseIds=["O1-E1"])]),
        mapped,
        checks,
    )
    assert result.obligations[0].support_span_ids == []
    assert result.obligations[0].refute_span_ids == []
    assert result.obligations[0].context_span_ids == ["s1"]


def test_parse_demotes_identical_source_copies_with_opposing_relations() -> None:
    atoms, evidence, documents, checks = fixtures()
    evidence[0].spans[1].text = evidence[0].spans[0].text
    checks["a1"][1] = EvidenceScopeCheck(
        spanId="s2", documentId="d2", status="MATCH",
        claimJurisdictions=["US"], evidenceJurisdictions=["US"], reason="Same jurisdiction.",
    )
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    result = _parse_audit(
        envelope([assessment_item(atomTrueIds=["O1-E1"], atomFalseIds=["O1-E2"])]),
        mapped,
        checks,
    )
    assert result.obligations[0].support_span_ids == []
    assert result.obligations[0].refute_span_ids == []
    assert set(result.obligations[0].context_span_ids) == {"s1", "s2"}


def test_parse_demotes_one_sided_relations_for_cross_jurisdiction_comparison() -> None:
    atom = PipelineAtom(id="a1", text="Sweden joined NATO before Finland.")
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[
        AssessmentInputSpan(id="s1", document_id="d1", text="Sweden joined NATO in 2024.", start=0, end=28),
        AssessmentInputSpan(id="s2", document_id="d2", text="Finland joined NATO in 2023.", start=0, end=29),
    ])]
    documents = [
        DemoDocument(id="d1", title="Sweden", url="https://example.test/sweden", text="Sweden joined NATO in 2024."),
        DemoDocument(id="d2", title="Finland", url="https://example.test/finland", text="Finland joined NATO in 2023."),
    ]
    checks = {"a1": [
        EvidenceScopeCheck(spanId="s1", documentId="d1", status="MATCH", claimJurisdictions=["FI", "SE"], evidenceJurisdictions=["SE"], reason="One side."),
        EvidenceScopeCheck(spanId="s2", documentId="d2", status="MATCH", claimJurisdictions=["FI", "SE"], evidenceJurisdictions=["FI"], reason="One side."),
    ]}
    _, mapped, _ = _audit_input("claim", [atom], evidence, documents, checks)
    result = _parse_audit(
        envelope([assessment_item(atomTrueIds=["O1-E1"], atomFalseIds=["O1-E2"])]),
        mapped,
        checks,
    )
    assert result.obligations[0].support_span_ids == []
    assert result.obligations[0].refute_span_ids == []
    assert set(result.obligations[0].context_span_ids) == {"s1", "s2"}


def test_insufficient_relations_are_retained_as_provisional_annotations() -> None:
    atoms, evidence, documents, checks = fixtures()
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    result = _parse_audit(envelope([assessment_item(sufficiency="INSUFFICIENT", missingInformation="An authoritative date is needed.")]), mapped, checks)
    assert result.obligations[0].support_span_ids == ["s1"]
    assert result.obligations[0].sufficiency == "INSUFFICIENT"


@pytest.mark.parametrize("value", [False, None, "false", "null", "NONE"])
def test_missing_information_normalizes_empty_model_values(value) -> None:
    atoms, evidence, documents, checks = fixtures()
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    result = _parse_audit(envelope([assessment_item(missingInformation=value)]), mapped, checks)
    assert result.obligations[0].missing_information == ""


def test_sufficient_assessment_clears_model_missing_information() -> None:
    atoms, evidence, documents, checks = fixtures()
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    result = _parse_audit(
        envelope([
            assessment_item(
                sufficiency="SUFFICIENT",
                missingInformation="A non-decisive detail was not reported.",
            )
        ]),
        mapped,
        checks,
    )
    assert result.obligations[0].missing_information == ""


def test_material_omission_requires_sufficient_support() -> None:
    atoms, evidence, documents, checks = fixtures()
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    omission = {"detected": True, "supportIds": ["O1-E1"], "contextIds": ["O1-E1"], "reason": "A scope was omitted."}
    with pytest.raises(GroundedEvidenceAuditOutputError, match="sufficient supporting"):
        _parse_audit(envelope([assessment_item(sufficiency="PARTIAL")], omission), mapped, checks)
