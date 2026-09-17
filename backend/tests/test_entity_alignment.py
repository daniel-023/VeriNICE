from __future__ import annotations

import json

import pytest

import verinice_backend.entity_alignment as entity_alignment
from verinice_backend.entity_alignment import (
    EntityAlignmentConfigurationError,
    align_identities,
    build_document_aliases,
    extract_identity_mentions,
    normalize_entity,
)
from verinice_backend.grounded_evidence_audit import _audit_input, _parse_audit
from verinice_backend.schemas import (
    AssessmentAtomEvidence,
    AssessmentInputSpan,
    DemoDocument,
    EvidenceScopeCheck,
    PipelineAtom,
)


def test_spacy_detects_both_spellings_but_exact_alignment_rejects_mismatch() -> None:
    claim = "The prize was awarded to Albert Ainstein."
    source = "The prize was awarded to Albert Einstein."

    assert any(item.text == "Albert Ainstein" for item in extract_identity_mentions(claim))
    result = align_identities(claim, {"d1": [source]}, {"d1": source})

    assert result.status == "UNRESOLVED"
    assert result.required_entities == ("Albert Ainstein",)
    assert result.matched_entities == ()
    assert align_identities(
        claim,
        {"d1": [source]},
        {"d1": source},
        relation="REFUTES",
        strict_refutation=True,
    ).status == "UNRESOLVED"


def test_missing_entity_model_has_a_clear_offline_setup_error(monkeypatch) -> None:
    monkeypatch.setattr(entity_alignment, "_NLP", None)
    monkeypatch.setattr(entity_alignment, "_NLP_ERROR", OSError("missing model"))
    entity_alignment.extract_identity_mentions.cache_clear()

    with pytest.raises(EntityAlignmentConfigurationError, match="run-verinice --prepare"):
        entity_alignment.extract_identity_mentions("A unique uncached sentence about Ada Lovelace.")


def test_document_local_full_name_and_surname_alias_work_both_directions() -> None:
    document = "Albert Einstein developed the theory. Einstein received the award."
    assert align_identities(
        "Albert Einstein received the award.", {"d1": ["Einstein received the award."]}, {"d1": document}
    ).status == "ALIGNED"
    assert align_identities(
        "Einstein received the award.", {"d1": ["Albert Einstein received the award."]}, {"d1": document}
    ).status == "ALIGNED"


def test_ambiguous_surname_and_cross_document_aliases_do_not_align() -> None:
    ambiguous = "Alex Smith spoke. Jordan Smith replied. Smith was quoted."
    assert "smith" not in build_document_aliases(ambiguous).get("alex smith", frozenset())

    result = align_identities(
        "Albert Einstein received the award.",
        {"d2": ["Einstein received the award."]},
        {"d1": "Albert Einstein was a physicist.", "d2": "Einstein received the award."},
    )
    assert result.status == "UNRESOLVED"


def test_explicit_acronym_alias_and_normalization_are_general() -> None:
    document = "World Health Organization (WHO) issued the guidance."
    assert align_identities(
        "WHO issued the guidance.",
        {"d1": ["World Health Organization issued the guidance."]},
        {"d1": document},
    ).status == "ALIGNED"
    assert normalize_entity("  Dr. Albert Einstein’s  ") == "albert einstein"


def test_audit_demotes_identity_mismatch_to_context_not_refutation() -> None:
    atom = PipelineAtom(
        id="a1", text="The Nobel Prize was awarded to Albert Ainstein."
    )
    source = "The Nobel Prize was awarded to Albert Einstein."
    span = AssessmentInputSpan(
        id="s1", document_id="d1", text=source, start=0, end=len(source)
    )
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[span])]
    documents = [DemoDocument(
        id="d1", title="Award record", url="https://example.test/award", text=source
    )]
    checks = {"a1": [EvidenceScopeCheck(
        span_id="s1", document_id="d1", status="NOT_APPLICABLE",
        reason="No jurisdiction was asserted.",
    )]}
    _, mapped, _ = _audit_input("claim", [atom], evidence, documents, checks)
    payload = {"done": True, "message": {"content": json.dumps({
        "obligations": [{
            "obligationId": "O1", "atomTrueIds": ["O1-E1"],
            "atomFalseIds": [], "contextIds": [], "sufficiency": "SUFFICIENT",
            "missingInformation": "", "reason": "The model selected it.",
        }],
        "materialOmission": {
            "detected": False, "supportIds": [], "contextIds": [], "reason": "None."
        },
    })}}

    result = _parse_audit(payload, mapped, checks, documents)
    audit = result.obligations[0]

    assert audit.support_span_ids == []
    assert audit.refute_span_ids == []
    assert audit.context_span_ids == ["s1"]
    assert audit.sufficiency == "INSUFFICIENT"
    assert audit.identity_checks[0].status.value == "UNRESOLVED"
