from __future__ import annotations

import json

import pytest

from verigraph_backend.grounded_evidence_audit import (
    GroundedEvidenceAuditOutputError,
    _audit_input,
    _parse_audit,
    classifications_from_grounded_audit,
)
from verigraph_backend.schemas import (
    GroundedClaimPosition,
    NLIAtomEvidence,
    NLIInputSpan,
    NLIRelation,
    PipelineAtom,
)


def inputs():
    atoms = [PipelineAtom(id="a1", text="The archive opened in 2021.")]
    evidence = [
        NLIAtomEvidence(
            atom_id="a1",
            spans=[
                NLIInputSpan(
                    id="s1",
                    document_id="d1",
                    text="The archive opened in 2021.",
                    context="Officials said the archive opened in 2021.",
                ),
                NLIInputSpan(
                    id="s2",
                    document_id="d1",
                    text="Visitors were admitted only on weekends.",
                ),
            ],
        )
    ]
    return atoms, evidence


def envelope(content):
    return {"done": True, "message": {"content": json.dumps(content)}}


def test_input_uses_grounded_candidate_enums() -> None:
    atoms, evidence = inputs()
    prompt, mapped, schema = _audit_input(
        "The archive opened in 2021.", atoms, evidence, {"d1": "Archive report"}
    )

    assert "O1-E1 | Archive report" in prompt
    assert list(mapped) == ["O1"]
    assert schema["properties"]["supportIds"]["items"]["enum"] == [
        "O1-E1",
        "O1-E2",
    ]


def test_parse_maps_claim_position_and_selected_codes_to_real_span_ids() -> None:
    atoms, evidence = inputs()
    _prompt, mapped, _schema = _audit_input("claim", atoms, evidence, {})
    result = _parse_audit(
        envelope(
            {
                "position": "MIXED_OR_MISLEADING",
                "supportIds": ["O1-E1"],
                "attackIds": [],
                "contextIds": ["O1-E2"],
                "reason": "Weekend-only access materially qualifies opening.",
            }
        ),
        mapped,
    )

    assert result.claim_position.position == GroundedClaimPosition.mixed_or_misleading
    assert result.claim_position.support_span_ids == ["s1"]
    assert result.claim_position.context_span_ids == ["s2"]
    assert result.obligations[0].support_span_ids == ["s1"]


def test_parse_rejects_invented_candidate_id() -> None:
    atoms, evidence = inputs()
    _prompt, mapped, _schema = _audit_input("claim", atoms, evidence, {})
    with pytest.raises(GroundedEvidenceAuditOutputError, match="unknown evidence"):
        _parse_audit(
            envelope(
                {
                    "position": "SUPPORT_ONLY",
                    "supportIds": ["INVENTED"],
                    "attackIds": [],
                    "contextIds": [],
                    "reason": "Unsupported.",
                }
            ),
            mapped,
        )


def test_parse_rejects_decisive_position_without_grounding() -> None:
    atoms, evidence = inputs()
    _prompt, mapped, _schema = _audit_input("claim", atoms, evidence, {})
    with pytest.raises(GroundedEvidenceAuditOutputError, match="ungrounded decisive"):
        _parse_audit(
            envelope(
                {
                    "position": "ATTACK_ONLY",
                    "supportIds": [],
                    "attackIds": [],
                    "contextIds": ["O1-E2"],
                    "reason": "No attack was actually selected.",
                }
            ),
            mapped,
        )


def test_insufficient_position_discards_decisive_ids() -> None:
    atoms, evidence = inputs()
    _prompt, mapped, _schema = _audit_input("claim", atoms, evidence, {})
    result = _parse_audit(
        envelope(
            {
                "position": "INSUFFICIENT",
                "supportIds": ["O1-E1"],
                "attackIds": ["O1-E2"],
                "contextIds": ["O1-E2"],
                "reason": "The available evidence is incomplete.",
            }
        ),
        mapped,
    )

    assert result.claim_position.support_span_ids == []
    assert result.claim_position.attack_span_ids == []
    assert result.obligations[0].state == "UNRESOLVED"


def test_classifications_use_only_validated_audit_selections() -> None:
    atoms, evidence = inputs()
    _prompt, mapped, _schema = _audit_input("claim", atoms, evidence, {})
    audit = _parse_audit(
        envelope(
            {
                "position": "MIXED_OR_MISLEADING",
                "supportIds": ["O1-E1"],
                "attackIds": ["O1-E2"],
                "contextIds": [],
                "reason": "Evidence exists on both sides.",
            }
        ),
        mapped,
    )

    response = classifications_from_grounded_audit(evidence, audit)

    assert response.provider == "ollama"
    assert [item.relation for item in response.classifications[0].relations] == [
        NLIRelation.entailment,
        NLIRelation.contradiction,
    ]


def test_support_only_requires_selected_support_for_every_obligation() -> None:
    atoms = [
        PipelineAtom(id="a1", text="The archive opened."),
        PipelineAtom(id="a2", text="The archive opens daily."),
    ]
    evidence = [
        NLIAtomEvidence(
            atom_id=atom.id,
            spans=[NLIInputSpan(id=f"s{index}", document_id="d1", text=atom.text)],
        )
        for index, atom in enumerate(atoms, start=1)
    ]
    _prompt, mapped, _schema = _audit_input("compound claim", atoms, evidence, {})

    result = _parse_audit(
        envelope(
            {
                "position": "SUPPORT_ONLY",
                "supportIds": ["O1-E1"],
                "attackIds": [],
                "contextIds": [],
                "reason": "Only the first obligation was established.",
            }
        ),
        mapped,
    )

    assert result.claim_position.position == GroundedClaimPosition.insufficient
    assert result.claim_position.support_span_ids == []
    assert all(item.state == "UNRESOLVED" for item in result.obligations)


def test_one_physical_span_can_support_multiple_obligations() -> None:
    atoms = [
        PipelineAtom(id="a1", text="The sky turned orange."),
        PipelineAtom(id="a2", text="The sky turned red."),
    ]
    shared = NLIInputSpan(
        id="shared",
        document_id="d1",
        text="Reports described the sky turning orange and red.",
    )
    evidence = [
        NLIAtomEvidence(atom_id=atom.id, spans=[shared]) for atom in atoms
    ]
    _prompt, mapped, _schema = _audit_input("compound claim", atoms, evidence, {})

    result = _parse_audit(
        envelope(
            {
                "position": "SUPPORT_ONLY",
                "supportIds": ["O1-E1"],
                "attackIds": [],
                "contextIds": [],
                "reason": "One sentence establishes both color obligations.",
            }
        ),
        mapped,
    )

    assert result.claim_position.position == GroundedClaimPosition.support_only
    assert result.claim_position.support_span_ids == ["shared"]
    assert [item.state for item in result.obligations] == ["SUPPORTED", "SUPPORTED"]
    assert all(item.support_span_ids == ["shared"] for item in result.obligations)
