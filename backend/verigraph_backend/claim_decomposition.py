from __future__ import annotations

import json
import re
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
from .segmentation import segment_document
from .settings import settings
from .text_offsets import utf16_offset


DECOMPOSITION_INSTRUCTIONS = """Decompose one claim into standalone verification
obligations. Cover every independently verifiable proposition the claim asserts,
and add nothing beyond them. Completeness comes first; among equally complete
decompositions prefer the shorter one.

Each obligation must be one independently verifiable proposition. Preserve the
claim's polarity, attribution, modality, quantities, dates, locations, and
causal relations. Do not add facts. sourceText must be copied exactly from one
contiguous span of the claim. Use the most specific role. Never create support
or evidence relations, entities, isolated dates, numbers, or tokens.

Do not split modifiers or constraints away from the proposition they qualify.
A single event with a quantity, date, location, attribution, modality, or
comparison is still one obligation containing all of those commitments. The
role names the obligation's main verification challenge; it does not create an
extra obligation. Split only propositions whose truth values can vary
independently. Never include both a broad proposition and a narrower duplicate
that merely repeats it with one qualifier restored.

When several propositions share a subject, verb, or modal, quote only the part
that distinguishes each one. sourceText is a locator, not the proposition: the
text field carries the full reconstructed proposition, so a fragment is correct
whenever the shared words sit elsewhere in the claim.

Constraint obligations must remain self-contained and semantically complete.
For comparisons, preserve both compared values or periods and the direction of
comparison in the same obligation. Never emit a fragment such as "2020 is from
2019" or split a comparison so that no obligation states what is greater,
lower, earlier, or later. A comparison does not separately assert background
facts about either participant: do not add obligations such as "Finland is a
country" or "Sweden joined NATO" when the claim only asserts their ordering.
Do not split a coordinated adjectival range that describes one event, such as
"the sky turned orange to blood red"; its endpoints are not independent events.

A claim of several sentences asserts several things. Every sentence that asserts
a verifiable proposition contributes at least one obligation, and an obligation's
sourceText must not span more than one sentence unless one proposition genuinely
runs across them. Never return a single obligation whose sourceText is the whole
of a multi-sentence claim.

Use AND when every obligation must hold, OR when any one is sufficient, and
SINGLE only when the claim asserts exactly one thing. This schema supports only
flat composition.

Examples:
Claim: The archive opened in 2021.
JSON: {"composition":"SINGLE","obligations":[{"text":"The archive opened in 2021.","sourceText":"The archive opened in 2021","role":"CORE"}]}
Claim: The minister said unemployment had fallen.
JSON: {"composition":"SINGLE","obligations":[{"text":"The minister said that unemployment had fallen.","sourceText":"The minister said unemployment had fallen","role":"ATTRIBUTION"}]}
Claim: The city cut emissions by 20% in 2023.
JSON: {"composition":"SINGLE","obligations":[{"text":"The city cut emissions by 20% in 2023.","sourceText":"The city cut emissions by 20% in 2023","role":"NUMERIC_CONSTRAINT"}]}
Claim: ExampleCo's annual revenue for 2024 decreased from its revenue for 2023.
JSON: {"composition":"SINGLE","obligations":[{"text":"ExampleCo's annual revenue for 2024 was lower than its annual revenue for 2023.","sourceText":"annual revenue for 2024 decreased from its revenue for 2023","role":"TEMPORAL_CONSTRAINT"}]}
Claim: Sweden joined NATO before Finland.
JSON: {"composition":"SINGLE","obligations":[{"text":"Sweden joined NATO before Finland.","sourceText":"Sweden joined NATO before Finland","role":"TEMPORAL_CONSTRAINT"}]}
Claim: The sky turned orange to blood red across the region.
JSON: {"composition":"SINGLE","obligations":[{"text":"The sky turned orange to blood red across the region.","sourceText":"The sky turned orange to blood red across the region","role":"CORE"}]}
Claim: The mayor called the report a hoax. She later said the harbour project would finish in 2022. It opened in 2024.
JSON: {"composition":"AND","obligations":[{"text":"The mayor called the report a hoax.","sourceText":"The mayor called the report a hoax","role":"ATTRIBUTION"},{"text":"The mayor said the harbour project would finish in 2022.","sourceText":"She later said the harbour project would finish in 2022","role":"ATTRIBUTION"},{"text":"The harbour project opened in 2024.","sourceText":"It opened in 2024","role":"TEMPORAL_CONSTRAINT"}]}
Claim: If given power they would ban animal agriculture and eliminate petrol cars.
JSON: {"composition":"AND","obligations":[{"text":"If given power they would ban animal agriculture.","sourceText":"ban animal agriculture","role":"CONDITIONAL"},{"text":"If given power they would eliminate petrol cars.","sourceText":"eliminate petrol cars","role":"CONDITIONAL"}]}
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


#: A single obligation covering at least this share of a multi-sentence claim
#: has not separated anything, whatever its role says.
_WHOLE_CLAIM_COVERAGE = 0.9


def _is_under_decomposed(claim: str, source_texts: list[str]) -> bool:
    """Report a multi-sentence claim that collapsed into one whole-claim obligation.

    The model is free to decide a claim asserts one thing, but when a claim spans
    several sentences and the single obligation quotes nearly all of them, no
    decomposition happened. Surfacing that is better than letting the rest of the
    pipeline treat an undivided claim as an atomic obligation.
    """
    if len(source_texts) != 1:
        return False
    if len(segment_document(claim)) < 2:
        return False
    return len(source_texts[0].strip()) >= _WHOLE_CLAIM_COVERAGE * len(claim.strip())


#: Punctuation a model tends to add when it closes a quoted span at a clause
#: boundary the claim continues past.
_ADDED_EDGE_PUNCTUATION = " \t\n\r.,;:!?\"'’”"

#: Bounds on shedding a repeated leading subject or modal. Wide enough for
#: "they would" and for a coordinated list item, and the remainder must still
#: occur exactly once, so a shortened span cannot highlight the wrong place.
_MAX_DROPPED_LEADING_WORDS = 5
_MIN_LOCATOR_CHARACTERS = 4

_TERM = re.compile(r"[^\W_]+", re.UNICODE)
_COVERING_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
    "had", "has", "have", "in", "is", "it", "of", "on", "or", "that", "the",
    "their", "they", "this", "to", "was", "were", "will", "with",
}


def _semantic_terms(text: str) -> set[str]:
    """Return conservative content terms for safe duplicate removal.

    Span containment alone is insufficient: a broad obligation may include a
    third list item that the narrower obligations silently omitted. Removing it
    would turn a decomposition error into an apparently complete claim.
    """
    return {
        term
        for term in (token.casefold() for token in _TERM.findall(text))
        if term not in _COVERING_STOP_WORDS
    }


def _locate_source_text(claim: str, source_text: str) -> tuple[int, str]:
    """Find a model-supplied span in the claim, tolerating punctuation it added.

    The span that gets stored is always an exact substring of the unmodified
    claim; this only widens what the model is allowed to hand us. Models
    routinely close a mid-sentence span with a full stop the claim does not have
    there, and discarding an otherwise correct decomposition over one character
    is not worth it.
    """
    start = claim.find(source_text)
    if start >= 0:
        return start, source_text
    trimmed = source_text.strip().strip(_ADDED_EDGE_PUNCTUATION)
    if not trimmed:
        return -1, source_text
    start = claim.find(trimmed)
    if start >= 0:
        return start, trimmed
    # Coordinated propositions share a subject or modal the claim states once
    # ("they would ban X and eliminate Y"), and a model will often repeat it in
    # both spans. Shed leading words until what remains is verbatim, so long as
    # enough of the span survives to still locate the proposition.
    words = trimmed.split()
    for dropped in range(1, min(_MAX_DROPPED_LEADING_WORDS, len(words)) + 1):
        candidate = " ".join(words[dropped:]).strip(_ADDED_EDGE_PUNCTUATION)
        if len(candidate) < _MIN_LOCATOR_CHARACTERS:
            break
        # Requiring a single occurrence is what makes shortening safe: a span
        # that appears twice would highlight an arbitrary one of them.
        if claim.count(candidate) == 1:
            return claim.find(candidate), candidate
    return -1, source_text


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
        # A one-sentence SINGLE claim is already a self-contained proposition.
        # Preserve it verbatim instead of allowing a rewrite to shed a reason,
        # date, quantity, location, or other verification condition.
        if (
            draft.composition is ClaimComposition.single
            and len(obligations) == 1
            and len(segment_document(claim)) == 1
        ):
            text = claim.strip()
        source_text = obligation.source_text
        if not text or not source_text.strip():
            raise DecompositionOutputError("Decomposition obligations and sourceText values cannot be blank.")
        start, source_text = _locate_source_text(claim, source_text)
        if start < 0:
            raise DecompositionOutputError(
                "Every sourceText value must be an exact contiguous substring of the claim. "
                f"This one is not: {source_text!r}. Quote a span that appears verbatim in the "
                "claim, even if it is only a fragment."
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
    if _is_under_decomposed(claim, source_texts):
        warnings.append(
            DecompositionWarning(
                code="UNDER_DECOMPOSED",
                message=(
                    "A claim of several sentences produced one obligation covering "
                    "almost all of it, so its separate assertions were not separated."
                ),
            )
        )
    if len(atoms) >= 3:
        covering = next(
            (
                outer
                for outer in atoms
                if all(
                    other.id == outer.id
                    or (outer.start <= other.start and outer.end >= other.end)
                    for other in atoms
                )
            ),
            None,
        )
        components = [atom for atom in atoms if covering is not None and atom.id != covering.id]
        component_terms = set().union(*(_semantic_terms(atom.text) for atom in components))
        has_uncovered_content = bool(
            covering is not None and _semantic_terms(covering.text) - component_terms
        )
        if covering is not None and not has_uncovered_content:
            atoms = [atom for atom in atoms if atom.id != covering.id]
            atoms = [
                atom.model_copy(update={"id": f"atom-{index}"})
                for index, atom in enumerate(atoms, start=1)
            ]
            warnings.append(
                DecompositionWarning(
                    code="REDUNDANT_COVERING_OBLIGATION_REMOVED",
                    message=(
                        "A broad obligation duplicated every component obligation and "
                        "was removed before retrieval."
                    ),
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
    # Cardinality determines SINGLE versus a conjunction.  Small local models
    # occasionally return several well-grounded obligations while leaving the
    # composition field at SINGLE.  Correct that structural inconsistency
    # server-side; OR remains model-explicit because it changes claim meaning.
    if len(draft.obligations) > 1 and draft.composition is ClaimComposition.single:
        draft = draft.model_copy(update={"composition": ClaimComposition.and_})
    elif len(draft.obligations) == 1 and draft.composition is ClaimComposition.and_:
        draft = draft.model_copy(update={"composition": ClaimComposition.single})
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
        "think": False,
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
