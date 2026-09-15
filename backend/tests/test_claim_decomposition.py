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
    assert result.warnings == []


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
    assert "preserve both compared values or periods" in instructions
    assert (
        "ExampleCo's annual revenue for 2024 was lower than its annual revenue for 2023"
        in instructions
    )
    assert "Nigeria" not in instructions


def test_prompt_keeps_qualifiers_with_the_proposition_they_modify() -> None:
    instructions = claim_decomposition.DECOMPOSITION_INSTRUCTIONS
    normalized = " ".join(instructions.split())
    assert "Do not split modifiers or constraints away" in instructions
    assert "Split only propositions whose truth values can vary independently" in normalized
    city_example = instructions.split("Claim: The city cut emissions by 20% in 2023.", 1)[1]
    city_example = city_example.split("Claim: ExampleCo", 1)[0]
    assert '"composition":"SINGLE"' in city_example
    assert city_example.count('"text"') == 1
    assert "by 20% in 2023" in city_example
