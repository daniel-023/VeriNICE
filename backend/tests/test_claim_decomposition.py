from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from verinice_backend import claim_decomposition
from verinice_backend.claim_decomposition import (
    ATOM_OUTPUT_SCHEMA,
    DecompositionOutputError,
    DecompositionProviderError,
    decompose_claim,
    parse_decomposition,
)


def envelope(draft: object) -> dict:
    return {
        "model": "test-model",
        "done": True,
        "message": {"role": "assistant", "content": json.dumps(draft)},
    }


def obligation(text: str, source_text: str, role: str = "CORE") -> dict:
    return {"text": text, "sourceText": source_text, "role": role}


def test_normalizes_versioned_structured_decomposition() -> None:
    claim = "Mara joined Orion in 2022 and became its chief technology officer."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation("Mara joined Orion in 2022.", "Mara joined Orion in 2022"),
                    obligation(
                        "Mara became Orion's chief technology officer.",
                        "became its chief technology officer",
                    ),
                ],
            }
        ),
        "test-model",
    )
    assert result.schema_version == 2
    assert result.composition == "AND"
    assert [atom.id for atom in result.atoms] == ["atom-1", "atom-2"]
    assert [atom.role.value for atom in result.atoms] == ["CORE", "CORE"]
    assert result.atoms[1].start == 30
    assert result.atoms[1].end == 65
    assert result.warnings == []


def test_repeated_source_text_warns_but_is_valid() -> None:
    claim = "Mara joined Orion in 2022 and became its chief technology officer."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation("Mara joined Orion in 2022.", claim),
                    obligation("Mara became Orion's chief technology officer.", claim),
                ],
            }
        ),
        "test-model",
    )
    assert [warning.code for warning in result.warnings] == ["REUSED_SOURCE_TEXT"]


def test_broad_obligation_is_removed_when_it_duplicates_all_components() -> None:
    claim = "The pandemic lost 22 million jobs and 11.6 million jobs were added back."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation(claim, claim, "NUMERIC_CONSTRAINT"),
                    obligation(
                        "The pandemic lost 22 million jobs.",
                        "The pandemic lost 22 million jobs",
                        "NUMERIC_CONSTRAINT",
                    ),
                    obligation(
                        "11.6 million jobs were added back.",
                        "11.6 million jobs were added back",
                        "NUMERIC_CONSTRAINT",
                    ),
                ],
            }
        ),
        "test-model",
    )

    assert [atom.id for atom in result.atoms] == ["atom-1", "atom-2"]
    assert [atom.text for atom in result.atoms] == [
        "The pandemic lost 22 million jobs.",
        "11.6 million jobs were added back.",
    ]
    assert [warning.code for warning in result.warnings] == [
        "REDUNDANT_COVERING_OBLIGATION_REMOVED"
    ]


def test_discourse_framing_does_not_preserve_a_redundant_covering_atom() -> None:
    claim = (
        "Right after a time where we're going through a pandemic that lost 22 million "
        "jobs at the height, we've already added back 11.6 million jobs."
    )
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation(claim, claim, "TEMPORAL_CONSTRAINT"),
                    obligation(
                        "The pandemic lost 22 million jobs at the height.",
                        "pandemic that lost 22 million jobs at the height",
                        "NUMERIC_CONSTRAINT",
                    ),
                    obligation(
                        "We've already added back 11.6 million jobs.",
                        "we've already added back 11.6 million jobs",
                        "NUMERIC_CONSTRAINT",
                    ),
                ],
            }
        ),
        "test-model",
    )
    assert [atom.text for atom in result.atoms] == [
        "The pandemic lost 22 million jobs at the height.",
        "We've already added back 11.6 million jobs.",
    ]
    assert [warning.code for warning in result.warnings] == [
        "REDUNDANT_COVERING_OBLIGATION_REMOVED"
    ]


def test_broad_obligation_is_kept_when_components_omit_a_list_item() -> None:
    claim = (
        "Illegal drug, border crossings, and human smuggling activities have "
        "decreased where barriers are deployed."
    )
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation(claim, claim, "CAUSAL_RELATION"),
                    obligation(
                        "Border crossings have decreased where barriers are deployed.",
                        claim,
                        "CAUSAL_RELATION",
                    ),
                    obligation(
                        "Human smuggling activities have decreased where barriers are deployed.",
                        claim,
                        "CAUSAL_RELATION",
                    ),
                ],
            }
        ),
        "test-model",
    )

    assert len(result.atoms) == 3
    assert result.atoms[0].text == claim
    assert "REDUNDANT_COVERING_OBLIGATION_REMOVED" not in {
        warning.code for warning in result.warnings
    }


def test_source_text_locates_despite_punctuation_the_model_added() -> None:
    """A full stop the claim does not have there must not discard a good split."""
    claim = "Most deaths originated from bacterial pneumonia caused by face masks."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    # Closed with a full stop the claim continues past.
                    obligation("Most deaths originated from bacterial pneumonia.",
                               "Most deaths originated from bacterial pneumonia."),
                    obligation("Bacterial pneumonia was caused by face masks.",
                               "caused by face masks", "CAUSAL_RELATION"),
                ],
            }
        ),
        "test-model",
    )
    assert result.atoms[0].source_text == "Most deaths originated from bacterial pneumonia"
    assert claim[result.atoms[0].start : result.atoms[0].end] == result.atoms[0].source_text


def test_source_text_sheds_a_subject_the_claim_states_once() -> None:
    """Coordination shares a subject; a model repeats it in every span."""
    claim = "If given power they would ban animal agriculture and eliminate petrol cars."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation("They would ban animal agriculture.",
                               "they would ban animal agriculture", "CONDITIONAL"),
                    # "they would" appears only before "ban", not before "eliminate".
                    obligation("They would eliminate petrol cars.",
                               "they would eliminate petrol cars", "CONDITIONAL"),
                ],
            }
        ),
        "test-model",
    )
    assert result.atoms[1].source_text == "eliminate petrol cars"
    assert claim[result.atoms[1].start : result.atoms[1].end] == "eliminate petrol cars"


def test_source_text_sheds_a_long_shared_prefix_for_coordinated_assertions() -> None:
    claim = "Nigeria is the leading producer of cassava in Africa and the world."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation(
                        "Nigeria is the leading producer of cassava in Africa.",
                        "Nigeria is the leading producer of cassava in Africa",
                    ),
                    obligation(
                        "Nigeria is the leading producer of cassava in the world.",
                        "Nigeria is the leading producer of cassava in the world",
                    ),
                ],
            }
        ),
        "test-model",
    )

    assert [atom.text for atom in result.atoms] == [
        "Nigeria is the leading producer of cassava in Africa.",
        "Nigeria is the leading producer of cassava in the world.",
    ]
    assert result.atoms[1].source_text == "the world"
    assert claim[result.atoms[1].start : result.atoms[1].end] == "the world"


def test_shortening_stops_when_it_would_be_ambiguous() -> None:
    """A span occurring twice cannot be shortened into: it would highlight either."""
    claim = "The report lists deaths and the summary lists deaths."
    with pytest.raises(DecompositionOutputError):
        parse_decomposition(
            claim,
            envelope(
                {
                    "composition": "SINGLE",
                    # "lists deaths" occurs twice, so no shortening is admissible.
                    "obligations": [obligation("Something lists deaths.", "nobody lists deaths")],
                }
            ),
            "test-model",
        )


def test_exact_source_text_must_uniquely_locate_its_assertion() -> None:
    claim = "the rate fell in March and the rate rose in April."
    with pytest.raises(DecompositionOutputError, match="missing or ambiguous"):
        parse_decomposition(
            claim,
            envelope(
                {
                    "composition": "AND",
                    "obligations": [
                        obligation("The rate fell in March.", "the rate"),
                        obligation("The rate rose in April.", "the rate"),
                    ],
                }
            ),
            "test-model",
        )


def test_multi_sentence_claim_collapsed_into_one_obligation_warns() -> None:
    """The typed-obligation prompt regressed into quoting whole claims verbatim.

    A single obligation spanning a whole multi-sentence claim has separated
    nothing, whatever role it carries, so the pipeline says so rather than
    treating an undivided claim as atomic.
    """
    claim = (
        "The mayor called the report a hoax. She said the harbour would open in 2022. "
        "It opened in 2024."
    )
    result = parse_decomposition(
        claim,
        envelope({"composition": "SINGLE", "obligations": [obligation(claim, claim)]}),
        "test-model",
    )
    assert "UNDER_DECOMPOSED" in [warning.code for warning in result.warnings]


def test_separated_multi_sentence_claim_does_not_warn() -> None:
    claim = "The mayor called the report a hoax. It opened in 2024."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation(
                        "The mayor called the report a hoax.",
                        "The mayor called the report a hoax",
                        "ATTRIBUTION",
                    ),
                    obligation(
                        "The harbour opened in 2024.",
                        "It opened in 2024",
                        "TEMPORAL_CONSTRAINT",
                    ),
                ],
            }
        ),
        "test-model",
    )
    assert [warning.code for warning in result.warnings] == []


def test_single_sentence_claim_may_stay_one_obligation() -> None:
    claim = "The archive opened in 2021."
    result = parse_decomposition(
        claim,
        envelope({"composition": "SINGLE", "obligations": [obligation(claim, claim)]}),
        "test-model",
    )
    assert [warning.code for warning in result.warnings] == []


def test_claim_offsets_use_browser_utf16_code_units() -> None:
    claim = "🚀 The archive opened."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "SINGLE",
                "obligations": [obligation("The archive opened.", "The archive opened.")],
            }
        ),
        "test-model",
    )
    assert result.atoms[0].start == 3
    assert result.atoms[0].end == 22


@pytest.mark.parametrize(
    "draft",
    [
        {"composition": "SINGLE", "obligations": [obligation("One.", "Missing.")]},
        {"composition": "SINGLE", "obligations": [obligation("One.", "One.", "INVALID")]},
        {"composition": "SINGLE", "obligations": [obligation("One.", "One."), obligation("One.", "One.")]},
    ],
)
def test_invalid_drafts_fail_hard_validation(draft: dict) -> None:
    with pytest.raises(DecompositionOutputError):
        parse_decomposition("One.", envelope(draft), "test-model")


def test_composition_cardinality_is_normalized_without_changing_or_semantics() -> None:
    multi = parse_decomposition(
        "One. Two.",
        envelope(
            {
                "composition": "SINGLE",
                "obligations": [
                    obligation("One.", "One."),
                    obligation("Two.", "Two."),
                ],
            }
        ),
        "test-model",
    )
    single = parse_decomposition(
        "One.",
        envelope({"composition": "AND", "obligations": [obligation("One.", "One.")]}),
        "test-model",
    )
    assert multi.composition == "AND"
    assert single.composition == "SINGLE"


@pytest.mark.asyncio
async def test_live_request_uses_structured_schema(monkeypatch) -> None:
    claim = "The archive opened in 2021."
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=envelope(
                {"composition": "SINGLE", "obligations": [obligation(claim, claim)]}
            ),
        )

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(
            claim_decomposition.settings,
            ollama_url="http://ollama.test:11434",
            ollama_model="test-model",
        ),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await decompose_claim(claim, client=client)

    assert result.atoms[0].text == claim
    assert captured["body"]["format"] == ATOM_OUTPUT_SCHEMA
    assert captured["body"]["options"]["temperature"] == 0
    assert "obligations" in json.dumps(captured["body"]["format"])


@pytest.mark.asyncio
async def test_invalid_first_response_is_repaired_once(monkeypatch) -> None:
    claim = "The archive opened in 2021."
    attempts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(json.loads(request.content))
        if len(attempts) == 1:
            return httpx.Response(
                200,
                json=envelope(
                    {"composition": "SINGLE", "obligations": [obligation("Unrelated.", "Unrelated.")]}
                ),
            )
        return httpx.Response(
            200,
            json=envelope(
                {"composition": "SINGLE", "obligations": [obligation(claim, claim)]}
            ),
        )

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(claim_decomposition.settings, ollama_url="http://ollama.test:11434"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await decompose_claim(claim, client=client)

    assert len(attempts) == 2
    assert "Validation errors" in attempts[1]["messages"][1]["content"]
    assert [warning.code for warning in result.warnings] == [
        "DECOMPOSITION_REPAIRED"
    ]


@pytest.mark.asyncio
async def test_failed_repair_returns_safe_fallback(monkeypatch) -> None:
    claim = "🚀 The archive opened in 2021."
    attempts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=envelope(
                {"composition": "SINGLE", "obligations": [obligation("Unrelated.", "Unrelated.")]}
            ),
        )

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(claim_decomposition.settings, ollama_url="http://ollama.test:11434"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await decompose_claim(claim, client=client)

    assert len(attempts) == 2
    assert result.composition == "SINGLE"
    assert result.atoms[0].text == claim
    assert result.atoms[0].end == len(claim) + 1
    assert [warning.code for warning in result.warnings] == ["DECOMPOSITION_FALLBACK"]


@pytest.mark.asyncio
async def test_provider_errors_do_not_fallback(monkeypatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(claim_decomposition.settings, ollama_url="http://ollama.test:11434"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DecompositionProviderError, match="timed out"):
            await decompose_claim("A claim.", client=client)


def test_prompt_keeps_comparisons_in_one_self_contained_obligation() -> None:
    instructions = claim_decomposition.DECOMPOSITION_INSTRUCTIONS
    assert "Comparisons must retain both sides" in instructions
    assert (
        "The reservoir level in June was lower than the reservoir level in May"
        in instructions
    )
    assert "Nigeria" not in instructions


def test_prompt_keeps_qualifiers_with_the_proposition_they_modify() -> None:
    instructions = claim_decomposition.DECOMPOSITION_INSTRUCTIONS
    normalized = " ".join(instructions.split())
    assert "Do not split a modifier from the proposition it qualifies" in normalized
    assert "truth can vary independently" in normalized
    causal_example = instructions.split(
        "Claim: An inquiry concluded a faulty valve caused 37 litres of coolant to leak.",
        1,
    )[1]
    causal_example = causal_example.split("Claim: After a sensor", 1)[0]
    assert '"composition":"SINGLE"' in causal_example
    assert causal_example.count('"text"') == 1
    assert "37 litres of coolant" in causal_example


def test_prompt_requires_standalone_references_and_stays_compact() -> None:
    instructions = claim_decomposition.DECOMPOSITION_INSTRUCTIONS
    normalized = " ".join(instructions.split())
    assert "Replace pronouns and cross-obligation references" in normalized
    assert "Mina digitized the Aurora archive's index" in instructions
    assert "association or correlation alone is CORE" in normalized
    assert len(instructions.split()) <= 700


def test_prompt_examples_do_not_echo_protected_walkthrough_claims() -> None:
    normalized = claim_decomposition.DECOMPOSITION_INSTRUCTIONS.casefold()
    for distinctive_demo_phrase in (
        "clinic closures",
        "22 million jobs",
        "albert einstein",
        "world wide web",
        "orange to blood red",
    ):
        assert distinctive_demo_phrase not in normalized


def test_single_sentence_multiple_numeric_assertions_warns() -> None:
    claim = (
        "After a downturn that eliminated 2 million jobs, "
        "the economy restored 1 million jobs."
    )
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "SINGLE",
                "obligations": [obligation(claim, claim, "NUMERIC_CONSTRAINT")],
            }
        ),
        "test-model",
    )
    assert "MULTIPLE_NUMERIC_ASSERTIONS" in {
        warning.code for warning in result.warnings
    }


@pytest.mark.parametrize(
    "claim",
    [
        "The city cut emissions by 20% in 2023.",
        "ExampleCo's annual revenue for 2024 decreased from its revenue for 2023.",
        "The population grew from 5.55 million to 12 million.",
        "On 5 May 2023, WHO ended the emergency.",
        "The sky turned orange to blood red across the region.",
    ],
)
def test_numeric_dates_comparisons_and_ranges_do_not_warn(claim: str) -> None:
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "SINGLE",
                "obligations": [obligation(claim, claim, "NUMERIC_CONSTRAINT")],
            }
        ),
        "test-model",
    )
    assert "MULTIPLE_NUMERIC_ASSERTIONS" not in {
        warning.code for warning in result.warnings
    }


def test_model_introduced_cross_atom_reference_warns() -> None:
    claim = "The agency said clinic closures caused more than 8,000 deaths."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation(
                        "The agency said more than 8,000 deaths occurred.",
                        "The agency said",
                        "NUMERIC_CONSTRAINT",
                    ),
                    obligation(
                        "The agency said clinic closures caused these deaths.",
                        "clinic closures caused more than 8,000 deaths",
                        "CAUSAL_RELATION",
                    ),
                ],
            }
        ),
        "test-model",
    )
    assert [warning.code for warning in result.warnings] == [
        "NON_STANDALONE_REFERENCE"
    ]


def test_possessive_with_explicit_subject_is_not_flagged() -> None:
    claim = "Ada designed the Atlas engine and improved its controller."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation("Ada designed the Atlas engine.", "Ada designed the Atlas engine"),
                    obligation(
                        "Ada improved its controller.",
                        "improved its controller",
                    ),
                ],
            }
        ),
        "test-model",
    )
    assert "NON_STANDALONE_REFERENCE" not in {
        warning.code for warning in result.warnings
    }


def test_gendered_possessive_uses_nearest_named_claim_antecedent() -> None:
    claim = "The prize went to Albert Einstein and was awarded for his theory."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation(
                        "The prize went to Albert Einstein.",
                        "The prize went to Albert Einstein",
                    ),
                    obligation(
                        "The prize was awarded for his theory.",
                        "was awarded for his theory",
                    ),
                ],
            }
        ),
        "test-model",
    )
    assert result.atoms[1].text == (
        "The prize was awarded for Albert Einstein's theory."
    )
    assert result.warnings == []


def test_leading_definite_reference_uses_earlier_named_noun_phrase() -> None:
    claim = (
        "The Meridian Prize in Optics for 1984 was awarded to Rao, and the prize "
        "was awarded for his lens research."
    )
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation(
                        "The Meridian Prize in Optics for 1984 was awarded to Rao.",
                        "The Meridian Prize in Optics for 1984 was awarded to Rao",
                    ),
                    obligation(
                        "The prize was awarded for his lens research.",
                        "the prize was awarded for his lens research",
                    ),
                ],
            }
        ),
        "test-model",
    )

    assert result.atoms[1].text == (
        "The Meridian Prize in Optics for 1984 was awarded for Rao's lens research."
    )
    assert result.warnings == []


def test_gendered_possessive_with_named_antecedent_is_not_flagged() -> None:
    claim = "The prize went to Albert Einstein and honoured his theory."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation(
                        "The prize went to Albert Einstein.",
                        "The prize went to Albert Einstein",
                    ),
                    obligation(
                        "Albert Einstein was honoured for his theory.",
                        "honoured his theory",
                    ),
                ],
            }
        ),
        "test-model",
    )
    assert "UNRESOLVED_PERSON_REFERENCE" not in {
        warning.code for warning in result.warnings
    }


def test_explicit_subject_before_their_is_standalone() -> None:
    claim = "The CDC tracks illnesses and adds deaths to their tally."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "AND",
                "obligations": [
                    obligation("The CDC tracks illnesses.", "The CDC tracks illnesses"),
                    obligation(
                        "The CDC adds deaths to their tally.",
                        "adds deaths to their tally",
                    ),
                ],
            }
        ),
        "test-model",
    )
    assert "NON_STANDALONE_REFERENCE" not in {
        warning.code for warning in result.warnings
    }


@pytest.mark.parametrize(
    ("claim", "draft_role", "expected_role"),
    [
        (
            "Daily tea consumption is associated with lower blood pressure.",
            "CAUSAL_RELATION",
            "CORE",
        ),
        (
            "The prize was awarded to Ada in 2021.",
            "ATTRIBUTION",
            "CORE",
        ),
        (
            "The prize was awarded for Ada's discovery.",
            "CAUSAL_RELATION",
            "CORE",
        ),
        (
            "The agency said the archive closed.",
            "CORE",
            "CORE",
        ),
        (
            "Ada won prizes in at least two fields.",
            "CORE",
            "NUMERIC_CONSTRAINT",
        ),
        (
            "Shaving makes hair grow faster.",
            "CAUSAL_RELATION",
            "CAUSAL_RELATION",
        ),
        (
            "Gustave Whitehead made the first powered flight.",
            "ATTRIBUTION",
            "CORE",
        ),
    ],
)
def test_server_applies_only_high_confidence_role_corrections(
    claim: str, draft_role: str, expected_role: str
) -> None:
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "SINGLE",
                "obligations": [obligation(claim, claim, draft_role)],
            }
        ),
        "test-model",
    )
    assert result.atoms[0].role.value == expected_role


def test_thousands_separator_is_not_a_clause_boundary() -> None:
    claim = "The agency said clinic closures caused more than 8,000 deaths."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "SINGLE",
                "obligations": [obligation(claim, claim, "CAUSAL_RELATION")],
            }
        ),
        "test-model",
    )
    assert "MULTIPLE_NUMERIC_ASSERTIONS" not in {
        warning.code for warning in result.warnings
    }


def test_coordinated_numeric_description_does_not_warn() -> None:
    claim = "The red 10-car train and the blue 20-car bus collided."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "SINGLE",
                "obligations": [obligation(claim, claim, "NUMERIC_CONSTRAINT")],
            }
        ),
        "test-model",
    )
    assert "MULTIPLE_NUMERIC_ASSERTIONS" not in {
        warning.code for warning in result.warnings
    }


def test_irregular_numeric_predicates_warn_advisorially() -> None:
    claim = "The company sold 10 cars and bought 20 vans."
    result = parse_decomposition(
        claim,
        envelope(
            {
                "composition": "SINGLE",
                "obligations": [obligation(claim, claim, "NUMERIC_CONSTRAINT")],
            }
        ),
        "test-model",
    )
    assert "MULTIPLE_NUMERIC_ASSERTIONS" in {
        warning.code for warning in result.warnings
    }


@pytest.mark.asyncio
async def test_semantic_warning_is_repaired_once(monkeypatch) -> None:
    claim = "The archive opened in 2021. The archive closed in 2024."
    attempts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(json.loads(request.content))
        if len(attempts) == 1:
            draft = {
                "composition": "SINGLE",
                "obligations": [obligation(claim, claim)],
            }
        else:
            draft = {
                "composition": "AND",
                "obligations": [
                    obligation(
                        "The archive opened in 2021.",
                        "The archive opened in 2021",
                        "TEMPORAL_CONSTRAINT",
                    ),
                    obligation(
                        "The archive closed in 2024.",
                        "The archive closed in 2024",
                        "TEMPORAL_CONSTRAINT",
                    ),
                ],
            }
        return httpx.Response(200, json=envelope(draft))

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(claim_decomposition.settings, ollama_url="http://ollama.test:11434"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await decompose_claim(claim, client=client)

    assert len(attempts) == 2
    assert "UNDER_DECOMPOSED" in attempts[1]["messages"][1]["content"]
    assert result.composition == "AND"
    assert [warning.code for warning in result.warnings] == [
        "DECOMPOSITION_REPAIRED"
    ]


@pytest.mark.asyncio
async def test_failed_semantic_repair_keeps_valid_first_result(monkeypatch) -> None:
    claim = "The archive opened in 2021. The archive closed in 2024."
    attempts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=envelope(
                {
                    "composition": "SINGLE",
                    "obligations": [obligation(claim, claim)],
                }
            ),
        )

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(claim_decomposition.settings, ollama_url="http://ollama.test:11434"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await decompose_claim(claim, client=client)

    assert len(attempts) == 2
    assert result.composition == "SINGLE"
    assert [warning.code for warning in result.warnings] == [
        "UNDER_DECOMPOSED"
    ]


@pytest.mark.asyncio
async def test_numeric_warning_triggers_one_successful_repair(monkeypatch) -> None:
    claim = (
        "After a downturn that eliminated 2 million jobs, "
        "the economy restored 1 million jobs."
    )
    attempts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(json.loads(request.content))
        if len(attempts) == 1:
            draft = {
                "composition": "SINGLE",
                "obligations": [obligation(claim, claim, "NUMERIC_CONSTRAINT")],
            }
        else:
            draft = {
                "composition": "AND",
                "obligations": [
                    obligation(
                        "The downturn eliminated 2 million jobs.",
                        "downturn that eliminated 2 million jobs",
                        "NUMERIC_CONSTRAINT",
                    ),
                    obligation(
                        "The economy restored 1 million jobs after the downturn.",
                        "the economy restored 1 million jobs",
                        "NUMERIC_CONSTRAINT",
                    ),
                ],
            }
        return httpx.Response(
            200,
            json=envelope(draft),
        )

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(claim_decomposition.settings, ollama_url="http://ollama.test:11434"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await decompose_claim(claim, client=client)

    assert len(attempts) == 2
    assert "MULTIPLE_NUMERIC_ASSERTIONS" in attempts[1]["messages"][1]["content"]
    assert attempts[1]["format"]["$defs"]["ClaimComposition"]["enum"] == ["AND"]
    assert attempts[1]["format"]["properties"]["obligations"]["minItems"] == 2
    assert result.composition == "AND"
    assert [warning.code for warning in result.warnings] == [
        "DECOMPOSITION_REPAIRED"
    ]


@pytest.mark.asyncio
async def test_general_reference_warning_is_advisory(monkeypatch) -> None:
    claim = "The policy cut taxes. These changes raised growth."
    attempts: list[dict] = []
    first_draft = {
        "composition": "AND",
        "obligations": [
            obligation("The policy cut taxes.", "The policy cut taxes"),
            obligation("These changes raised growth.", "These changes raised growth"),
        ],
    }
    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(first_draft))

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(claim_decomposition.settings, ollama_url="http://ollama.test:11434"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await decompose_claim(claim, client=client)

    assert len(attempts) == 1
    assert [warning.code for warning in result.warnings] == [
        "NON_STANDALONE_REFERENCE"
    ]


@pytest.mark.asyncio
async def test_named_person_reference_is_resolved_without_an_extra_call(monkeypatch) -> None:
    claim = "The prize went to Albert Einstein and was awarded for his theory."
    attempts: list[dict] = []
    first_draft = {
        "composition": "AND",
        "obligations": [
            obligation(
                "The prize went to Albert Einstein.",
                "The prize went to Albert Einstein",
            ),
            obligation(
                "The prize was awarded for his theory.",
                "was awarded for his theory",
                "CAUSAL_RELATION",
            ),
        ],
    }
    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(first_draft))

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(claim_decomposition.settings, ollama_url="http://ollama.test:11434"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await decompose_claim(claim, client=client)

    assert len(attempts) == 1
    assert result.atoms[1].text == (
        "The prize was awarded for Albert Einstein's theory."
    )
    assert result.warnings == []


@pytest.mark.asyncio
async def test_reused_source_text_alone_does_not_add_a_call(monkeypatch) -> None:
    claim = "Drug activity, border crossings, and smuggling decreased."
    attempts: list[dict] = []
    draft = {
        "composition": "AND",
        "obligations": [
            obligation("Drug activity decreased.", claim),
            obligation("Border crossings decreased.", claim),
            obligation("Smuggling decreased.", claim),
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(draft))

    monkeypatch.setattr(
        claim_decomposition,
        "settings",
        replace(claim_decomposition.settings, ollama_url="http://ollama.test:11434"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await decompose_claim(claim, client=client)

    assert len(attempts) == 1
    assert [warning.code for warning in result.warnings] == ["REUSED_SOURCE_TEXT"]
