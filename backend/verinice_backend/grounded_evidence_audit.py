"""Atom-scoped, provenance-constrained evidence assessment with Ollama."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Sequence

import httpx
from pydantic import ValidationError

from .entity_alignment import (
    EntityAlignmentConfigurationError,
    align_identities,
    grouped_selected_texts,
)
from .evidence_scope import check_evidence_scope, mismatched_span_ids
from .schemas import (
    AssessmentAtomEvidence,
    DemoDocument,
    EvidenceScopeCheck,
    GroundedEvidenceAssessment,
    GroundedObligationAudit,
    IdentityAlignmentCheck,
    MaterialOmissionCertificate,
    PipelineAtom,
)
from .settings import settings
from .symbolic_reasoning.operators import incompatible_extremum_measures
from .symbolic_reasoning.profiles import (
    AWARD_MOTIVATION,
    AWARD_RECIPIENT,
    attribute_profile,
    exclusive_purpose_counterexample,
)


AUDIT_INSTRUCTIONS = """Assess the supplied candidate evidence for each atomic
claim. Use only supplied evidence IDs and do not use outside knowledge. This is
an evidence assessment, not a case verdict.

For every atomic claim, select zero to three IDs in each field. atomTrueIds are
sentences that make the exact atomic claim true. atomFalseIds are sentences
that make the exact atomic claim false. contextIds provide context but establish
neither truth value. Assess the selected sentences jointly and mark the bundle SUFFICIENT,
PARTIAL, or INSUFFICIENT. Support requires the asserted entity, relationship,
time, quantity, comparison, and scope. Refutation requires a direct conflict;
mere irrelevance, missing evidence, or uncertainty is not refutation. Context
may help interpret evidence but does not itself support or refute the claim.
Select the smallest evidence set that resolves the claim; three IDs is a limit,
not a target. Once one candidate directly resolves the complete atomic claim,
do not add topically related candidates unless they are independently decisive.

For a numeric claim, decisive evidence must discuss the same measured fact and
must state the claimed quantity, compatible source values, or an explicit
calculation from those values. A generic description of a dataset is context,
not numeric support. A different number about another measure or time period is
not refutation. Large descriptive counts may differ by up to five percent when
the wording and scale make clear that they are rounded; dates, percentages,
thresholds, and explicitly exact values are not eligible for that tolerance.
An explicit rejection or negation that rules out the claimed quantity or
duration is sufficient refutation even when the source gives no replacement
number. Mark that bundle SUFFICIENT, not PARTIAL.

An authoritative sentence that explicitly calls the proposition false or a
myth is direct refutation; it does not need an opposing exact number. Likewise,
"does not change" directly refutes a claimed increase without a measurement,
and an explicit different location refutes a location claim. Each evidence ID
may appear in at most one of atomTrueIds, atomFalseIds, or contextIds. If the
rationale says a candidate directly supports or refutes the atom, include that
candidate in the corresponding list. Judge sufficiency from whether the bundle
resolves every material part of the atom.

For an exclusivity claim using "only," "exclusively," or "solely," one explicit
in-scope counterexample is sufficient refutation. Prefer evidence addressing
the same relationship and time as the claim: a statement about why something
was developed can refute a claimed development purpose, while later use alone
cannot. Select the clearest direct counterexample rather than weaker funding or
background evidence.

For a historical event or priority claim, an authoritative source explicitly
asserting the event is direct support and an explicit denial is direct
refutation. If supplied sources directly assert opposing truth values, select
both sides and mark the joint bundle SUFFICIENT: the evidence sufficiently
establishes a source conflict even though the underlying history remains
disputed. Do not demand measurements that the atomic claim does not contain.

Relation examples: for atom "The bridge has cables," a source saying "the
bridge does not have cables" is REFUTES, never SUPPORTS. A source calling the
atom's proposition a "myth" or "false" is REFUTES; a heading that merely quotes
a myth is CONTEXT unless its truth status is explicit. If reading context
explicitly rejects the anchor's proposition, as in "But this isn't true," treat
the anchor and its context jointly as REFUTES; lexical overlap with the quoted
proposition is not support. For "A happened before B," two dated sentences
establishing B before A jointly REFUTE the atom. For a superlative, values
measured under different definitions are not opposing evidence: mark the bundle
PARTIAL or INSUFFICIENT and explain the ambiguity.
For atom "Rao made the first powered crossing," if E1 says Rao made the first
powered crossing and E2 says Rao never made a powered crossing, select E1 as
atomTrueIds and E2 as atomFalseIds and mark the bundle SUFFICIENT.

Each ANCHOR is selectable. READING CONTEXT may resolve a reference in that
anchor but is not an independent candidate. Never move evidence between atomic
claims. Some candidates may be absent because deterministic scope validation
excluded an explicit jurisdiction mismatch.

Keep missingInformation to one short sentence, and keep reason under 40 words.

Return materialOmission.detected only when sufficient selected support evidence
establishes a narrower fact and selected context establishes an omitted scope,
exception, cost, comparison period, or eligibility condition that materially
changes the claim. Otherwise return false and empty ID lists. Return JSON only."""

MAX_CONTEXT_CHARACTERS = 1600


class GroundedEvidenceAuditError(RuntimeError):
    pass


class GroundedEvidenceAuditConfigurationError(GroundedEvidenceAuditError):
    pass


class GroundedEvidenceAuditProviderError(GroundedEvidenceAuditError):
    pass


class GroundedEvidenceAuditOutputError(GroundedEvidenceAuditError):
    pass


def _compact(text: str, limit: int = MAX_CONTEXT_CHARACTERS) -> str:
    return " ".join(text.split())[:limit]


def _audit_schema(codes_by_atom: dict[str, list[str]]) -> dict[str, Any]:
    all_codes = [code for codes in codes_by_atom.values() for code in codes]
    all_evidence_items: dict[str, Any] = {"type": "string"}
    if all_codes:
        all_evidence_items["enum"] = all_codes
    obligation_schemas: dict[str, Any] = {}
    for atom_code, codes in codes_by_atom.items():
        local_items: dict[str, Any] = {"type": "string"}
        if codes:
            local_items["enum"] = codes
        selection = {"type": "array", "items": local_items, "maxItems": min(3, len(codes))}
        obligation_schemas[atom_code] = {
            "type": "object",
            "properties": {
                "atomTrueIds": selection,
                "atomFalseIds": selection,
                "contextIds": selection,
                "sufficiency": {"type": "string", "enum": ["SUFFICIENT", "PARTIAL", "INSUFFICIENT"]},
                "missingInformation": {"type": "string", "maxLength": 180},
                "reason": {"type": "string", "maxLength": 300},
            },
            "required": ["atomTrueIds", "atomFalseIds", "contextIds", "sufficiency", "missingInformation", "reason"],
        }
    return {
        "type": "object",
        "properties": {
            "obligations": {
                "type": "object",
                "properties": obligation_schemas,
                "required": list(codes_by_atom),
            },
            "materialOmission": {
                "type": "object",
                "properties": {
                    "detected": {"type": "boolean"},
                    "supportIds": {"type": "array", "items": all_evidence_items, "maxItems": 3},
                    "contextIds": {"type": "array", "items": all_evidence_items, "maxItems": 3},
                    "reason": {"type": "string", "maxLength": 300},
                },
                "required": ["detected", "supportIds", "contextIds", "reason"],
            },
        },
        "required": ["obligations", "materialOmission"],
    }


def _audit_input(
    claim: str,
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[AssessmentAtomEvidence],
    documents: Sequence[DemoDocument],
    scope_checks: dict[str, list[EvidenceScopeCheck]],
) -> tuple[str, Dict[str, tuple[PipelineAtom, Dict[str, Any]]], dict[str, Any]]:
    evidence_by_atom = {item.atom_id: item for item in evidence}
    documents_by_id = {item.id: item for item in documents}
    mapped: Dict[str, tuple[PipelineAtom, Dict[str, Any]]] = {}
    lines = [f"CLAIM: {claim}"]
    for atom_index, atom in enumerate(atoms, start=1):
        atom_code = f"O{atom_index}"
        lines.append(f"\nATOMIC CLAIM {atom_code}: {atom.text}")
        excluded = mismatched_span_ids(scope_checks[atom.id])
        candidates: Dict[str, Any] = {}
        eligible_index = 0
        for span in evidence_by_atom[atom.id].spans:
            if span.id in excluded:
                continue
            eligible_index += 1
            code = f"{atom_code}-E{eligible_index}"
            candidates[code] = span
            document = documents_by_id[span.document_id]
            lines.append(f"{code} | {_compact(document.title, 180)} | ANCHOR: {_compact(span.text)}")
            if span.context_spans:
                context = " ".join(f"[{item.direction}] {_compact(item.text)}" for item in span.context_spans)
                lines.append(f"  READING CONTEXT (not independent evidence): {context}")
            elif span.context and span.context.strip() != span.text.strip():
                lines.append(f"  READING CONTEXT (not independent evidence): {_compact(span.context)}")
        mapped[atom_code] = (atom, candidates)
    return "\n".join(lines), mapped, _audit_schema({
        atom_code: list(candidates) for atom_code, (_atom, candidates) in mapped.items()
    })


def _response_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise GroundedEvidenceAuditOutputError("Ollama returned an invalid response envelope.")
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise GroundedEvidenceAuditOutputError("Ollama returned no evidence assessment JSON.")
    if not payload.get("done", True):
        raise GroundedEvidenceAuditProviderError("Ollama stopped before completing the evidence assessment.")
    return message["content"]


async def _request_audit(prompt: str, schema: dict[str, Any]) -> Any:
    payload = {
        "model": settings.ollama_model, "stream": False,
        "messages": [{"role": "system", "content": AUDIT_INSTRUCTIONS}, {"role": "user", "content": prompt}],
        "think": False, "format": schema,
        "options": {"temperature": 0, "seed": 0, "num_ctx": settings.evidence_audit_context_size, "num_predict": 1400},
        "keep_alive": settings.ollama_keep_alive,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as error:
        raise GroundedEvidenceAuditProviderError("The Ollama evidence assessment timed out. Check that Ollama is running and retry.") from error
    except httpx.HTTPStatusError as error:
        raise GroundedEvidenceAuditProviderError("Ollama rejected the evidence assessment request.") from error
    except (httpx.HTTPError, ValueError) as error:
        raise GroundedEvidenceAuditProviderError("Ollama could not complete the evidence assessment.") from error


def _unique_valid_codes(raw: Any, candidates: Dict[str, Any]) -> list[str]:
    if not isinstance(raw, list):
        return []
    codes = list(dict.fromkeys(str(code) for code in raw))[:3]
    unknown = [code for code in codes if code not in candidates]
    if unknown:
        raise GroundedEvidenceAuditOutputError(
            "The model selected unavailable evidence IDs: " + ", ".join(unknown)
        )
    return codes


_EMPTY_MODEL_VALUES = {"", "false", "null", "none", "n/a", "not applicable", "no"}

_QUANTITY_RE = re.compile(
    r"(?<![\w.])(?P<number>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"\s*(?P<scale>billion|million|thousand|bn|mn|m|k|%|percent(?:age)?)?"
    r"(?=\s|[.,;:!?)]|$)",
    re.IGNORECASE,
)
_QUANTITY_SCALES = {
    "billion": 1_000_000_000.0, "bn": 1_000_000_000.0,
    "million": 1_000_000.0, "mn": 1_000_000.0, "m": 1_000_000.0,
    "thousand": 1_000.0, "k": 1_000.0,
    "%": 0.01, "percent": 0.01, "percentage": 0.01,
}
_QUANTITY_WORDS = {
    "zero": 0.0, "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0,
    "five": 5.0, "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0,
    "ten": 10.0, "eleven": 11.0, "twelve": 12.0, "thirteen": 13.0,
    "fourteen": 14.0, "fifteen": 15.0, "sixteen": 16.0,
    "seventeen": 17.0, "eighteen": 18.0, "nineteen": 19.0,
    "twenty": 20.0,
}
_QUANTITY_WORD_RE = re.compile(
    r"(?<![\w-])(?:" + "|".join(_QUANTITY_WORDS) + r")(?![\w-])",
    re.IGNORECASE,
)
_NUMERIC_STOPWORDS = {
    "about", "added", "after", "already", "and", "approximately", "around", "back",
    "been", "before", "claim", "during", "from", "height", "more", "pandemic",
    "than", "that", "the", "their", "there", "these", "this", "through", "time", "were",
    "where", "with", "would",
}
_DIRECT_REFUTATION_RE = re.compile(
    r"\b(?:false|incorrect|inaccurate|myth|not true|"
    r"isn[’']t\s+true|did not|didn[’']t|does not|doesn[’']t|never)\b",
    re.IGNORECASE,
)


def _quantities(text: str) -> list[tuple[float, str]]:
    """Return material quantities while excluding bare calendar years."""
    values: list[tuple[float, str]] = []
    for match in _QUANTITY_RE.finditer(text):
        raw = float(match.group("number").replace(",", ""))
        scale = (match.group("scale") or "").casefold()
        if not scale and raw.is_integer() and 1000 <= raw <= 2099:
            continue
        values.append((raw * _QUANTITY_SCALES.get(scale, 1.0), scale))
    values.extend(
        (_QUANTITY_WORDS[match.group(0).casefold()], "")
        for match in _QUANTITY_WORD_RE.finditer(text)
    )
    return values


def _numeric_terms(text: str) -> set[str]:
    terms = set()
    for token in re.findall(r"[A-Za-z]{3,}", text.casefold()):
        if token in _NUMERIC_STOPWORDS:
            continue
        terms.add(token[:-1] if token.endswith("s") and len(token) > 4 else token)
    return terms


def _quantity_matches(claim_value: float, claim_scale: str, evidence_value: float, evidence_scale: str) -> bool:
    if claim_scale in {"%", "percent", "percentage"} or evidence_scale in {"%", "percent", "percentage"}:
        return abs(claim_value - evidence_value) <= 1e-9
    if abs(claim_value - evidence_value) <= 1e-9:
        return True
    # A small tolerance is reserved for large descriptive counts such as
    # employment estimates. It is deliberately unavailable to ordinary counts.
    return abs(claim_value) >= 1_000_000 and abs(claim_value - evidence_value) / abs(claim_value) <= 0.05


def _numeric_relation_is_grounded(
    atom_text: str,
    relation_codes: Sequence[str],
    candidates: Dict[str, Any],
    *,
    support: bool,
) -> bool:
    claim_quantities = _quantities(atom_text)
    if not claim_quantities or not relation_codes:
        return True
    selected_text = " ".join(
        " ".join(
            part for part in (
                candidates[code].text,
                candidates[code].context or "",
                " ".join(item.text for item in candidates[code].context_spans),
            ) if part
        )
        for code in relation_codes
    )
    if not (_numeric_terms(atom_text) & _numeric_terms(selected_text)):
        return False
    evidence_quantities = _quantities(selected_text)
    if support:
        return all(
            any(_quantity_matches(claim_value, claim_scale, evidence_value, evidence_scale)
                for evidence_value, evidence_scale in evidence_quantities)
            for claim_value, claim_scale in claim_quantities
        )
    return bool(evidence_quantities) or bool(_DIRECT_REFUTATION_RE.search(selected_text))


def _minimal_numeric_relation_codes(
    atom_text: str,
    relation_codes: Sequence[str],
    candidates: Dict[str, Any],
    *,
    support: bool,
) -> list[str]:
    """Discard bundled extras when one candidate grounds the numeric relation alone."""
    codes = list(relation_codes)
    if len(codes) < 2 or not _quantities(atom_text):
        return codes
    independently_grounded = [
        code
        for code in codes
        if _numeric_relation_is_grounded(
            atom_text, [code], candidates, support=support
        )
    ]
    return independently_grounded or codes


def _numeric_support_uses_rounding(
    atom_text: str,
    relation_codes: Sequence[str],
    candidates: Dict[str, Any],
) -> bool:
    claim_quantities = _quantities(atom_text)
    if not claim_quantities or not relation_codes:
        return False
    selected_text = " ".join(
        " ".join(
            part for part in (
                candidates[code].text,
                candidates[code].context or "",
                " ".join(item.text for item in candidates[code].context_spans),
            ) if part
        )
        for code in relation_codes
    )
    evidence_quantities = _quantities(selected_text)
    return any(
        not any(abs(claim_value - evidence_value) <= 1e-9 for evidence_value, _ in evidence_quantities)
        and any(
            _quantity_matches(claim_value, claim_scale, evidence_value, evidence_scale)
            for evidence_value, evidence_scale in evidence_quantities
        )
        for claim_value, claim_scale in claim_quantities
    )


def _clean_model_sentence(value: Any, *, fallback: str = "", limit: int = 300) -> str:
    """Normalize short display copy without exposing JSON-ish model values."""
    if value is None or isinstance(value, bool):
        return fallback
    text = " ".join(str(value).split()).strip()
    if text.casefold() in _EMPTY_MODEL_VALUES:
        return fallback
    complete = re.match(r"^(.+?[.!?])(?:\s|$)", text)
    if complete:
        return complete.group(1)[:limit]
    if len(text) <= limit:
        return text if text.endswith((".", "!", "?")) else f"{text}."
    # A long fragment has no safe sentence boundary. Do not publish a clipped
    # half-sentence as an explanation.
    return fallback or "Additional source information is needed."


def _parse_audit(
    payload: Any,
    mapped: Dict[str, tuple[PipelineAtom, Dict[str, Any]]],
    scope_checks: dict[str, list[EvidenceScopeCheck]],
    documents: Sequence[DemoDocument] = (),
) -> GroundedEvidenceAssessment:
    try:
        raw = json.loads(_response_content(payload))
    except (ValueError, json.JSONDecodeError) as error:
        raise GroundedEvidenceAuditOutputError("The model returned malformed assessment JSON.") from error
    items = raw.get("obligations") if isinstance(raw, dict) else None
    if isinstance(items, dict):
        items = [dict(value, obligationId=atom_code) for atom_code, value in items.items() if isinstance(value, dict)]
    if not isinstance(items, list) or len(items) != len(mapped):
        raise GroundedEvidenceAuditOutputError("The model returned incomplete atomic-claim assessments.")
    document_texts = {
        document.id: "\n".join(part for part in (document.title, document.text) if part)
        for document in documents
    }
    selections: dict[str, dict[str, Any]] = {}
    identity_demoted_codes: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise GroundedEvidenceAuditOutputError("The model returned an invalid atomic-claim assessment.")
        atom_code = str(item.get("obligationId", ""))
        if atom_code not in mapped or atom_code in selections:
            raise GroundedEvidenceAuditOutputError("The model returned duplicate or unknown atomic-claim assessments.")
        candidates = mapped[atom_code][1]
        sufficiency = str(item.get("sufficiency", ""))
        if sufficiency not in {"SUFFICIENT", "PARTIAL", "INSUFFICIENT"}:
            raise GroundedEvidenceAuditOutputError("The model returned an unknown evidence sufficiency value.")
        missing = _clean_model_sentence(item.get("missingInformation"), limit=220)
        # A sufficient bundle resolves the obligation by definition. Model
        # commentary about absent but non-decisive detail must not be exposed
        # as required missing information.
        if sufficiency == "SUFFICIENT":
            missing = ""
        selections[atom_code] = {
            "support": _unique_valid_codes(item.get("atomTrueIds"), candidates),
            "refute": _unique_valid_codes(item.get("atomFalseIds"), candidates),
            "context": _unique_valid_codes(item.get("contextIds"), candidates),
            "sufficiency": sufficiency,
            "missing": missing,
            "reason": _clean_model_sentence(
                item.get("reason"), fallback="No rationale was returned.", limit=300
            ),
        }
        support = selections[atom_code]["support"]
        refute = selections[atom_code]["refute"]
        context = selections[atom_code]["context"]
        contradictory = set(support) & set(refute)
        # Two sources may reproduce the same sentence under different IDs. The
        # same normalized statement cannot coherently support and refute one
        # atom, so demote both copies to reading context.
        support_by_text = {
            " ".join(candidates[code].text.casefold().split()): code for code in support
        }
        refute_by_text = {
            " ".join(candidates[code].text.casefold().split()): code for code in refute
        }
        duplicated_conflicts = support_by_text.keys() & refute_by_text.keys()
        for text in duplicated_conflicts:
            contradictory.update({support_by_text[text], refute_by_text[text]})
        if contradictory:
            # A single sentence cannot be both decisive support and decisive
            # refutation for one atom. Preserve it conservatively as context
            # instead of turning an invalid model assignment into a verdict.
            support = [code for code in support if code not in contradictory]
            refute = [code for code in refute if code not in contradictory]
            context = list(dict.fromkeys([*context, *sorted(contradictory)]))[:3]
        # A one-sided sentence cannot establish a relation between two named
        # jurisdictions. The model may correctly extract each date yet assign
        # the Sweden-only sentence as support for "Sweden before Finland".
        # Require each decisive bundle for an explicit before/after comparison
        # to cover every compared jurisdiction; incomplete bundles remain
        # available as context and to the grounded symbolic stage.
        atom, _ = mapped[atom_code]
        if re.search(r"\b(?:before|after)\b", atom.text, re.IGNORECASE):
            checks_by_span = {
                check.span_id: check for check in scope_checks[atom.id]
            }
            claim_jurisdictions = {
                jurisdiction
                for check in checks_by_span.values()
                for jurisdiction in check.claim_jurisdictions
            }
            if len(claim_jurisdictions) >= 2:
                for relation_codes in (support, refute):
                    covered = {
                        jurisdiction
                        for code in relation_codes
                        for jurisdiction in checks_by_span[candidates[code].id].evidence_jurisdictions
                    }
                    if not claim_jurisdictions.issubset(covered):
                        context = list(dict.fromkeys([*context, *relation_codes]))[:3]
                        relation_codes.clear()
        original_support = list(support)
        original_refute = list(refute)
        support = _minimal_numeric_relation_codes(
            atom.text, support, candidates, support=True
        )
        refute = _minimal_numeric_relation_codes(
            atom.text, refute, candidates, support=False
        )
        pruned_numeric_relations = (
            support != original_support or refute != original_refute
        )
        numeric_demotions: list[str] = []
        if not _numeric_relation_is_grounded(atom.text, support, candidates, support=True):
            numeric_demotions.extend(support)
            support.clear()
        if not _numeric_relation_is_grounded(atom.text, refute, candidates, support=False):
            numeric_demotions.extend(refute)
            refute.clear()
        if numeric_demotions:
            context = list(dict.fromkeys([*numeric_demotions, *context]))[:3]
            if not support and not refute:
                if selections[atom_code]["sufficiency"] == "SUFFICIENT":
                    selections[atom_code]["sufficiency"] = "PARTIAL"
                selections[atom_code]["missing"] = (
                    "Evidence stating the claimed quantity for the same measured fact is needed."
                )
                selections[atom_code]["reason"] = (
                    "The selected evidence does not ground the atom's numeric assertion."
                )
        elif support and _numeric_support_uses_rounding(atom.text, support, candidates):
            selections[atom_code]["reason"] = (
                "The selected evidence reports a compatible rounded quantity for the same measured fact."
            )
        elif pruned_numeric_relations and support and not refute:
            selections[atom_code]["reason"] = (
                "The retained evidence directly supports the atomic claim's numeric assertion."
            )
        elif pruned_numeric_relations and refute and not support:
            selections[atom_code]["reason"] = (
                "The retained evidence directly refutes the atomic claim's numeric assertion."
            )
        exclusive_counterexamples = [
            code
            for code, candidate in candidates.items()
            if exclusive_purpose_counterexample(atom.text, candidate.text)
        ]
        if exclusive_counterexamples:
            support = [code for code in support if code not in exclusive_counterexamples]
            refute = exclusive_counterexamples[:1]
            selections[atom_code]["sufficiency"] = "SUFFICIENT"
            selections[atom_code]["missing"] = ""
            selections[atom_code]["reason"] = (
                "The selected evidence states an explicit competing development purpose."
            )
        decisive_codes = list(dict.fromkeys([*support, *refute]))
        if decisive_codes and incompatible_extremum_measures(
            atom.text, [candidates[code].text for code in decisive_codes]
        ):
            context = list(dict.fromkeys([*decisive_codes, *context]))[:3]
            support.clear()
            refute.clear()
            selections[atom_code]["sufficiency"] = "PARTIAL"
            selections[atom_code]["missing"] = (
                "Comparable measurements using one definition and a complete comparison set are needed."
            )
            selections[atom_code]["reason"] = (
                "The selected evidence compares measurements that use incompatible definitions."
            )
        # Once the model has selected valid direct evidence on both sides, the
        # bundle is sufficient to establish an evidence conflict. Marking that
        # same bundle PARTIAL would discard both validated positions during
        # aggregation and incorrectly turn a conflict into missing evidence.
        if support and refute:
            selections[atom_code]["sufficiency"] = "SUFFICIENT"
            selections[atom_code]["missing"] = ""
            selections[atom_code]["reason"] = (
                "The selected evidence directly supports and refutes the same atomic claim."
            )
        identity_checks: list[IdentityAlignmentCheck] = []
        identity_demotions: list[str] = []
        for relation, relation_codes in (("SUPPORTS", support), ("REFUTES", refute)):
            if not relation_codes:
                continue
            selected_by_document = grouped_selected_texts(
                (
                    candidates[code].document_id,
                    " ".join(
                        part for part in (
                            candidates[code].text,
                            candidates[code].context or "",
                            " ".join(item.text for item in candidates[code].context_spans),
                        ) if part
                    ),
                )
                for code in relation_codes
            )
            # Direct parser tests may omit documents. In production the full
            # source is always supplied; the fallback still enforces exact
            # identity matching over the selected evidence itself.
            local_document_texts = dict(document_texts)
            for document_id, texts in selected_by_document.items():
                local_document_texts.setdefault(document_id, " ".join(texts))
            alignment = align_identities(
                atom.text,
                selected_by_document,
                local_document_texts,
                relation=relation,
                strict_refutation=attribute_profile(atom) in {
                    AWARD_MOTIVATION, AWARD_RECIPIENT,
                },
            )
            identity_checks.append(IdentityAlignmentCheck(
                relation=relation,
                span_ids=[candidates[code].id for code in relation_codes],
                status=alignment.status,
                required_entities=list(alignment.required_entities),
                matched_entities=list(alignment.matched_entities),
                reason=alignment.reason,
            ))
            if alignment.status == "UNRESOLVED":
                identity_demotions.extend(relation_codes)
                relation_codes.clear()
        if identity_demotions:
            identity_demoted_codes.update(identity_demotions)
            context = list(dict.fromkeys([*identity_demotions, *context]))[:3]
            if not support and not refute:
                selections[atom_code]["sufficiency"] = "INSUFFICIENT"
                selections[atom_code]["missing"] = (
                    "Evidence explicitly identifying the claimed entity is needed."
                )
                selections[atom_code]["reason"] = (
                    "The selected evidence does not align every named identity in the atomic claim."
                )
            elif support and not refute:
                selections[atom_code]["missing"] = ""
                selections[atom_code]["reason"] = (
                    "Only the supporting relation retained a non-conflicting subject identity."
                )
            elif refute and not support:
                selections[atom_code]["missing"] = ""
                selections[atom_code]["reason"] = (
                    "Only the refuting relation retained a non-conflicting subject identity."
                )
        decisive = set(support) | set(refute)
        selections[atom_code]["support"] = support
        selections[atom_code]["refute"] = refute
        selections[atom_code]["context"] = [code for code in context if code not in decisive]
        selections[atom_code]["identity_checks"] = identity_checks

    obligations: list[GroundedObligationAudit] = []
    all_candidates: dict[str, Any] = {}
    for atom_code, (atom, candidates) in mapped.items():
        selection = selections[atom_code]
        all_candidates.update(candidates)
        obligations.append(GroundedObligationAudit(
            atom_id=atom.id,
            support_span_ids=[candidates[code].id for code in selection["support"]],
            refute_span_ids=[candidates[code].id for code in selection["refute"]],
            context_span_ids=[candidates[code].id for code in selection["context"]],
            sufficiency=selection["sufficiency"],
            missing_information=selection["missing"],
            reason=selection["reason"],
            scope_checks=scope_checks[atom.id],
            identity_checks=selection["identity_checks"],
        ))

    omission_raw = raw.get("materialOmission")
    if not isinstance(omission_raw, dict):
        raise GroundedEvidenceAuditOutputError("The model omitted the material-omission certificate.")
    detected = bool(omission_raw.get("detected"))
    support_codes = _unique_valid_codes(omission_raw.get("supportIds"), all_candidates)
    context_codes = _unique_valid_codes(omission_raw.get("contextIds"), all_candidates)
    omission_reason = omission_raw.get("reason")
    if detected:
        sufficient_codes = {
            code for atom_code, selection in selections.items()
            if selection["sufficiency"] == "SUFFICIENT" for code in selection["support"]
        }
        if not set(support_codes).issubset(sufficient_codes):
            invalid_codes = set(support_codes) - sufficient_codes
            if invalid_codes.issubset(identity_demoted_codes):
                detected = False
                support_codes, context_codes = [], []
                omission_reason = (
                    "No material omission remained after deterministic evidence validation."
                )
            else:
                raise GroundedEvidenceAuditOutputError(
                    "A material omission must cite sufficient supporting evidence."
                )
    else:
        support_codes, context_codes = [], []
    try:
        omission = MaterialOmissionCertificate(
            detected=detected,
            support_span_ids=[all_candidates[code].id for code in support_codes],
            context_span_ids=[all_candidates[code].id for code in context_codes],
            reason=_clean_model_sentence(
                omission_reason,
                fallback="No material omission was established.",
                limit=300,
            ),
        )
    except ValidationError as error:
        raise GroundedEvidenceAuditOutputError("The model returned an invalid material-omission certificate.") from error
    return GroundedEvidenceAssessment(obligations=obligations, material_omission=omission)


async def audit_grounded_evidence(
    claim: str,
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[AssessmentAtomEvidence],
    documents: Sequence[DemoDocument],
) -> GroundedEvidenceAssessment:
    if not settings.ollama_url.strip() or not settings.ollama_model.strip():
        raise GroundedEvidenceAuditConfigurationError("Evidence assessment requires a configured local Ollama model.")
    try:
        # Fail before the provider call so a missing local model produces a
        # clear configuration response rather than an ambiguous audit failure.
        from .entity_alignment import extract_identity_mentions

        for atom in atoms:
            extract_identity_mentions(atom.text)
        scope_checks = check_evidence_scope(atoms, evidence, documents)
        prompt, mapped, schema = _audit_input(claim, atoms, evidence, documents, scope_checks)
        return _parse_audit(
            await _request_audit(prompt, schema), mapped, scope_checks, documents
        )
    except EntityAlignmentConfigurationError as error:
        raise GroundedEvidenceAuditConfigurationError(str(error)) from error
