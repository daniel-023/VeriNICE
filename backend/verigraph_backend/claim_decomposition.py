from __future__ import annotations

import json
import re
from typing import Any, List, Literal, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .schemas import DecomposedAtom, DecompositionResponse
from .settings import settings
from .text_offsets import utf16_offset


WICE_DECOMPOSITION_INSTRUCTIONS = """Segment one claim into its essential,
independently verifiable facts. Return JSON matching the supplied schema.

Split coordinated predicates when they make separately verifiable assertions
(for example, “X acquired Y and moved to Z” becomes two atoms). Do not return a
multi-fact claim unchanged as one atom. Keep a single atom only when splitting
would destroy the meaning of one indivisible assertion.

Write each `text` as a clear standalone fact, as in WiCE-style claim
decomposition. You may restore an omitted subject or connective only when it is
unambiguously licensed by the claim; do not invent facts or strengthen scope.
Preserve negation, modality, attribution, time, quantities, and collective
scope. `source_text` must be an exact contiguous substring of the original
claim that grounds the rewritten fact. More than one fact may use the same
`source_text`. Copy `source_text` character-for-character: never reorder,
paraphrase, or normalize it. When a rewritten atom combines a shared modifier
with a later clause, use the entire original claim as `source_text`. Before
returning, verify mechanically that every `source_text` occurs verbatim in the
claim. Do not verify the claim.

Example claim: In March 2018, the company partnered with Amazon Web Services
(AWS) to offer AI-enabled conversational solutions to customers in India.
Example atoms:
- The company partnered with Amazon Web Services in March 2018.
- The partnership offered AI-enabled conversational solutions to customers in India.
For both atoms, `source_text` is the complete example claim exactly as written.

Example claim: A previous six-time winner of the Nations' Cup, Sebastian Vettel
became Champion of Champions for the first time, defeating Tom Kristensen 2–0.
Example atoms:
- Sebastian Vettel was a previous six-time winner of the Nations' Cup.
- Sebastian Vettel became Champion of Champions for the first time.
- Sebastian Vettel defeated Tom Kristensen 2–0.
"""


ATOM_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["atoms"],
    "properties": {
        "atoms": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "source_text", "essential"],
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "source_text": {"type": "string", "minLength": 1},
                    "essential": {"type": "boolean", "const": True},
                },
            },
        }
    },
}


class DecompositionError(RuntimeError):
    pass


class DecompositionConfigurationError(DecompositionError):
    pass


class DecompositionProviderError(DecompositionError):
    pass


class DecompositionOutputError(DecompositionError):
    pass


class _LLMAtom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    essential: Literal[True]


class _LLMDecomposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    atoms: List[_LLMAtom] = Field(min_length=1, max_length=12)


_GROUNDING_QUOTES = frozenset('"\'“”‘’')
_GROUNDING_WORDS = re.compile(r"[A-Za-z0-9]+")


def _soft_ground_source_text(claim: str, source_text: str) -> tuple[int, int] | None:
    """Match quote/whitespace-only transcription differences without inventing text.

    Some local models reproduce a quotation while normalising curly quotes or
    adding a missing closing quote.  The returned range always slices the
    original claim, and every non-quote, non-whitespace character must still
    match exactly.
    """

    def compact(value: str) -> tuple[str, list[int]]:
        characters: list[str] = []
        offsets: list[int] = []
        pending_space = False
        for offset, character in enumerate(value):
            if character in _GROUNDING_QUOTES:
                continue
            if character.isspace():
                pending_space = bool(characters)
                continue
            if pending_space:
                characters.append(" ")
                offsets.append(offset)
                pending_space = False
            characters.append(character)
            offsets.append(offset)
        return "".join(characters), offsets

    compact_claim, claim_offsets = compact(claim)
    compact_source, _ = compact(source_text)
    if not compact_source:
        return None
    normalized_start = compact_claim.find(compact_source)
    if normalized_start < 0:
        return None
    normalized_end = normalized_start + len(compact_source)
    return (
        claim_offsets[normalized_start],
        claim_offsets[normalized_end - 1] + 1,
    )


def _ground_source_text(claim: str, source_text: str) -> tuple[int, str] | None:
    start = claim.find(source_text)
    if start >= 0:
        return start, source_text
    soft_range = _soft_ground_source_text(claim, source_text)
    if soft_range is None:
        return None
    start, end = soft_range
    return start, claim[start:end]


def _can_use_full_claim_grounding(claim: str, atom_text: str, source_text: str) -> bool:
    """Allow a full-claim span only for a visibly claim-derived model result."""

    claim_words = {word.lower() for word in _GROUNDING_WORDS.findall(claim) if len(word) > 2}
    atom_words = {word.lower() for word in _GROUNDING_WORDS.findall(atom_text) if len(word) > 2}
    source_words = {word.lower() for word in _GROUNDING_WORDS.findall(source_text) if len(word) > 2}
    return len(claim_words & atom_words) >= 2 and len(claim_words & source_words) >= 2


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

    text_parts: List[str] = []
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
    try:
        parsed = _LLMDecomposition.model_validate_json(_response_text(payload))
    except (ValueError, ValidationError) as error:
        raise DecompositionOutputError(
            "The model returned malformed decomposition data. Please retry."
        ) from error

    atoms: List[DecomposedAtom] = []
    for index, item in enumerate(parsed.atoms, start=1):
        atom_text = item.text.strip()
        if not atom_text or not item.source_text.strip():
            raise DecompositionOutputError(
                "The model returned an empty atom. Please retry."
            )
        grounded = _ground_source_text(claim, item.source_text)
        if grounded is None:
            if not _can_use_full_claim_grounding(claim, atom_text, item.source_text):
                raise DecompositionOutputError(
                    "A returned atom was not grounded in the original claim. Please retry."
                )
            grounded = (0, claim)
        start, grounded_source_text = grounded
        atoms.append(
            DecomposedAtom(
                id=f"atom-{index}",
                text=atom_text,
                source_text=grounded_source_text,
                start=utf16_offset(claim, start),
                end=utf16_offset(claim, start + len(grounded_source_text)),
            )
        )
    return DecompositionResponse(atoms=atoms, model=model)


# The first attempt is fully deterministic (temperature 0, seed 0) so a
# successful decomposition is reproducible. Ollama returns byte-identical
# output for identical input+options, so a caller-level retry against that
# same request can never recover from an output-shape failure (e.g. an
# ungrounded atom) - only varying the sampling on retry gives it a chance.
_MAX_ATTEMPTS = 3


def _decomposition_options(attempt: int) -> dict[str, Any]:
    if attempt == 0:
        return {"temperature": 0, "seed": 0, "num_ctx": settings.ollama_context_size}
    return {
        "temperature": 0.4,
        "seed": attempt,
        "num_ctx": settings.ollama_context_size,
    }


def _decomposition_request_payload(claim: str, attempt: int) -> dict[str, Any]:
    return {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": WICE_DECOMPOSITION_INSTRUCTIONS},
            {
                "role": "user",
                "content": (
                    f"Claim:\n{claim}\n\n"
                    "Copy every source_text verbatim from the claim above. If in doubt, "
                    "use the complete claim exactly as written.\n\nRequired JSON schema:\n"
                    f"{json.dumps(ATOM_OUTPUT_SCHEMA, ensure_ascii=False)}"
                ),
            },
        ],
        "format": ATOM_OUTPUT_SCHEMA,
        "options": _decomposition_options(attempt),
        "keep_alive": settings.ollama_keep_alive,
    }


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
    active_client = client or httpx.AsyncClient(
        timeout=settings.request_timeout_seconds
    )
    try:
        last_error: DecompositionOutputError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            request_payload = _decomposition_request_payload(claim, attempt)
            try:
                response = await active_client.post(
                    f"{settings.ollama_url.rstrip('/')}/api/chat",
                    headers={"Content-Type": "application/json"},
                    content=json.dumps(request_payload),
                )
                response.raise_for_status()
                return parse_decomposition(
                    claim,
                    response.json(),
                    settings.ollama_model,
                )
            except DecompositionOutputError as error:
                last_error = error
                continue
            except httpx.TimeoutException as error:
                raise DecompositionProviderError(
                    "The Ollama decomposition request timed out. Check that Ollama is running and retry."
                ) from error
            except httpx.HTTPStatusError as error:
                raise DecompositionProviderError(
                    "Ollama rejected the decomposition request. Check that the configured model is installed."
                ) from error
            except (httpx.RequestError, ValueError) as error:
                raise DecompositionProviderError(
                    "Ollama could not be reached. Start Ollama and retry."
                ) from error
        assert last_error is not None
        raise last_error
    finally:
        if owns_client:
            await active_client.aclose()
