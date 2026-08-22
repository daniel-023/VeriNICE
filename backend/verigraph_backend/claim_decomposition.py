from __future__ import annotations

import json
from typing import Any, Optional

import httpx
from pydantic import ValidationError

from .schemas import (
    ClaimComposition,
    ClaimDecompositionDraft,
    DecomposedAtom,
    DecompositionResponse,
    DecompositionWarning,
)
from .settings import settings
from .text_offsets import utf16_offset


DECOMPOSITION_INSTRUCTIONS = """Decompose one claim into the smallest set of
standalone verification obligations needed to verify the complete claim.

Each obligation must be one independently verifiable proposition. Preserve the
claim's polarity, attribution, modality, quantities, dates, locations, and
causal relations. Do not add facts. sourceText must be copied exactly from one
contiguous span of the claim. Use the most specific role. Never create support
or attack relations, entities, isolated dates, numbers, or tokens.

Use SINGLE for one obligation, AND when every obligation must hold, and OR when
any obligation is sufficient. This schema supports only flat composition.

Examples:
Claim: The archive opened in 2021.
JSON: {"composition":"SINGLE","obligations":[{"text":"The archive opened in 2021.","sourceText":"The archive opened in 2021","role":"CORE"}]}
Claim: The minister said unemployment had fallen.
JSON: {"composition":"SINGLE","obligations":[{"text":"The minister said that unemployment had fallen.","sourceText":"The minister said unemployment had fallen","role":"ATTRIBUTION"}]}
Claim: The city cut emissions by 20% in 2023.
JSON: {"composition":"AND","obligations":[{"text":"The city cut emissions.","sourceText":"The city cut emissions","role":"CORE"},{"text":"The city cut emissions by 20%.","sourceText":"by 20%","role":"NUMERIC_CONSTRAINT"},{"text":"The city cut emissions in 2023.","sourceText":"in 2023","role":"TEMPORAL_CONSTRAINT"}]}
Claim: The bridge is in Paris or Lyon.
JSON: {"composition":"OR","obligations":[{"text":"The bridge is in Paris.","sourceText":"in Paris","role":"LOCATION_CONSTRAINT"},{"text":"The bridge is in Lyon.","sourceText":"Lyon","role":"LOCATION_CONSTRAINT"}]}

Return only JSON conforming to the supplied schema."""


ATOM_OUTPUT_SCHEMA = ClaimDecompositionDraft.model_json_schema(by_alias=True)


class DecompositionError(RuntimeError):
    pass


class DecompositionConfigurationError(DecompositionError):
    pass


class DecompositionProviderError(DecompositionError):
    pass


class DecompositionOutputError(DecompositionError):
    pass


def _response_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise DecompositionOutputError("The model returned an invalid response envelope.")
    message = payload.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        if not payload.get("done", True):
            raise DecompositionProviderError(
                "Ollama stopped before completing the decomposition. Please retry."
            )
        return message["content"]
    if payload.get("status") == "incomplete":
        raise DecompositionProviderError(
            "The model stopped before completing the decomposition. Please retry."
        )

    text_parts: list[str] = []
    for output in payload.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "refusal":
                raise DecompositionProviderError(
                    "The model declined this claim. Revise the claim and try again."
                )
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                text_parts.append(content["text"])
    if not text_parts:
        raise DecompositionOutputError(
            "The model returned no structured decomposition. Please retry."
        )
    return "".join(text_parts)


def _validate_and_normalize(
    claim: str, draft: ClaimDecompositionDraft, model: str
) -> DecompositionResponse:
    obligations = draft.obligations
    if draft.composition is ClaimComposition.single and len(obligations) != 1:
        raise DecompositionOutputError("SINGLE decompositions must contain exactly one obligation.")
    if draft.composition in {ClaimComposition.and_, ClaimComposition.or_} and len(obligations) < 2:
        raise DecompositionOutputError("AND and OR decompositions must contain at least two obligations.")

    texts = [item.text.strip() for item in obligations]
    if len(texts) != len(set(texts)):
        raise DecompositionOutputError("Decomposition obligations must not be exact duplicates.")

    atoms: list[DecomposedAtom] = []
    source_texts: list[str] = []
    for index, obligation in enumerate(obligations, start=1):
        text = obligation.text.strip()
        source_text = obligation.source_text
        if not text or not source_text.strip():
            raise DecompositionOutputError("Decomposition obligations and sourceText values cannot be blank.")
        start = claim.find(source_text)
        if start < 0:
            raise DecompositionOutputError(
                "Every sourceText value must be an exact contiguous substring of the claim."
            )
        source_texts.append(source_text)
        atoms.append(
            DecomposedAtom(
                id=f"atom-{index}",
                text=text,
                source_text=source_text,
                start=utf16_offset(claim, start),
                end=utf16_offset(claim, start + len(source_text)),
                role=obligation.role,
            )
        )

    warnings: list[DecompositionWarning] = []
    if len(source_texts) != len(set(source_texts)):
        warnings.append(
            DecompositionWarning(
                code="REUSED_SOURCE_TEXT",
                message="One sourceText span grounds more than one obligation.",
            )
        )
    if any(len(source.strip()) < 4 for source in source_texts):
        warnings.append(
            DecompositionWarning(
                code="AMBIGUOUS_SOURCE_TEXT",
                message="A very short sourceText span may be ambiguous in the original claim.",
            )
        )
    return DecompositionResponse(
        composition=draft.composition,
        atoms=atoms,
        warnings=warnings,
        model=model,
    )


def parse_decomposition(claim: str, payload: Any, model: str) -> DecompositionResponse:
    """Validate one model response and normalize its server-owned fields."""

    try:
        draft = ClaimDecompositionDraft.model_validate_json(_response_text(payload))
    except (ValueError, ValidationError) as error:
        raise DecompositionOutputError(
            f"The model returned malformed decomposition data: {error}"
        ) from error
    return _validate_and_normalize(claim, draft, model)


def _decomposition_options() -> dict[str, Any]:
    return {"temperature": 0, "seed": 0, "num_ctx": settings.ollama_context_size}


def _decomposition_request_payload(
    claim: str, *, repair_errors: str | None = None, invalid_json: str | None = None
) -> dict[str, Any]:
    request = (
        f"Claim:\n{claim}\n\nRequired JSON schema:\n"
        f"{json.dumps(ATOM_OUTPUT_SCHEMA, ensure_ascii=False)}"
    )
    if repair_errors is not None:
        request += (
            "\n\nYour previous response failed validation. Repair only the JSON."
            f"\nValidation errors:\n{repair_errors}"
            f"\nPrevious response:\n{invalid_json or '(unavailable)'}"
        )
    return {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": DECOMPOSITION_INSTRUCTIONS},
            {"role": "user", "content": request},
        ],
        "format": ATOM_OUTPUT_SCHEMA,
        "options": _decomposition_options(),
        "keep_alive": settings.ollama_keep_alive,
    }


async def _generate(
    client: httpx.AsyncClient,
    claim: str,
    *,
    repair_errors: str | None = None,
    invalid_json: str | None = None,
) -> Any:
    try:
        response = await client.post(
            f"{settings.ollama_url.rstrip('/')}/api/chat",
            headers={"Content-Type": "application/json"},
            content=json.dumps(
                _decomposition_request_payload(
                    claim, repair_errors=repair_errors, invalid_json=invalid_json
                )
            ),
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as error:
        raise DecompositionProviderError(
            "The Ollama decomposition request timed out. Check that Ollama is running and retry."
        ) from error
    except httpx.HTTPStatusError as error:
        raise DecompositionProviderError(
            "Ollama rejected the decomposition request. Check that the configured model is installed."
        ) from error
    except (httpx.RequestError, ValueError) as error:
        raise DecompositionProviderError("Ollama could not be reached. Start Ollama and retry.") from error


def _fallback(claim: str, model: str) -> DecompositionResponse:
    return DecompositionResponse(
        composition=ClaimComposition.single,
        atoms=[
            DecomposedAtom(
                id="atom-1",
                text=claim,
                source_text=claim,
                start=0,
                end=utf16_offset(claim, len(claim)),
                role="CORE",
            )
        ],
        warnings=[
            DecompositionWarning(
                code="DECOMPOSITION_FALLBACK",
                message="Structured decomposition failed; the original claim was retained as one obligation.",
            )
        ],
        model=model,
    )


async def decompose_claim(
    claim: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> DecompositionResponse:
    if not settings.ollama_url.strip() or not settings.ollama_model.strip():
        raise DecompositionConfigurationError(
            "Live decomposition is not configured. Set VERIGRAPH_OLLAMA_URL and VERIGRAPH_OLLAMA_MODEL."
        )

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    try:
        first_payload = await _generate(active_client, claim)
        try:
            return parse_decomposition(claim, first_payload, settings.ollama_model)
        except DecompositionOutputError as first_error:
            try:
                previous_json = _response_text(first_payload)
            except DecompositionError:
                previous_json = None
            repaired_payload = await _generate(
                active_client,
                claim,
                repair_errors=str(first_error),
                invalid_json=previous_json,
            )
            try:
                return parse_decomposition(claim, repaired_payload, settings.ollama_model)
            except DecompositionOutputError:
                return _fallback(claim, settings.ollama_model)
    finally:
        if owns_client:
            await active_client.aclose()
