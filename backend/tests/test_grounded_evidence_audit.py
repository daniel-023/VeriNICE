from __future__ import annotations

import json

import pytest

from verinice_backend.grounded_evidence_audit import (
    AUDIT_INSTRUCTIONS,
    GroundedEvidenceAuditOutputError,
    _audit_input,
    _parse_audit,
)
from verinice_backend.schemas import AssessmentAtomEvidence, AssessmentInputSpan, DemoDocument, EvidenceContextSpan, EvidenceScopeCheck, PipelineAtom


def test_prompt_handles_exclusivity_and_explicit_historical_conflict() -> None:
    normalized = " ".join(AUDIT_INSTRUCTIONS.split())
    assert "one explicit in-scope counterexample is sufficient refutation" in normalized
    assert "later use alone cannot" in normalized
    assert "select both sides and mark the joint bundle SUFFICIENT" in normalized
    assert "Do not demand measurements" in normalized


def test_explicit_competing_development_purpose_is_decisive_refutation() -> None:
    atom = PipelineAtom(
        id="a1", text="Orion was developed exclusively for civilian navigation."
    )
    texts = [
        "Orion is available to military and civilian users.",
        "Orion was initially developed to improve military navigation.",
    ]
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[
        AssessmentInputSpan(
            id=f"s{index}", document_id="d1", text=text,
            start=0, end=len(text),
        )
        for index, text in enumerate(texts, start=1)
    ])]
    documents = [DemoDocument(
        id="d1", title="Orion history", url="https://example.test/orion",
        text=" ".join(texts),
    )]
    checks = {"a1": [EvidenceScopeCheck(
        spanId=f"s{index}", documentId="d1", status="NOT_APPLICABLE",
        claimJurisdictions=[], evidenceJurisdictions=[], reason="No jurisdiction.",
    ) for index in range(1, 3)]}
    _, mapped, _ = _audit_input("claim", [atom], evidence, documents, checks)

    result = _parse_audit(
        envelope([
            assessment_item(
                atomTrueIds=[],
                atomFalseIds=["O1-E1"],
                sufficiency="PARTIAL",
                missingInformation="The original purpose is needed.",
            )
        ]),
        mapped,
        checks,
    )

    obligation = result.obligations[0]
    assert obligation.refute_span_ids == ["s2"]
    assert obligation.sufficiency == "SUFFICIENT"
    assert obligation.missing_information == ""


def test_incompatible_extremum_measurements_are_not_decisive_refutation() -> None:
    atom = PipelineAtom(id="a1", text="Mount Astra is the tallest mountain on Earth.")
    texts = [
        "Mount Astra is 8,800 metres above sea level.",
        "Mount Borealis rises 10,000 metres from base to top.",
    ]
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[
        AssessmentInputSpan(
            id=f"s{index}", document_id="d1", text=text,
            start=0, end=len(text),
        )
        for index, text in enumerate(texts, start=1)
    ])]
    documents = [DemoDocument(
        id="d1", title="Mountain measurements", url="https://example.test/mountains",
        text=" ".join(texts),
    )]
    checks = {"a1": [EvidenceScopeCheck(
        spanId=f"s{index}", documentId="d1", status="NOT_APPLICABLE",
        claimJurisdictions=[], evidenceJurisdictions=[], reason="No jurisdiction.",
    ) for index in range(1, 3)]}
    _, mapped, _ = _audit_input("claim", [atom], evidence, documents, checks)

    result = _parse_audit(
        envelope([assessment_item(
            atomTrueIds=[], atomFalseIds=["O1-E1", "O1-E2"]
        )]),
        mapped,
        checks,
    )

    obligation = result.obligations[0]
    assert obligation.refute_span_ids == []
    assert obligation.context_span_ids == ["s1", "s2"]
    assert obligation.sufficiency == "PARTIAL"
    assert "one definition" in obligation.missing_information


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


def numeric_fixtures(atom_text: str, evidence_text: str):
    atom = PipelineAtom(id="a1", text=atom_text)
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[
        AssessmentInputSpan(
            id="s1", document_id="d1", text=evidence_text,
            start=0, end=len(evidence_text),
        ),
    ])]
    documents = [DemoDocument(
        id="d1", title="Employment data", url="https://example.test/data",
        text=evidence_text,
    )]
    checks = {"a1": [EvidenceScopeCheck(
        spanId="s1", documentId="d1", status="NOT_APPLICABLE",
        claimJurisdictions=[], evidenceJurisdictions=[], reason="No jurisdiction.",
    )]}
    return atom, evidence, documents, checks


def test_numeric_support_requires_a_relevant_compatible_quantity() -> None:
    atom, evidence, documents, checks = numeric_fixtures(
        "The pandemic lost 22 million jobs.",
        "This employment series can represent jobs added or lost in an economy.",
    )
    _, mapped, _ = _audit_input("claim", [atom], evidence, documents, checks)
    result = _parse_audit(envelope([assessment_item()]), mapped, checks)
    obligation = result.obligations[0]
    assert obligation.support_span_ids == []
    assert obligation.context_span_ids == ["s1"]
    assert obligation.sufficiency == "PARTIAL"
    assert "claimed quantity" in obligation.missing_information


def test_unrelated_number_cannot_refute_a_numeric_claim() -> None:
    atom, evidence, documents, checks = numeric_fixtures(
        "The pandemic lost 22 million jobs.",
        "Travelers were quarantined for 14 days during the pandemic.",
    )
    _, mapped, _ = _audit_input("claim", [atom], evidence, documents, checks)
    result = _parse_audit(
        envelope([assessment_item(atomTrueIds=[], atomFalseIds=["O1-E1"])]),
        mapped,
        checks,
    )
    obligation = result.obligations[0]
    assert obligation.refute_span_ids == []
    assert obligation.context_span_ids == ["s1"]
    assert obligation.sufficiency == "PARTIAL"


@pytest.mark.parametrize("contraction", ["doesn't", "doesn’t"])
def test_contracted_direct_negation_can_refute_a_numeric_claim(contraction: str) -> None:
    atom, evidence, documents, checks = numeric_fixtures(
        "Swallowed gum sits in your stomach for seven years before it can be digested.",
        f"If you swallow gum, it {contraction} stay in your stomach.",
    )
    _, mapped, _ = _audit_input("claim", [atom], evidence, documents, checks)
    result = _parse_audit(
        envelope([
            assessment_item(
                atomTrueIds=[],
                atomFalseIds=["O1-E1"],
                reason="The evidence directly rejects the claimed duration.",
            )
        ]),
        mapped,
        checks,
    )
    obligation = result.obligations[0]
    assert obligation.refute_span_ids == ["s1"]
    assert obligation.context_span_ids == []
    assert obligation.sufficiency == "SUFFICIENT"


def test_spelled_out_quantity_keeps_only_independently_decisive_refutation() -> None:
    atom = PipelineAtom(
        id="a1",
        text="Swallowed gum sits in your stomach for seven years before it can be digested.",
    )
    texts = [
        "If you swallow gum, it doesn't stay in your stomach.",
        "Chewing gum generally isn't harmful if swallowed.",
        "Large amounts of swallowed gum have rarely blocked intestines.",
    ]
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[
        AssessmentInputSpan(
            id=f"s{index}", document_id="d1", text=text,
            start=sum(len(item) + 1 for item in texts[: index - 1]),
            end=sum(len(item) + 1 for item in texts[: index - 1]) + len(text),
        )
        for index, text in enumerate(texts, start=1)
    ])]
    document_text = " ".join(texts)
    documents = [DemoDocument(
        id="d1", title="Swallowed gum", url="https://example.test/gum",
        text=document_text,
    )]
    checks = {"a1": [EvidenceScopeCheck(
        spanId=f"s{index}", documentId="d1", status="NOT_APPLICABLE",
        claimJurisdictions=[], evidenceJurisdictions=[], reason="No jurisdiction.",
    ) for index in range(1, 4)]}
    _, mapped, _ = _audit_input("claim", [atom], evidence, documents, checks)
    result = _parse_audit(
        envelope([
            assessment_item(
                atomTrueIds=[], atomFalseIds=["O1-E1", "O1-E2", "O1-E3"],
                reason="The evidence refutes the claimed duration.",
            )
        ]),
        mapped,
        checks,
    )
    obligation = result.obligations[0]
    assert obligation.refute_span_ids == ["s1"]
    assert obligation.sufficiency == "SUFFICIENT"
    assert obligation.reason == (
        "The retained evidence directly refutes the atomic claim's numeric assertion."
    )


def test_rounded_large_quantity_can_support_a_descriptive_count() -> None:
    atom, evidence, documents, checks = numeric_fixtures(
        "The economy added back 11.6 million jobs.",
        "Payroll employment increased by 11.344 million jobs from April to September 2020.",
    )
    _, mapped, _ = _audit_input("claim", [atom], evidence, documents, checks)
    result = _parse_audit(envelope([assessment_item()]), mapped, checks)
    assert result.obligations[0].support_span_ids == ["s1"]
    assert result.obligations[0].sufficiency == "SUFFICIENT"
    assert result.obligations[0].reason == (
        "The selected evidence reports a compatible rounded quantity for the same measured fact."
    )


def test_numeric_guard_does_not_treat_a_calendar_year_as_a_quantity() -> None:
    atoms, evidence, documents, checks = fixtures()
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    result = _parse_audit(envelope([assessment_item()]), mapped, checks)
    assert result.obligations[0].support_span_ids == ["s1"]
    assert result.obligations[0].sufficiency == "SUFFICIENT"


def test_direct_evidence_on_both_sides_is_a_sufficient_conflict_bundle() -> None:
    atoms, evidence, documents, checks = fixtures()
    checks["a1"][1] = EvidenceScopeCheck(
        spanId="s2", documentId="d2", status="MATCH",
        claimJurisdictions=["US"], evidenceJurisdictions=["US"], reason="Same jurisdiction.",
    )
    evidence[0].spans[1].text = "The US archive did not open in 2021."
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    result = _parse_audit(
        envelope([assessment_item(
            atomTrueIds=["O1-E1"], atomFalseIds=["O1-E2"],
            sufficiency="PARTIAL", missingInformation="More evidence is needed.",
        )]),
        mapped,
        checks,
    )
    obligation = result.obligations[0]
    assert obligation.sufficiency == "SUFFICIENT"
    assert obligation.missing_information == ""
    assert obligation.reason == (
        "The selected evidence directly supports and refutes the same atomic claim."
    )


def test_material_omission_requires_sufficient_support() -> None:
    atoms, evidence, documents, checks = fixtures()
    _, mapped, _ = _audit_input("claim", atoms, evidence, documents, checks)
    omission = {"detected": True, "supportIds": ["O1-E1"], "contextIds": ["O1-E1"], "reason": "A scope was omitted."}
    with pytest.raises(GroundedEvidenceAuditOutputError, match="sufficient supporting"):
        _parse_audit(envelope([assessment_item(sufficiency="PARTIAL")], omission), mapped, checks)
