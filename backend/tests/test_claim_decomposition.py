from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from verigraph_backend import claim_decomposition
from verigraph_backend.claim_decomposition import (
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
        {"composition": "SINGLE", "obligations": [obligation("One.", "One."), obligation("Two.", "Two.")]},
        {"composition": "AND", "obligations": [obligation("One.", "One.")]},
        {"composition": "SINGLE", "obligations": [obligation("One.", "Missing.")]},
        {"composition": "SINGLE", "obligations": [obligation("One.", "One.", "INVALID")]},
        {"composition": "SINGLE", "obligations": [obligation("One.", "One."), obligation("One.", "One.")]},
    ],
)
def test_invalid_drafts_fail_hard_validation(draft: dict) -> None:
    with pytest.raises(DecompositionOutputError):
        parse_decomposition("One.", envelope(draft), "test-model")


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
