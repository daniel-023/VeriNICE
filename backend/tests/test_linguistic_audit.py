from verigraph_backend.linguistic_analysis import (
    audit_role,
    claim_preservation_warnings,
    obligation_warnings,
    summary_from_analysis,
)
from verigraph_backend.schemas import (
    AtomLinguisticAnalysis,
    DecomposedAtom,
    LinguisticCue,
    LinguisticSpan,
    LinguisticWarningCode,
    ObligationRole,
    PropositionFrame,
    RoleAuditStatus,
)


def atom(role: ObligationRole, text: str = "The city cut emissions by 20%.") -> DecomposedAtom:
    return DecomposedAtom(
        id="atom-1",
        text=text,
        source_text=text,
        start=0,
        end=len(text),
        role=role,
    )


def analysis(*cue_kinds: str, frames: int = 1, partial: bool = False) -> AtomLinguisticAnalysis:
    return AtomLinguisticAnalysis(
        atom_id="atom-1",
        frames=[
            PropositionFrame(
                id=f"frame-{index}",
                predicate=LinguisticSpan(id=f"predicate-{index}", text="cut", start=0, end=3),
            )
            for index in range(frames)
        ],
        cues=[
            LinguisticCue(id=f"cue-{index}", text=kind, start=0, end=len(kind), kind=kind)
            for index, kind in enumerate(cue_kinds)
        ],
        entities=[],
        tokens=[],
        status="partial" if partial else "complete",
        unresolved=["subject"] if partial else [],
    )


def test_role_audit_matches_expected_numeric_signal() -> None:
    parsed = analysis("numeric")
    assert audit_role(atom(ObligationRole.numeric_constraint), parsed) is RoleAuditStatus.match


def test_role_audit_flags_clear_incompatible_signal() -> None:
    parsed = analysis("temporal")
    assert audit_role(atom(ObligationRole.numeric_constraint), parsed) is RoleAuditStatus.mismatch
    assert LinguisticWarningCode.role_cue_mismatch in obligation_warnings(
        atom(ObligationRole.numeric_constraint), parsed, RoleAuditStatus.mismatch
    )


def test_partial_analysis_is_inconclusive_and_warned() -> None:
    parsed = analysis(partial=True)
    audit = audit_role(atom(ObligationRole.modality_constraint), parsed)
    assert audit is RoleAuditStatus.inconclusive
    warnings = obligation_warnings(atom(ObligationRole.modality_constraint), parsed, audit)
    assert LinguisticWarningCode.partial_linguistic_analysis in warnings
    assert LinguisticWarningCode.unresolved_subject in warnings


def test_claim_audit_detects_lost_negation_and_numeric_information() -> None:
    claim = analysis("negation", "numeric")
    claim.atom_id = "claim"
    obligation = atom(ObligationRole.core, "The city cut emissions.")
    warnings = claim_preservation_warnings(claim, [obligation], [analysis()])
    assert LinguisticWarningCode.negation_not_preserved in warnings
    assert LinguisticWarningCode.numeric_information_not_preserved in warnings


def test_summary_is_compact_and_keeps_stable_warning_codes() -> None:
    parsed = analysis("numeric", frames=2)
    warning_codes = obligation_warnings(atom(ObligationRole.numeric_constraint), parsed, RoleAuditStatus.match)
    summary = summary_from_analysis(
        atom(ObligationRole.numeric_constraint), parsed, RoleAuditStatus.match, warning_codes
    )
    assert summary.atom_id == "atom-1"
    assert summary.cue_kinds == ["numeric"]
    assert summary.warnings == [
        LinguisticWarningCode.multiple_proposition_frames,
        LinguisticWarningCode.qualifier_attachment_unclear,
    ]
