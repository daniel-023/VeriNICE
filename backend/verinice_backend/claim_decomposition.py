"""Claim decomposition orchestration and stable public API."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Optional

import httpx
from pydantic import ValidationError

from .claim_decomposition_errors import (
    DecompositionConfigurationError,
    DecompositionError,
    DecompositionOutputError,
    DecompositionProviderError,
)
from .claim_decomposition_prompt import DECOMPOSITION_INSTRUCTIONS
from .claim_decomposition_validation import (
    numeric_assertion_clauses,
    semantic_repair_errors,
    validate_and_normalize,
)
from .schemas import (
    ClaimComposition,
    ClaimDecompositionDraft,
    DecomposedAtom,
    DecompositionResponse,
    DecompositionWarning,
)
from .settings import settings
from .text_offsets import utf16_offset


ATOM_OUTPUT_SCHEMA = ClaimDecompositionDraft.model_json_schema(by_alias=True)


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
            if content.get("type") == "output_text" and isinstance(
                content.get("text"), str
            ):
                text_parts.append(content["text"])
    if not text_parts:
        raise DecompositionOutputError(
            "The model returned no structured decomposition. Please retry."
        )
    return "".join(text_parts)


def parse_decomposition(claim: str, payload: Any, model: str) -> DecompositionResponse:
    """Validate one model response and normalize its server-owned fields."""
    try:
        draft = ClaimDecompositionDraft.model_validate_json(_response_text(payload))
    except (ValueError, ValidationError) as error:
        raise DecompositionOutputError(
            f"The model returned malformed decomposition data: {error}"
        ) from error

    # Cardinality safely determines SINGLE versus conjunction. OR stays
    # model-explicit because changing it would alter the claim's meaning.
    if len(draft.obligations) > 1 and draft.composition is ClaimComposition.single:
        draft = draft.model_copy(update={"composition": ClaimComposition.and_})
    elif len(draft.obligations) == 1 and draft.composition is ClaimComposition.and_:
        draft = draft.model_copy(update={"composition": ClaimComposition.single})
    return validate_and_normalize(claim, draft, model)


def _mark_repaired(result: DecompositionResponse) -> DecompositionResponse:
    return result.model_copy(
        update={
            "warnings": [
                *result.warnings,
                DecompositionWarning(
                    code="DECOMPOSITION_REPAIRED",
                    message=(
                        "The first model response was repaired after decomposition "
                        "validation."
                    ),
                ),
            ]
        }
    )


def _decomposition_options() -> dict[str, Any]:
    return {"temperature": 0, "seed": 0, "num_ctx": settings.ollama_context_size}


def _decomposition_request_payload(
    claim: str,
    *,
    repair_errors: str | None = None,
    invalid_json: str | None = None,
) -> dict[str, Any]:
    output_schema = deepcopy(ATOM_OUTPUT_SCHEMA)
    requires_split = repair_errors is not None and any(
        code in repair_errors
        for code in ("MULTIPLE_NUMERIC_ASSERTIONS", "UNDER_DECOMPOSED")
    )
    if requires_split:
        output_schema["$defs"]["ClaimComposition"]["enum"] = ["AND"]
        output_schema["properties"]["obligations"]["minItems"] = 2

    request = (
        f"Claim:\n{claim}\n\nRequired JSON schema:\n"
        f"{json.dumps(output_schema, ensure_ascii=False)}"
    )
    if repair_errors is not None:
        request += _repair_instruction(
            claim,
            repair_errors=repair_errors,
            invalid_json=invalid_json,
        )
    return {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": DECOMPOSITION_INSTRUCTIONS},
            {"role": "user", "content": request},
        ],
        "think": False,
        "format": output_schema,
        "options": _decomposition_options(),
        "keep_alive": settings.ollama_keep_alive,
    }


def _repair_instruction(
    claim: str, *, repair_errors: str, invalid_json: str | None
) -> str:
    if invalid_json is None:
        instruction = (
            "\n\nA previous answer failed semantic validation. Generate corrected "
            f"JSON from the claim.\nValidation errors:\n{repair_errors}"
        )
    else:
        instruction = (
            "\n\nYour previous response failed structural validation. Repair only "
            f"the JSON.\nValidation errors:\n{repair_errors}"
            f"\nPrevious response:\n{invalid_json}"
        )
    if "MULTIPLE_NUMERIC_ASSERTIONS" in repair_errors:
        instruction += (
            "\nMandatory repair: use AND with at least two obligations. Put each "
            "independently asserted numeric predicate in its own standalone "
            "obligation. Do not split a comparison, range, or one quantity with "
            "its date. Remove discourse framing that is not part of the numeric "
            "proposition. The validator has already established that the following "
            "clauses are independent assertions; do not merge them:\n- "
            + "\n- ".join(numeric_assertion_clauses(claim))
            + "\nA SINGLE answer will fail again."
        )
    if "UNDER_DECOMPOSED" in repair_errors:
        instruction += (
            "\nMandatory repair: represent every asserted sentence separately; "
            "do not return one whole-claim obligation."
        )
    return instruction


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
                    claim,
                    repair_errors=repair_errors,
                    invalid_json=invalid_json,
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
            "Ollama rejected the decomposition request. Check that the configured "
            "model is installed."
        ) from error
    except (httpx.RequestError, ValueError) as error:
        raise DecompositionProviderError(
            "Ollama could not be reached. Start Ollama and retry."
        ) from error


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
                message=(
                    "Structured decomposition failed; the original claim was "
                    "retained as one obligation."
                ),
            )
        ],
        model=model,
    )


async def decompose_claim(
    claim: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> DecompositionResponse:
    """Decompose a claim with no more than two model calls."""
    if not settings.ollama_url.strip() or not settings.ollama_model.strip():
        raise DecompositionConfigurationError(
            "Live decomposition is not configured. Set VERINICE_OLLAMA_URL and "
            "VERINICE_OLLAMA_MODEL."
        )

    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=settings.request_timeout_seconds
    )
    try:
        first_payload = await _generate(active_client, claim)
        try:
            first_result = parse_decomposition(
                claim, first_payload, settings.ollama_model
            )
        except DecompositionOutputError as first_error:
            return await _repair_invalid_output(
                active_client, claim, first_payload, first_error
            )

        errors = semantic_repair_errors(first_result)
        if errors is None:
            return first_result
        return await _repair_semantic_output(
            active_client, claim, first_result, errors
        )
    finally:
        if owns_client:
            await active_client.aclose()


async def _repair_invalid_output(
    client: httpx.AsyncClient,
    claim: str,
    first_payload: Any,
    error: DecompositionOutputError,
) -> DecompositionResponse:
    try:
        previous_json = _response_text(first_payload)
    except DecompositionError:
        previous_json = None
    repaired_payload = await _generate(
        client,
        claim,
        repair_errors=str(error),
        invalid_json=previous_json,
    )
    try:
        repaired = parse_decomposition(claim, repaired_payload, settings.ollama_model)
    except DecompositionOutputError:
        return _fallback(claim, settings.ollama_model)
    return _mark_repaired(repaired)


async def _repair_semantic_output(
    client: httpx.AsyncClient,
    claim: str,
    original: DecompositionResponse,
    errors: str,
) -> DecompositionResponse:
    try:
        repaired_payload = await _generate(client, claim, repair_errors=errors)
        repaired = parse_decomposition(claim, repaired_payload, settings.ollama_model)
    except DecompositionError:
        return original
    if semantic_repair_errors(repaired) is not None:
        return original
    return _mark_repaired(repaired)
