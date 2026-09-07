from __future__ import annotations

import json
from typing import Any, Sequence

import httpx

from ..settings import settings
from .grounding import Candidate


INSTRUCTIONS = """Compile grounded fact-checking inputs into symbolic programs.
Use only candidate IDs and premise IDs supplied by the server. Do not calculate
results, decide truth, rewrite operands, or use outside knowledge. Select at
most three distinct programs per obligation. Omit a candidate when its operator
does not apply or the supplied premises cannot represent the claimed operands.
For a negative set-membership claim, select the matching LIST_CERTIFICATE; the
Python executor will inspect every item covered by its server-owned content
hash. Do not enumerate list items merely to establish absence.
For a positive membership claim, a counted complete-list certificate can test
absence as well as presence. For an extremum counterexample, select the claimed
subject's aligned value and at least one comparable source row. For a before or
after claim whose dates are supplied by the sources, select one dated premise
for each named event. Include an immediately adjacent OPERAND when it completes
an anchor's explicit address, date, quantity, or attribute.
For a location attribute, when a source anchor names the same subject and its
adjacent grounded address names a country different from the atom's country,
map the ATTRIBUTE_COMPARE candidate with both premises. This maps operands
only; Python, not you, decides whether the locations are equal.
Return JSON only."""


class CompilerConfigurationError(RuntimeError):
    pass


class CompilerProviderError(RuntimeError):
    pass


class CompilerOutputError(RuntimeError):
    pass


def _validated_programs(
    programs: Any,
    candidates: Sequence[Candidate],
) -> list[tuple[str, list[str]]]:
    """Keep only grounded programs and merge repeated candidate selections.

    Qwen compilation is untrusted parsing. Invalid selections are omitted so
    the service can expose the corresponding typed candidate as unresolved;
    they never abort unrelated checks or become a model-derived verdict.
    """
    if not isinstance(programs, list):
        raise CompilerOutputError("Ollama returned malformed symbolic programs.")
    known = {candidate.id: candidate for candidate in candidates}
    selected_by_candidate: dict[str, list[str]] = {}
    candidate_order: list[str] = []
    counts: dict[str, int] = {}
    for program in programs:
        if not isinstance(program, dict):
            continue
        candidate_id = str(program.get("candidateId", ""))
        candidate = known.get(candidate_id)
        if candidate is None:
            continue
        selected = list(
            dict.fromkeys(str(item) for item in program.get("premiseIds", []))
        )
        if any(item not in candidate.premise_ids for item in selected):
            continue
        if candidate_id in selected_by_candidate:
            selected_by_candidate[candidate_id] = list(
                dict.fromkeys([*selected_by_candidate[candidate_id], *selected])
            )
            continue
        count = counts.get(candidate.atom_id, 0)
        if count >= 3:
            continue
        counts[candidate.atom_id] = count + 1
        candidate_order.append(candidate_id)
        selected_by_candidate[candidate_id] = selected
    return [
        (candidate_id, selected_by_candidate[candidate_id])
        for candidate_id in candidate_order
    ]


def _schema(candidate_ids: list[str], premise_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "programs": {
                "type": "array",
                "maxItems": 36,
                "items": {
                    "type": "object",
                    "properties": {
                        "candidateId": {"type": "string", "enum": candidate_ids},
                        "premiseIds": {"type": "array", "items": {"type": "string", "enum": premise_ids}, "maxItems": 8},
                    },
                    "required": ["candidateId", "premiseIds"],
                },
            }
        },
        "required": ["programs"],
    }


async def compile_programs(candidates: Sequence[Candidate]) -> list[tuple[str, list[str]]]:
    if not candidates:
        return []
    if not settings.ollama_url.strip() or not settings.ollama_model.strip():
        raise CompilerConfigurationError("Symbolic program compilation requires the configured local Ollama model.")
    candidate_ids = [candidate.id for candidate in candidates]
    premise_ids = list(dict.fromkeys(premise for candidate in candidates for premise in candidate.premise_ids))
    prompt = "\n\n".join(
        f"{candidate.id} | {candidate.operator} | ATOM: {candidate.summary}\n"
        + "\n".join(f"  {premise_id} = {text}" for premise_id, text in candidate.premise_texts)
        for candidate in candidates
    )
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": prompt}],
        "think": False,
        "format": _schema(candidate_ids, premise_ids),
        "options": {"temperature": 0, "seed": 0, "num_ctx": settings.evidence_audit_context_size, "num_predict": 1200},
        "keep_alive": settings.ollama_keep_alive,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
            envelope = response.json()
    except httpx.TimeoutException as error:
        raise CompilerProviderError("Ollama timed out while compiling symbolic programs.") from error
    except (httpx.HTTPError, ValueError) as error:
        raise CompilerProviderError("Ollama could not compile symbolic programs.") from error
    try:
        raw = json.loads(envelope["message"]["content"])
        programs = raw["programs"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise CompilerOutputError("Ollama returned malformed symbolic programs.") from error
    return _validated_programs(programs, candidates)
