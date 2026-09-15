from __future__ import annotations

import re
from typing import Sequence

from ..schemas import (
    AssessmentAtomEvidence,
    GroundedEvidenceAssessment,
    PipelineAtom,
    ProgramStep,
    ReasoningResponse,
    RetrievalDocument,
    SymbolicExecution,
    SymbolicListItem,
    SymbolicOperator,
    SymbolicProgram,
    SymbolicStatus,
)
from ..settings import settings
from .compiler import CompilerConfigurationError, CompilerOutputError, CompilerProviderError, compile_programs
from .grounding import build_candidates, lexical_tokens, normalize, validate_grounding
from .operators import REGISTRY, _subject_before_copula
from .profiles import distinct_count_request, distinct_profile, extract_distinct_values


class SymbolicReasoningError(RuntimeError):
    pass


class SymbolicReasoningConfigurationError(SymbolicReasoningError):
    pass


class SymbolicReasoningProviderError(SymbolicReasoningError):
    pass


class SymbolicReasoningOutputError(SymbolicReasoningError):
    pass


_PROGRAM_OPERATIONS = {
    SymbolicOperator.set_membership: "MEMBER",
    SymbolicOperator.numeric_compare: "NUMERIC_COMPARE",
    SymbolicOperator.temporal_compare: "TEMPORAL_COMPARE",
    SymbolicOperator.attribute_compare: "EQUAL",
    SymbolicOperator.count_distinct: "COUNT_DISTINCT",
    SymbolicOperator.extremum_compare: "EXTREMUM_COUNTEREXAMPLE",
}


def _explicit_countries(text: str) -> set[str]:
    """Return only country names explicitly written in the premise text."""
    try:
        import pycountry
    except ImportError:
        return set()
    aliases = {country.name.casefold(): country.alpha_2 for country in pycountry.countries}
    aliases.update({
        "usa": "US", "u.s.": "US", "us": "US", "united states": "US",
        "uk": "GB", "u.k.": "GB", "united kingdom": "GB",
    })
    normalized = normalize(text)
    return {
        code for alias, code in aliases.items()
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", normalized)
    }


def _program(operator: SymbolicOperator, premise_ids: Sequence[str], candidate_id: str) -> SymbolicProgram:
    inputs = list(premise_ids) or [candidate_id]
    steps = [
        ProgramStep(
            id=f"input-{index}", operation="LOOKUP", input_ids=[premise_id],
            output_type="FACT", description="Read an unchanged server-owned premise.",
        )
        for index, premise_id in enumerate(inputs, start=1)
    ]
    output_id = "result"
    steps.append(ProgramStep(
        id=output_id,
        operation=_PROGRAM_OPERATIONS[operator],
        input_ids=[step.id for step in steps],
        output_type="NUMBER" if operator == SymbolicOperator.count_distinct else "BOOLEAN",
        description="Validate operand alignment and execute the typed operation in Python.",
    ))
    return SymbolicProgram(steps=steps, output_step_id=output_id)


def _validated_operand_ids(candidate, atom: PipelineAtom, premise_ids: Sequence[str], premises) -> list[str]:
    """Complete a mapped program with source-owned operands, never results."""
    result = list(premise_ids)
    operator = SymbolicOperator(candidate.operator)
    if operator == SymbolicOperator.extremum_compare:
        for premise_id in candidate.premise_ids:
            premise = premises[premise_id]
            if premise.kind == "OPERAND" and premise_id not in result:
                result.append(premise_id)
            if len(result) >= 10:
                break
    elif operator == SymbolicOperator.count_distinct:
        # Once the compiler maps the server-issued count candidate, attach all
        # candidate premises that Python can align to explicit values. This
        # avoids making completeness of a lower-bound count depend on the model
        # repeating every already-grounded operand.
        for premise_id in candidate.premise_ids:
            if premise_id in result:
                continue
            if extract_distinct_values(candidate.profile, [premises[premise_id]], atom):
                result.append(premise_id)
            if len(result) >= 10:
                break
    elif operator == SymbolicOperator.temporal_compare and re.search(r"(?i)\b(?:before|after)\b", atom.text):
        comparison = re.match(r"(?is)^(.+?)\b(?:before|after)\b(.+?)[.!?]?$", atom.text.strip())
        if comparison:
            entities = []
            for side in comparison.groups():
                names = re.findall(r"\b[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)*", side)
                if names:
                    entities.append(normalize(names[0]))
            claim_terms = lexical_tokens(atom.text)
            for entity in entities:
                if any(entity in normalize(premises[item].text) and re.search(r"\b(?:19|20)\d{2}\b", premises[item].text) for item in result):
                    continue
                choices = [
                    item for item in candidate.premise_ids
                    if entity in normalize(premises[item].text)
                    and re.search(r"\b(?:19|20)\d{2}\b", premises[item].text)
                ]
                choices.sort(key=lambda item: (-len(claim_terms & lexical_tokens(premises[item].text)), item))
                if choices:
                    result.append(choices[0])
    return list(dict.fromkeys(result))[:10]


def _presentation_premise_ids(
    operator: SymbolicOperator,
    atom: PipelineAtom,
    premise_ids: Sequence[str],
    premises,
    status: SymbolicStatus,
    expression: str = "",
) -> list[str]:
    """Keep only the grounded premises consumed by the displayed operation.

    Execution may inspect the contents covered by a list certificate, but the
    certificate is the single public premise for an absence result.
    """
    ordered = list(dict.fromkeys(premise_ids))
    if operator == SymbolicOperator.set_membership:
        certificates = [item for item in ordered if premises[item].kind == "LIST_CERTIFICATE"]
        if certificates:
            return certificates[:1]
        subject_terms = lexical_tokens(atom.text)
        matching = [
            item for item in ordered
            if premises[item].kind == "LIST_ITEM"
            and lexical_tokens(premises[item].text) & subject_terms
        ]
        return matching[:1]
    if operator == SymbolicOperator.count_distinct:
        profile = distinct_profile(atom)
        request = distinct_count_request(atom)
        target = request[0] if request else 2
        selected: list[str] = []
        seen: set[str] = set()
        for item in ordered:
            values = extract_distinct_values(profile or "", [premises[item]], atom) - seen
            if values:
                selected.append(item)
                seen.update(values)
            if len(seen) >= target:
                break
        return selected[:target]
    if operator == SymbolicOperator.temporal_compare:
        years = list(dict.fromkeys(re.findall(r"\b(?:19|20)\d{2}\b", expression)))
        selected: list[str] = []
        atom_terms = lexical_tokens(atom.text)
        for year in years:
            choices = [item for item in ordered if year in premises[item].text and item not in selected]
            choices.sort(key=lambda item: (-len(atom_terms & lexical_tokens(premises[item].text)), item))
            if choices:
                selected.append(choices[0])
        return selected[:2] or ordered[:2]
    if operator == SymbolicOperator.extremum_compare:
        # A counterexample consumes the claimed subject value and one aligned
        # comparator. An unresolved incompatible-measure check likewise needs
        # only one premise for each measurement definition.
        targets = [value.lstrip("0") or "0" for value in re.findall(r"\d+(?:\.\d+)?", expression)]
        selected: list[str] = []
        for target in targets:
            for item in ordered:
                values = [
                    value.replace(",", "").lstrip("0") or "0"
                    for value in re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", premises[item].text)
                ]
                if target in values and item not in selected:
                    selected.append(item)
                    break
        return (selected or ordered)[:2]
    if operator == SymbolicOperator.attribute_compare:
        subject_terms = lexical_tokens(atom.text)
        # A location comparison consumes a premise that explicitly names the
        # source country. General subject overlap (for example, "Gustave
        # Eiffel") is not enough to establish the Eiffel Tower's location.
        if re.search(r"\b(?:located|location)\b", normalize(atom.text)) and _explicit_countries(atom.text):
            located = [item for item in ordered if _explicit_countries(premises[item].text)]
            located.sort(key=lambda item: (-len(subject_terms & lexical_tokens(premises[item].text)), item))
            if not located:
                return ordered[:2]
            selected = located[:1]
            subject = _subject_before_copula(atom.text)
            if subject and subject not in normalize(premises[selected[0]].text):
                subject_premises = [
                    item for item in ordered
                    if subject in normalize(premises[item].text) and item not in selected
                ]
                subject_premises.sort(
                    key=lambda item: (-len(subject_terms & lexical_tokens(premises[item].text)), item)
                )
                selected = subject_premises[:1] + selected
            return selected[:2]
        # An exclusivity result consumes the statement that explicitly names
        # the competing values. A heading or one-sided purpose statement is
        # background rather than a decisive premise.
        if "exclusively" in normalize(atom.text):
            competing = [
                item for item in ordered
                if re.search(r"(?i)\bmilitary\b", premises[item].text)
                and re.search(r"(?i)\bcivil(?:ian)?\b", premises[item].text)
            ]
            if competing:
                return competing[:1]
        # Prize-reason comparisons consume the explicit citation or motivation,
        # not a nearby award-date sentence that happens to mention the prize.
        if "reason" in expression and re.search(r"(?i)\b(?:prize|award|citation)\b", atom.text):
            reasons = [
                item for item in ordered
                if re.search(r"(?i)\b(?:motivation|reason)\b|\bfor\s+(?:his|her|their|the)\b", premises[item].text)
            ]
            if reasons:
                return reasons[:1]
        # Explicit source negation is the decisive fact for a simple attribute
        # conflict such as “has horns” or “grows thicker”.
        negated = [
            item for item in ordered
            if re.search(r"(?i)\b(?:no|not|never|without|did not|does not|will not|won['’]t|cannot|can['’]t|false|myth)\b", premises[item].text)
            and lexical_tokens(premises[item].text) & subject_terms
        ]
        if negated:
            negated.sort(key=lambda item: (-len(subject_terms & lexical_tokens(premises[item].text)), item))
            return negated[:2]
        aligned = [item for item in ordered if lexical_tokens(premises[item].text) & subject_terms]
        return (aligned or ordered)[:2]
    if status in {SymbolicStatus.proved, SymbolicStatus.disproved}:
        return ordered[:2]
    return ordered[:3]


def _presentation_premise(premise, premises):
    """Attach exact list rows to a displayed completeness certificate."""
    if premise.kind != "LIST_CERTIFICATE":
        return premise
    items = sorted(
        (
            item for item in premises.values()
            if item.kind == "LIST_ITEM"
            and item.document_id == premise.document_id
            and item.content_hash == premise.content_hash
        ),
        key=lambda item: (item.start, item.end, item.id),
    )
    if premise.item_count != len(items):
        raise SymbolicReasoningOutputError(
            f"List certificate {premise.id} covers {premise.item_count} items but {len(items)} were grounded"
        )
    return premise.model_copy(update={
        "list_items": [
            SymbolicListItem(
                id=item.id,
                document_id=item.document_id,
                text=item.text,
                start=item.start,
                end=item.end,
                content_hash=item.content_hash,
            )
            for item in items
        ]
    })


def _execution_preconditions(candidate, execution_premises, outcome) -> list[dict]:
    resolved = outcome["status"] in {SymbolicStatus.proved, SymbolicStatus.disproved}
    checks = [
        {
            "name": "Source grounding",
            "status": "PASSED",
            "detail": f"{len(execution_premises)} selected premise(s) retain exact source offsets.",
        },
        {
            "name": "Registered profile",
            "status": "PASSED" if candidate.profile else "UNRESOLVED",
            "detail": candidate.profile.replace("_", " ").lower() if candidate.profile else "No registered extraction profile was available.",
        },
        {
            "name": "Operand alignment",
            "status": "PASSED" if resolved else "UNRESOLVED",
            "detail": outcome["explanation"],
        },
    ]
    if candidate.operator == "SET_MEMBERSHIP":
        complete = any(premise.kind == "LIST_CERTIFICATE" for premise in execution_premises)
        checks.append({
            "name": "Closed-set evidence",
            "status": "PASSED" if complete else "UNRESOLVED",
            "detail": "A validated complete-list certificate is present." if complete else "No complete-list certificate was selected; only explicit presence can resolve membership.",
        })
    if candidate.operator == "COUNT_DISTINCT":
        checks.append({
            "name": "Count semantics",
            "status": "PASSED" if "≥" in outcome["expression"] else "UNRESOLVED",
            "detail": "The claim requests a lower bound; exact completeness is not assumed." if "≥" in outcome["expression"] else "An exact count requires a complete-value-set certificate.",
        })
    return checks


async def reason_symbolically(
    atoms: Sequence[PipelineAtom],
    evidence: Sequence[AssessmentAtomEvidence],
    documents: Sequence[RetrievalDocument],
    assessment: GroundedEvidenceAssessment,
) -> ReasoningResponse:
    excluded_by_atom = {}
    for item in assessment.obligations:
        excluded_by_atom[item.atom_id] = {
            check.span_id for check in item.scope_checks if check.status == "MISMATCH"
        }
    # Typed operand generation starts from every retrieved, scope-compatible
    # span. Assessment and symbolic execution are independent checks: a missed
    # assessed relation must not hide a source-owned operand from Python.
    selected_evidence = [
        AssessmentAtomEvidence(
            atom_id=group.atom_id,
            spans=[span for span in group.spans if span.id not in excluded_by_atom.get(group.atom_id, set())],
        )
        for group in evidence
    ]
    candidates, premises = build_candidates(atoms, selected_evidence, documents)
    validate_grounding(premises.values(), documents)
    if not candidates:
        return ReasoningResponse(executions=[], model=settings.ollama_model)
    compilable_candidates = [candidate for candidate in candidates if candidate.premise_ids]
    try:
        compiled = await compile_programs(compilable_candidates)
    except CompilerConfigurationError as error:
        raise SymbolicReasoningConfigurationError(str(error)) from error
    except CompilerProviderError as error:
        raise SymbolicReasoningProviderError(str(error)) from error
    except CompilerOutputError as error:
        raise SymbolicReasoningOutputError(str(error)) from error

    # The model proposes grounded program mappings, but it is not allowed to
    # suppress a proof that the server can validate directly from a typed
    # candidate and its source-owned operands. This domain-neutral recovery is
    # limited to operators with conservative extractors: it admits a missed
    # candidate only when Python independently reaches a decisive result.
    compiled_ids = {candidate_id for candidate_id, _premise_ids in compiled}
    candidates_by_id = {candidate.id: candidate for candidate in candidates}
    atoms_by_id = {atom.id: atom for atom in atoms}
    for candidate in compilable_candidates:
        if candidate.id in compiled_ids:
            continue
        operator = SymbolicOperator(candidate.operator)
        if operator not in {SymbolicOperator.attribute_compare, SymbolicOperator.count_distinct}:
            continue
        atom = atoms_by_id[candidate.atom_id]
        operand_ids = _validated_operand_ids(
            candidate, atom, candidate.premise_ids, premises
        )
        candidate_premises = [premises[premise_id] for premise_id in operand_ids]
        outcome = REGISTRY[operator](atom, candidate_premises, candidate.profile)
        if outcome["status"] in {SymbolicStatus.proved, SymbolicStatus.disproved}:
            compiled.append((candidate.id, operand_ids))
            compiled_ids.add(candidate.id)

    executions: list[SymbolicExecution] = []
    for index, (candidate_id, premise_ids) in enumerate(compiled, start=1):
        candidate = candidates_by_id[candidate_id]
        expanded_ids = _validated_operand_ids(
            candidate, atoms_by_id[candidate.atom_id], premise_ids, premises
        )
        certificate_hashes = {
            premises[premise_id].content_hash
            for premise_id in premise_ids
            if premises[premise_id].kind == "LIST_CERTIFICATE"
        }
        # The compiler selects a server-owned certificate. Python then attaches
        # every item covered by that exact content hash before execution; Qwen
        # never needs to repeat or alter the list contents.
        for premise_id, premise in premises.items():
            if premise.kind == "LIST_ITEM" and premise.content_hash in certificate_hashes and premise_id not in expanded_ids:
                expanded_ids.append(premise_id)
        execution_premises = [premises[premise_id] for premise_id in expanded_ids]
        operator = SymbolicOperator(candidate.operator)
        if operator in {SymbolicOperator.attribute_compare, SymbolicOperator.count_distinct}:
            outcome = REGISTRY[operator](
                atoms_by_id[candidate.atom_id], execution_premises, candidate.profile
            )
        else:
            outcome = REGISTRY[operator](atoms_by_id[candidate.atom_id], execution_premises)
        public_ids = _presentation_premise_ids(
            operator,
            atoms_by_id[candidate.atom_id],
            expanded_ids,
            premises,
            outcome["status"],
            outcome["expression"],
        )
        selected_premises = [
            _presentation_premise(premises[premise_id], premises)
            for premise_id in public_ids
        ]
        executions.append(SymbolicExecution(
            id=f"proof:{candidate.atom_id}:{operator.value.lower()}:{index}",
            atom_id=candidate.atom_id,
            operator=operator,
            profile=candidate.profile,
            status=outcome["status"],
            relation=outcome["relation"],
            premise_ids=public_ids,
            premises=selected_premises,
            expression=outcome["expression"],
            conclusion=outcome["conclusion"],
            explanation=outcome["explanation"],
            validation_warnings=outcome["validation_warnings"],
            preconditions=_execution_preconditions(candidate, execution_premises, outcome),
            program=_program(operator, public_ids, candidate_id),
        ))
    # Applicable candidates deliberately omitted by the compiler remain visible
    # as unresolved, rather than silently disappearing or becoming a model verdict.
    compiled_ids = {item[0] for item in compiled}
    for candidate in candidates:
        if candidate.id in compiled_ids:
            continue
        executions.append(SymbolicExecution(
            id=f"proof:{candidate.atom_id}:{candidate.operator.lower()}:unresolved",
            atom_id=candidate.atom_id,
            operator=SymbolicOperator(candidate.operator),
            profile=candidate.profile,
            status=SymbolicStatus.unresolved,
            relation=None,
            premise_ids=[],
            premises=[],
            expression=candidate.operator.replace("_", " ").lower(),
            conclusion="No grounded program was compiled.",
            explanation="Qwen did not map the typed candidate to sufficient server-owned premises.",
            validation_warnings=["NO_GROUNDED_PROGRAM"],
            preconditions=[
                {
                    "name": "Registered profile",
                    "status": "PASSED" if candidate.profile else "UNRESOLVED",
                    "detail": candidate.profile.replace("_", " ").lower() if candidate.profile else "No registered extraction profile was available.",
                },
                {
                    "name": "Operand alignment",
                    "status": "UNRESOLVED",
                    "detail": "The model did not map the candidate to sufficient server-owned premises.",
                },
            ],
            program=_program(SymbolicOperator(candidate.operator), [], candidate.id),
        ))
    operator_order = {operator: index for index, operator in enumerate(SymbolicOperator)}
    executions.sort(key=lambda item: (
        [atom.id for atom in atoms].index(item.atom_id),
        operator_order[item.operator],
        item.id,
    ))
    return ReasoningResponse(executions=executions, model=settings.ollama_model)
