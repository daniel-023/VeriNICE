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


def envelope(atoms):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps({"atoms": atoms}),
                    }
                ],
            }
        ],
    }


def ollama_envelope(atoms):
    return {
        "model": "test-model",
        "done": True,
        "message": {
            "role": "assistant",
            "content": json.dumps({"atoms": atoms}),
        },
    }


def test_rewritten_atoms_share_and_preserve_exact_source_span() -> None:
    claim = "Mara joined Orion in 2022 and became its chief technology officer."
    result = parse_decomposition(
        claim,
        envelope(
            [
                {
                    "text": "Mara joined Orion in 2022.",
                    "source_text": claim,
                    "essential": True,
                },
                {
                    "text": "Mara became Orion's chief technology officer.",
                    "source_text": claim,
                    "essential": True,
                },
            ]
        ),
        "test-model",
    )
    assert [atom.id for atom in result.atoms] == ["atom-1", "atom-2"]
    assert all(atom.start == 0 and atom.end == len(claim) for atom in result.atoms)
    assert all(claim[atom.start : atom.end] == atom.source_text for atom in result.atoms)


def test_repeated_source_text_uses_a_valid_exact_occurrence() -> None:
    claim = "The archive opened. The archive opened."
    result = parse_decomposition(
        claim,
        envelope(
            [
                {
                    "text": "The archive opened.",
                    "source_text": "The archive opened.",
                    "essential": True,
                }
            ]
        ),
        "test-model",
    )
    assert result.atoms[0].start == 0
    assert claim[result.atoms[0].start : result.atoms[0].end] == result.atoms[0].source_text


def test_claim_offsets_use_browser_utf16_code_units() -> None:
    claim = "🚀 The archive opened."
    result = parse_decomposition(
        claim,
        envelope(
            [
                {
                    "text": "The archive opened.",
                    "source_text": "The archive opened.",
                    "essential": True,
                }
            ]
        ),
        "test-model",
    )
    assert result.atoms[0].start == 3
    assert result.atoms[0].end == 22


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "completed", "output": []},
        envelope([{"text": "Fact", "source_text": "invented", "essential": True}]),
        {
            "status": "completed",
            "output": [{"content": [{"type": "refusal", "refusal": "no"}]}],
        },
    ],
)
def test_invalid_or_ungrounded_outputs_fail_without_fallback(payload) -> None:
    with pytest.raises((DecompositionOutputError, DecompositionProviderError)):
        parse_decomposition("Original claim.", payload, "test-model")


@pytest.mark.asyncio
async def test_live_request_uses_ollama_schema_and_sends_only_claim(monkeypatch) -> None:
    claim = "The archive opened in 2021."
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json=ollama_envelope(
                [
                    {
                        "text": claim,
                        "source_text": claim,
                        "essential": True,
                    }
                ]
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
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["stream"] is False
    assert captured["body"]["format"] == ATOM_OUTPUT_SCHEMA
    assert captured["body"]["options"]["temperature"] == 0
    assert claim in json.dumps(captured["body"])
    assert "document" not in json.dumps(captured["body"]).lower()


@pytest.mark.asyncio
async def test_timeout_is_reported_as_provider_error(monkeypatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

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
        with pytest.raises(DecompositionProviderError, match="timed out"):
            await decompose_claim("A claim.", client=client)
