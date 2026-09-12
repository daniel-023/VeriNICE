from decimal import Decimal

import pytest

from verigraph_backend.schemas import (
    AssessmentAtomEvidence, GroundedEvidenceAssessment,
    GroundedObligationAudit, MaterialOmissionCertificate, PipelineAtom,
    RetrievalDocument, SymbolicPremise,
)
from verigraph_backend.symbolic_reasoning.grounding import (
    build_candidates,
    identity_tokens,
    lexical_tokens,
    list_premises,
    normalize,
)
from verigraph_backend.symbolic_reasoning.operators import (
    execute_attribute_compare, execute_count_distinct, execute_extremum_compare,
    execute_numeric_compare, execute_set_membership, execute_temporal_compare,
)


def premise(text, kind="EVIDENCE", premise_id="p1", document_id="d1", content_hash=None, item_count=None):
    return SymbolicPremise(id=premise_id, document_id=document_id, text=text, start=0, end=len(text), kind=kind, content_hash=content_hash, item_count=item_count)


def test_normalization_is_unicode_case_and_whitespace_stable():
    assert normalize("  ＮＤＦ\n") == "ndf"
    assert "uk" in identity_tokens("The U.K. designation")
    assert "uk" in identity_tokens("The UK register")


def test_lexical_tokens_separate_trademark_symbols():
    assert "iphone" in lexical_tokens("Apple iPhone™ will go on sale.")
    assert "iphonetm" not in lexical_tokens("Apple iPhone™ will go on sale.")


def test_compiler_validation_merges_duplicates_and_omits_ungrounded_programs():
    from verigraph_backend.symbolic_reasoning.compiler import _validated_programs
    from verigraph_backend.symbolic_reasoning.grounding import Candidate

    candidates = [
        Candidate(
            id="candidate-1",
            atom_id="atom-1",
            operator="SET_MEMBERSHIP",
            summary="Check list membership.",
            premise_ids=("premise-1", "premise-2"),
            premise_texts=(("premise-1", "Alpha"), ("premise-2", "Beta")),
        )
    ]
    programs = [
        {"candidateId": "unknown", "premiseIds": ["premise-1"]},
        {"candidateId": "candidate-1", "premiseIds": ["premise-1"]},
        {"candidateId": "candidate-1", "premiseIds": ["premise-2"]},
        {"candidateId": "candidate-1", "premiseIds": ["outside"]},
    ]

    assert _validated_programs(programs, candidates) == [
        ("candidate-1", ["premise-1", "premise-2"])
    ]


def test_set_presence_and_exhaustive_absence_are_general():
    positive = PipelineAtom(id="a", text="NDF is included in the designated entities list.")
    negative = PipelineAtom(id="a", text="NDF is not included in the designated entities list.")
    item = premise("NDF", "LIST_ITEM", "item", content_hash="h")
    certificate = premise("The complete list consists of A, B and C.", "LIST_CERTIFICATE", "certificate", content_hash="h")
    assert execute_set_membership(positive, [item])["status"].value == "PROVED"
    assert execute_set_membership(negative, [item])["status"].value == "DISPROVED"
    assert execute_set_membership(negative, [certificate])["status"].value == "PROVED"
    assert execute_set_membership(negative, [])["status"].value == "UNRESOLVED"


def test_set_membership_requires_exact_full_item_not_substring():
    atom = PipelineAtom(id="a", text="NDF is included in the designated list.")
    assert execute_set_membership(atom, [premise("NDF Alliance", "LIST_ITEM", "item")])["status"].value == "UNRESOLVED"


def test_set_membership_accepts_only_an_explicit_source_alias():
    atom = PipelineAtom(id="a", text="NDF is included in the designated list.")
    alias = premise("National Democratic Front (NDF) appears in official records.")
    item = premise("National Democratic Front", "LIST_ITEM", "item")
    assert execute_set_membership(atom, [alias, item])["status"].value == "PROVED"


def test_generic_multiline_list_extraction_has_offsets_count_and_hash():
    text = "The complete entities list is:\n- Alpha\n- Beta\n- Gamma\n"
    found = list_premises([RetrievalDocument(id="d", text=text)])
    items = [item for item in found.values() if item.kind == "LIST_ITEM"]
    certificate = next(item for item in found.values() if item.kind == "LIST_CERTIFICATE")
    assert [item.text for item in items] == ["Alpha", "Beta", "Gamma"]
    assert len({item.content_hash for item in items + [certificate]}) == 1
    assert certificate.item_count == 3
    assert text.encode("utf-16-le")[certificate.start * 2:certificate.end * 2].decode("utf-16-le") == certificate.text


def test_counted_member_list_is_an_exhaustive_certificate():
    text = "Five permanent members: China, France, Russian Federation, the United Kingdom, and the United States."
    found = list_premises([RetrievalDocument(id="d", text=text)])
    certificate = next(item for item in found.values() if item.kind == "LIST_CERTIFICATE")
    items = [item.text for item in found.values() if item.kind == "LIST_ITEM"]
    assert certificate.item_count == 5
    assert items == ["China", "France", "Russian Federation", "the United Kingdom", "the United States"]
    result = execute_set_membership(
        PipelineAtom(id="a", text="Australia is a permanent member of the UN Security Council."),
        list(found.values()),
    )
    assert result["status"].value == "DISPROVED"


def test_population_intro_does_not_create_set_membership_candidate():
    atom = PipelineAtom(
        id="a",
        text=(
            "Among US adults, each additional half egg consumed per day is "
            "associated with a higher risk of incident cardiovascular disease."
        ),
    )
    candidates, _ = build_candidates(
        [atom],
        [AssessmentAtomEvidence(atom_id="a", spans=[])],
        [],
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_certificate_selection_executes_against_every_server_owned_item(monkeypatch):
    from verigraph_backend.symbolic_reasoning import service

    atom = PipelineAtom(id="a", text="The register has not included Delta in the official list.")
    document = RetrievalDocument(
        id="d",
        text="Official register\nThe complete entities list is:\n- Alpha\n- Beta\n- Gamma\n",
    )
    assessment = GroundedEvidenceAssessment(
        obligations=[GroundedObligationAudit(atom_id="a", reason="No sentence selected.")],
        material_omission=MaterialOmissionCertificate(),
    )

    async def select_certificate(candidates):
        certificate_id = next(
            premise_id for premise_id in candidates[0].premise_ids if premise_id.endswith(":certificate")
        )
        return [(candidates[0].id, [certificate_id])]

    monkeypatch.setattr(service, "compile_programs", select_certificate)
    result = await service.reason_symbolically(
        [atom], [AssessmentAtomEvidence(atom_id="a")], [document], assessment
    )
    proof = result.executions[0]
    assert proof.status.value == "PROVED"
    assert proof.relation == "SUPPORTS"
    assert proof.premises[0].item_count == 3
    assert [item.text for item in proof.premises[0].list_items] == ["Alpha", "Beta", "Gamma"]
    assert all(item.content_hash == proof.premises[0].content_hash for item in proof.premises[0].list_items)


@pytest.mark.parametrize(("claim", "evidence", "status"), [
    ("The levy was more than 20 percent in 2020.", "The levy was 25 percent in 2020.", "PROVED"),
    ("The levy was at most $2 million in 2020.", "The levy was $3 million in 2020.", "DISPROVED"),
    ("The levy was more than 20 percent in 2020.", "The levy was $25 million in 2020.", "UNRESOLVED"),
    ("The levy was more than 20 percent in 2020.", "The levy was 25 percent in 2021.", "UNRESOLVED"),
])
def test_numeric_comparison_uses_decimal_and_compatible_units(claim, evidence, status):
    result = execute_numeric_compare(PipelineAtom(id="a", text=claim), [premise(evidence)])
    assert result["status"].value == status


@pytest.mark.parametrize(("claim", "evidence", "status"), [
    ("The vote happened after November 3, 2020.", "The vote happened on November 6, 2020.", "PROVED"),
    ("The vote happened before November 3, 2020.", "The vote happened on November 6, 2020.", "DISPROVED"),
    ("The vote happened after November 2020.", "The vote happened in 2020.", "UNRESOLVED"),
])
def test_temporal_comparison_uses_date_intervals(claim, evidence, status):
    result = execute_temporal_compare(PipelineAtom(id="a", text=claim), [premise(evidence)])
    assert result["status"].value == status


def test_temporal_comparison_aligns_two_named_events_without_dates_in_claim():
    atom = PipelineAtom(id="a", text="Sweden joined NATO before Finland.")
    result = execute_temporal_compare(atom, [
        premise("Sweden joined NATO on 7 March 2024."),
        premise("Finland joined NATO on 4 April 2023.", premise_id="p2"),
    ])
    assert result["status"].value == "DISPROVED"


def test_temporal_comparison_refutes_wrong_year_for_aligned_event():
    atom = PipelineAtom(id="a", text="The first iPhone went on sale in the United States in 2005.")
    result = execute_temporal_compare(atom, [
        premise("Apple's iPhone went on sale on June 29, 2007."),
        premise("Apple introduced iPhone on January 9, 2007.", premise_id="p2"),
    ])
    assert result["status"].value == "DISPROVED"


def test_distinct_value_count_supports_two_nobel_fields():
    atom = PipelineAtom(id="a", text="Marie Curie won Nobel Prizes in two different scientific fields.")
    result = execute_count_distinct(atom, [premise("Marie Curie received the Nobel Prize in Physics."), premise("Marie Curie received the Nobel Prize in Chemistry.", premise_id="p2")])
    assert result["status"].value == "PROVED"


def test_attribute_comparison_does_not_treat_generic_for_phrase_as_prize_reason():
    atom = PipelineAtom(id="a", text="Ivermectin is a treatment for coronavirus.")
    result = execute_attribute_compare(atom, [premise("Ivermectin is a treatment for parasitic worms.")])
    assert result["status"].value == "UNRESOLVED"


def test_attribute_comparison_treats_nobel_prize_year_as_edition_not_reason():
    atom = PipelineAtom(
        id="a",
        text="The Nobel Prize in Physics for 1921 was awarded to Albert Einstein.",
    )
    result = execute_attribute_compare(atom, [premise(
        "Einstein was eventually awarded the 1921 Nobel Prize in Physics for his "
        "discovery of the law of the photoelectric effect."
    )])
    assert result["status"].value == "PROVED"
    assert result["relation"] == "SUPPORTS"
    assert result["expression"] == "claimed recipient = source recipient"


def test_attribute_comparison_ignores_pronoun_overlap_in_nobel_reason():
    atom = PipelineAtom(
        id="a",
        text="The Nobel Prize in Physics for 1921 was awarded for his theory of relativity.",
    )
    result = execute_attribute_compare(atom, [premise(
        "Einstein was awarded the 1921 Nobel Prize in Physics for his discovery of "
        "the law of the photoelectric effect."
    )])
    assert result["status"].value == "DISPROVED"
    assert result["relation"] == "REFUTES"
    assert result["expression"] == "claimed reason ≠ source reason"


def test_extremum_counterexample_refutes_largest_claim():
    atom = PipelineAtom(id="a", text="Canberra is Australia's most populous capital city.")
    result = execute_extremum_compare(atom, [premise("Canberra population 473,855."), premise("Sydney population 5,557,233.", premise_id="p2")])
    assert result["status"].value == "DISPROVED"


def test_extremum_rejects_incompatible_height_definitions():
    atom = PipelineAtom(id="a", text="Mount Everest is the tallest mountain on Earth.")
    result = execute_extremum_compare(atom, [premise("Everest is 8,848 metres above sea level."), premise("Mauna Kea is 10,210 metres base to summit.", premise_id="p2")])
    assert result["status"].value == "UNRESOLVED"
    assert "INCOMPATIBLE_MEASURES" in result["validation_warnings"]


def test_attribute_location_comparison_uses_explicit_country_names():
    atom = PipelineAtom(id="a", text="The Eiffel Tower is located in Germany.")
    result = execute_attribute_compare(atom, [premise("The Eiffel Tower is in Paris, France.")])
    assert result["status"].value == "DISPROVED"


def test_attribute_location_comparison_rejects_ownership_as_location_evidence():
    atom = PipelineAtom(id="a", text="The Eiffel Tower is located in Germany.")
    result = execute_attribute_compare(atom, [
        premise("A convention was signed between Gustave Eiffel and representatives of the City.")
    ])
    assert result["status"].value == "UNRESOLVED"


def test_location_presentation_keeps_the_country_premise_not_name_only_overlap():
    from verigraph_backend.symbolic_reasoning.service import _presentation_premise_ids
    from verigraph_backend.schemas import SymbolicOperator, SymbolicStatus

    atom = PipelineAtom(id="a", text="The Eiffel Tower is located in Germany.")
    premises = {
        "ownership": premise(
            "A convention was signed between Gustave Eiffel and representatives of the City.",
            premise_id="ownership",
        ),
        "location": premise(
            "The Eiffel Tower is located in Paris, France.", premise_id="location"
        ),
    }
    selected = _presentation_premise_ids(
        SymbolicOperator.attribute_compare,
        atom,
        ["ownership", "location"],
        premises,
        SymbolicStatus.disproved,
        "claimed location = source location",
    )
    assert selected == ["location"]


def test_attribute_presentation_keeps_the_competing_exclusive_purposes():
    from verigraph_backend.symbolic_reasoning.service import _presentation_premise_ids
    from verigraph_backend.schemas import SymbolicOperator, SymbolicStatus

    atom = PipelineAtom(id="a", text="GPS was developed exclusively for civilian navigation.")
    premises = {
        "civilian": premise("Free access for civilian use.", premise_id="civilian"),
        "both": premise(
            "GPS provides navigation data to military and civilian users.", premise_id="both"
        ),
    }
    selected = _presentation_premise_ids(
        SymbolicOperator.attribute_compare, atom, ["civilian", "both"], premises,
        SymbolicStatus.disproved, "purposes = {military, civilian}",
    )
    assert selected == ["both"]


def test_attribute_presentation_keeps_prize_motivation_not_award_date():
    from verigraph_backend.symbolic_reasoning.service import _presentation_premise_ids
    from verigraph_backend.schemas import SymbolicOperator, SymbolicStatus

    atom = PipelineAtom(id="a", text="Einstein received the Nobel Prize for relativity.")
    premises = {
        "date": premise("Einstein received his Nobel Prize in 1922.", premise_id="date"),
        "reason": premise(
            "Prize motivation: for his discovery of the photoelectric effect.", premise_id="reason"
        ),
    }
    selected = _presentation_premise_ids(
        SymbolicOperator.attribute_compare, atom, ["date", "reason"], premises,
        SymbolicStatus.disproved, "claimed reason ≠ source reason",
    )
    assert selected == ["reason"]


def test_attribute_comparison_recognizes_explicit_contracted_negation():
    atom = PipelineAtom(id="a", text="Shaving makes hair grow back thicker.")
    result = execute_attribute_compare(
        atom,
        [premise("Shaving won’t make your hair regrow any thicker or faster.")],
    )
    assert result["status"].value == "DISPROVED"
