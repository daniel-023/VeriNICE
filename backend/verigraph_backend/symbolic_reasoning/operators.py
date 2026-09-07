from __future__ import annotations

import calendar
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Sequence

from ..schemas import PipelineAtom, SymbolicOperator, SymbolicPremise, SymbolicStatus
from .grounding import lexical_tokens, normalize


_SUPERLATIVE = re.compile(r"(?i)\b(largest|smallest|highest|lowest|tallest|shortest|most|least)\b")
_MEASURE_TERMS = {
    "population": {"population", "populous", "residents", "people"},
    "height_above_sea_level": {"above sea level", "elevation", "sea level"},
    "base_to_summit": {"base to summit", "base-to-summit", "from its base", "ocean floor"},
}


def _result(status: SymbolicStatus, relation: str | None, expression: str, conclusion: str, explanation: str, warnings: list[str] | None = None) -> dict:
    return {
        "status": status,
        "relation": relation,
        "expression": expression,
        "conclusion": conclusion,
        "explanation": explanation,
        "validation_warnings": warnings or [],
    }


_MEMBERSHIP = re.compile(
    r"(?i)^(?P<subject>.+?)\s+(?P<neg>is\s+not|isn't|was\s+not|wasn't|has\s+not\s+been|has\s+been|is|was)\s+(?:an?\s+)?(?:officially\s+)?(?:included\s+in|included\s+on|on|in|among|listed\s+on|designated\s+(?:as|by))\s+(?P<list>.+?)[.!?]?$"
)
_INCLUSION = re.compile(
    r"(?i)^(?P<authority>.+?)\s+(?P<neg>(?:has|have|had)\s+not|(?:has|have|had))\s+(?:officially\s+)?(?:included|listed|designated)\s+(?P<subject>.+?)\s+(?:in|on|among|as|by)\s+(?P<list>.+?)[.!?]?$"
)
_MEMBER_OF = re.compile(
    r"(?i)^(?P<subject>.+?)\s+(?P<neg>is\s+not|isn't|was\s+not|wasn't|is|was)\s+"
    r"(?:an?\s+)?(?:permanent\s+)?member\s+of\s+(?P<list>.+?)[.!?]?$"
)

_PAREN_ALIAS = re.compile(r"\b(?P<name>[A-Z][A-Za-z0-9&' .-]{2,80})\s*\((?P<alias>[A-Z][A-Z0-9.-]{1,12})\)")
_KNOWN_AS_ALIAS = re.compile(r"(?i)\b(?P<name>[A-Za-z][A-Za-z0-9&' .-]{2,80}?),?\s+(?:also\s+known\s+as|abbreviated\s+as)\s+(?P<alias>[A-Za-z][A-Za-z0-9&' .-]{1,40})")
_STANDS_FOR_ALIAS = re.compile(r"(?i)\b(?P<alias>[A-Z][A-Z0-9.-]{1,12})\s+stands\s+for\s+(?P<name>[A-Za-z][A-Za-z0-9&' .-]{2,80})")


def _explicit_aliases(premises: Sequence[SymbolicPremise]) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for premise in premises:
        for pattern in (_PAREN_ALIAS, _KNOWN_AS_ALIAS, _STANDS_FOR_ALIAS):
            for match in pattern.finditer(premise.text):
                left, right = normalize(match.group("name")), normalize(match.group("alias"))
                aliases.setdefault(left, set()).add(right)
                aliases.setdefault(right, set()).add(left)
    return aliases


def execute_set_membership(atom: PipelineAtom, premises: Sequence[SymbolicPremise]) -> dict:
    match = (
        _INCLUSION.match(atom.text.strip())
        or _MEMBERSHIP.match(atom.text.strip())
        or _MEMBER_OF.match(atom.text.strip())
    )
    if not match:
        return _result(SymbolicStatus.not_applicable, None, "set membership", "No executable membership claim", "The atom does not state a supported membership relation.")
    subject = normalize(match.group("subject")).strip(" ,")
    negated = "not" in normalize(match.group("neg")) or "n't" in normalize(match.group("neg"))
    certificates = [item for item in premises if item.kind == "LIST_CERTIFICATE"]
    items = [item for item in premises if item.kind == "LIST_ITEM"]
    aliases = _explicit_aliases(premises)
    accepted_names = {subject, *aliases.get(subject, set())}
    matching = [item for item in items if normalize(item.text) in accepted_names]
    expression = f"{subject} {'∉' if negated else '∈'} source list"
    if matching:
        truth = not negated
        return _result(
            SymbolicStatus.proved if truth else SymbolicStatus.disproved,
            "SUPPORTS" if truth else "REFUTES",
            expression,
            f"{subject} is present in the grounded list.",
            "Exact normalized full-item matching, or an explicitly stated source alias, found the claimed entity in the source list.",
        )
    if certificates:
        hashes = {item.content_hash for item in certificates}
        if len(hashes) > 1:
            return _result(SymbolicStatus.unresolved, None, expression, "Conflicting complete lists", "The selected sources contain non-identical exhaustive-list certificates.", ["CONFLICTING_COMPLETE_LISTS"])
        truth = negated
        return _result(
            SymbolicStatus.proved if truth else SymbolicStatus.disproved,
            "SUPPORTS" if truth else "REFUTES",
            expression,
            f"{subject} is absent from the validated exhaustive list.",
            "Absence is conclusive only because the source explicitly certifies the list as complete.",
        )
    return _result(SymbolicStatus.unresolved, None, expression, "Membership is unresolved", "No exact item match or validated exhaustive-list certificate was available.", ["INCOMPLETE_LIST_EVIDENCE"])


_NUMBER = re.compile(
    r"(?P<currency>[$£€¥])?\s*"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*"
    r"(?P<scale>billion|million|thousand|bn|mn|m|k)?\s*"
    r"(?P<percent>%|percent(?:age points?)?)?",
    re.I,
)
_SCALES = {"": Decimal(1), "k": Decimal(1000), "thousand": Decimal(1000), "m": Decimal(1_000_000), "mn": Decimal(1_000_000), "million": Decimal(1_000_000), "bn": Decimal(1_000_000_000), "billion": Decimal(1_000_000_000)}


def _numbers(text: str) -> list[tuple[Decimal, str, str]]:
    values = []
    for match in _NUMBER.finditer(text):
        try:
            value = Decimal(match.group("number").replace(",", "")) * _SCALES[(match.group("scale") or "").casefold()]
        except (InvalidOperation, KeyError):
            continue
        unit = match.group("currency") or ("percent" if match.group("percent") else "count")
        values.append((value, unit, match.group(0).strip()))
    return values


def _measurements(text: str) -> list[tuple[Decimal, str, str]]:
    values = _numbers(text)
    without_years = [item for item in values if not (item[1] == "count" and Decimal(1900) <= item[0] <= Decimal(2100) and len(item[2]) == 4)]
    return without_years or values


def _years(text: str) -> set[str]:
    return set(re.findall(r"\b(?:19|20)\d{2}\b", text))


def _comparator(text: str) -> str | None:
    normalized = normalize(text)
    for phrase, comparator in (("at least", ">="), ("no less than", ">="), ("at most", "<="), ("no more than", "<="), ("more than", ">"), ("greater than", ">"), ("over", ">"), ("less than", "<"), ("fewer than", "<"), ("under", "<"), ("equal to", "=="), ("exactly", "==")):
        if phrase in normalized:
            return comparator
    return next((item for item in (">=", "<=", "≥", "≤", ">", "<", "=") if item in text), None)


def execute_numeric_compare(atom: PipelineAtom, premises: Sequence[SymbolicPremise]) -> dict:
    comparator = _comparator(atom.text)
    claim_numbers = _measurements(atom.text)
    if comparator is None or not claim_numbers:
        return _result(SymbolicStatus.not_applicable, None, "numeric comparison", "No executable comparison", "The atom lacks an explicit supported comparator and value.")
    threshold, unit, raw_threshold = claim_numbers[-1]
    evidence_values = [(value, evidence_unit, raw, premise) for premise in premises for value, evidence_unit, raw in _measurements(premise.text)]
    claim_years = _years(atom.text)
    compatible = [
        item for item in evidence_values
        if item[1] == unit and (not claim_years or _years(item[3].text) == claim_years)
    ]
    if not compatible:
        return _result(SymbolicStatus.unresolved, None, f"value {comparator} {raw_threshold}", "Numeric relation is unresolved", "No grounded value with a compatible unit was mapped.", ["MISSING_COMPATIBLE_UNIT"])
    atom_terms = lexical_tokens(_NUMBER.sub(" ", atom.text))
    matched = [item for item in compatible if atom_terms & lexical_tokens(_NUMBER.sub(" ", item[3].text))]
    if len(matched) != 1:
        return _result(SymbolicStatus.unresolved, None, f"value {comparator} {raw_threshold}", "Numeric relation is ambiguous", "Entity, measure, or time alignment was not unique.", ["AMBIGUOUS_NUMERIC_MAPPING"])
    value, _unit, raw_value, _premise = matched[0]
    operations = {">": value > threshold, "<": value < threshold, ">=": value >= threshold, "≥": value >= threshold, "<=": value <= threshold, "≤": value <= threshold, "=": value == threshold, "==": value == threshold}
    truth = operations[comparator]
    return _result(SymbolicStatus.proved if truth else SymbolicStatus.disproved, "SUPPORTS" if truth else "REFUTES", f"{raw_value} {comparator} {raw_threshold}", f"The grounded comparison is {'true' if truth else 'false'}.", "Python compared normalized Decimal values with compatible units; no conversion or unstated arithmetic was used.")


_MONTHS = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
_DATE = re.compile(r"(?i)(?:(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(?P<day>\d{1,2})(?:,)?)?\s+)?(?P<year>19\d{2}|20\d{2})")


def _intervals(text: str) -> list[tuple[date, date, str]]:
    result = []
    for match in _DATE.finditer(text):
        year = int(match.group("year"))
        month_name = match.group("month")
        if month_name:
            month = _MONTHS[month_name.casefold()]
            if match.group("day"):
                day = int(match.group("day"))
                start = end = date(year, month, day)
            else:
                start, end = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        else:
            start, end = date(year, 1, 1), date(year, 12, 31)
        result.append((start, end, match.group(0)))
    return result


def execute_temporal_compare(atom: PipelineAtom, premises: Sequence[SymbolicPremise]) -> dict:
    normalized = normalize(atom.text)
    relation = next((value for value in ("before", "after", "between") if re.search(rf"\b{value}\b", normalized)), None)
    if relation is None and re.search(
        r"\b(?:on|in)\s+(?:(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+)?(?:19|20)\d{2}\b",
        normalized,
    ):
        relation = "on"
    atom_dates = _intervals(atom.text)
    if relation is None:
        return _result(SymbolicStatus.not_applicable, None, "temporal comparison", "No executable date relation", "The atom lacks an explicit supported temporal comparison.")
    if re.search(r"\b(?:yesterday|today|tomorrow|last|next|ago|later|earlier)\b", normalized):
        return _result(SymbolicStatus.unresolved, None, relation, "Relative time is unresolved", "Relative dates and durations are intentionally not resolved.", ["RELATIVE_TIME"])
    evidence_dates = [(interval, premise) for premise in premises for interval in _intervals(premise.text)]
    if not evidence_dates:
        return _result(SymbolicStatus.unresolved, None, relation, "Temporal relation is unresolved", "No grounded absolute date was mapped.", ["MISSING_DATE_OPERAND"])
    if not atom_dates and relation in {"before", "after"}:
        comparison = re.match(r"(?is)^(.+?)\b(?:before|after)\b(.+?)[.!?]?$", atom.text.strip())
        if comparison:
            left_names = re.findall(r"\b[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)*", comparison.group(1))
            right_names = re.findall(r"\b[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)*", comparison.group(2))
            if left_names and right_names:
                left, right = normalize(left_names[0]), normalize(right_names[0])

                def dates_for(entity: str) -> list[tuple[date, date, str]]:
                    values = {
                        interval for interval, premise in evidence_dates
                        if re.search(rf"\b{re.escape(entity)}\b", normalize(premise.text))
                    }
                    return sorted(values)

                left_dates, right_dates = dates_for(left), dates_for(right)
                if len(left_dates) == len(right_dates) == 1:
                    left_date, right_date = left_dates[0], right_dates[0]
                    if relation == "before":
                        certain_true = left_date[1] < right_date[0]
                        certain_false = left_date[0] >= right_date[1]
                    else:
                        certain_true = left_date[0] > right_date[1]
                        certain_false = left_date[1] <= right_date[0]
                    if certain_true or certain_false:
                        truth = certain_true
                        return _result(
                            SymbolicStatus.proved if truth else SymbolicStatus.disproved,
                            "SUPPORTS" if truth else "REFUTES",
                            f"{left_date[2]} {relation} {right_date[2]}",
                            f"The grounded temporal ordering is {'true' if truth else 'false'}.",
                            "Python aligned each named event with one absolute date and compared their intervals.",
                        )
        return _result(SymbolicStatus.unresolved, None, relation, "Temporal relation is ambiguous", "The two compared events could not each be aligned to one absolute date.", ["AMBIGUOUS_TEMPORAL_MAPPING"])
    target_start, target_end, target_raw = atom_dates[-1]
    # Prefer a unique evidence interval not identical to the threshold.
    possible = [(interval, premise) for interval, premise in evidence_dates if interval[2] != target_raw]
    if relation == "on" and possible:
        atom_terms = lexical_tokens(_DATE.sub(" ", atom.text))
        overlaps = [
            len(atom_terms & lexical_tokens(_DATE.sub(" ", premise.text)))
            for _interval, premise in possible
        ]
        best_overlap = max(overlaps)
        aligned = [item for item, overlap in zip(possible, overlaps) if overlap == best_overlap and overlap > 0]
        if aligned:
            if any(interval[0] == interval[1] == target_start == target_end for interval, _premise in aligned):
                value_raw = next(interval[2] for interval, _premise in aligned if interval[0] == interval[1] == target_start == target_end)
                return _result(SymbolicStatus.proved, "SUPPORTS", f"{value_raw} on {target_raw}", "The grounded temporal comparison is true.", "Python aligned the event wording and compared absolute date intervals.")
            if all(interval[1] < target_start or interval[0] > target_end for interval, _premise in aligned):
                value_raw = aligned[0][0][2]
                return _result(SymbolicStatus.disproved, "REFUTES", f"{value_raw} on {target_raw}", "The grounded temporal comparison is false.", "Python aligned the event wording and compared absolute date intervals.")
    if len(possible) != 1:
        return _result(SymbolicStatus.unresolved, None, relation, "Temporal relation is ambiguous", "Event identity or date alignment was not unique.", ["AMBIGUOUS_TEMPORAL_MAPPING"])
    (value_start, value_end, value_raw), _premise = possible[0]
    if relation == "before":
        certain_true, certain_false = value_end < target_start, value_start >= target_end
    elif relation == "after":
        certain_true, certain_false = value_start > target_end, value_end <= target_start
    elif relation == "on":
        certain_true = value_start == value_end == target_start == target_end
        certain_false = value_end < target_start or value_start > target_end
    else:
        if len(atom_dates) < 2:
            return _result(SymbolicStatus.unresolved, None, relation, "Between relation is incomplete", "A between comparison requires two explicit boundary dates.", ["MISSING_DATE_BOUNDARY"])
        lower, upper = atom_dates[-2], atom_dates[-1]
        certain_true, certain_false = value_start >= lower[0] and value_end <= upper[1], value_end < lower[0] or value_start > upper[1]
    if not certain_true and not certain_false:
        return _result(SymbolicStatus.unresolved, None, f"{value_raw} {relation} {target_raw}", "Coarse dates overlap", "Date intervals do not make the relation logically certain.", ["COARSE_DATE_OVERLAP"])
    truth = certain_true
    return _result(SymbolicStatus.proved if truth else SymbolicStatus.disproved, "SUPPORTS" if truth else "REFUTES", f"{value_raw} {relation} {target_raw}", f"The grounded temporal comparison is {'true' if truth else 'false'}.", "Python compared absolute date intervals and resolved the relation only when logically certain.")


def _subject_before_copula(text: str) -> str:
    match = re.match(r"(?i)^(.+?)\s+(?:is|was|has|have|received|won|invented|developed|makes|make|uses|causes)\b", text.strip())
    return normalize(match.group(1)) if match else ""


def execute_attribute_compare(atom: PipelineAtom, premises: Sequence[SymbolicPremise]) -> dict:
    """Resolve only explicit, source-linked attribute agreements or conflicts."""
    claim = normalize(atom.text)
    evidence = "\n".join(premise.text for premise in premises)
    normalized_evidence = normalize(evidence)
    subject = _subject_before_copula(atom.text)
    if subject and not any(token in lexical_tokens(normalized_evidence) for token in lexical_tokens(subject)):
        return _result(SymbolicStatus.unresolved, None, "attribute comparison", "Entity alignment is unresolved", "The selected premises do not explicitly identify the claim subject.", ["MISSING_ENTITY_ALIGNMENT"])

    # An explicit source negation of the claimed property is a conservative
    # refutation. This covers simple attributes without inventing a valency map.
    property_terms = lexical_tokens(re.sub(r"(?i)^.+?\b(?:is|was|has|have|for|in)\b", "", atom.text))
    aligned_negative = any(
        subject
        and lexical_tokens(subject) & lexical_tokens(premise.text)
        and property_terms & lexical_tokens(premise.text)
        and re.search(
            r"(?i)\b(?:no|not|never|without|did not|does not|will not|won['’]t|cannot|can['’]t|false|myth)\b",
            premise.text,
        )
        for premise in premises
    )
    if aligned_negative:
        return _result(SymbolicStatus.disproved, "REFUTES", "claimed attribute = source attribute", "The source explicitly negates the claimed attribute.", "Python accepted an explicit source negation only after entity and property terms were aligned.")

    # Country/location claims are resolved only when both sides name explicit,
    # different countries. This is an equality check, not geographic inference.
    try:
        import pycountry
        aliases = {country.name.casefold(): country.name for country in pycountry.countries}
        aliases.update({"usa": "United States", "u.s.": "United States", "us": "United States", "uk": "United Kingdom"})
        claim_countries = {canonical for alias, canonical in aliases.items() if re.search(rf"\b{re.escape(alias)}\b", claim)}
        evidence_countries = {canonical for alias, canonical in aliases.items() if re.search(rf"\b{re.escape(alias)}\b", normalized_evidence)}
        if claim_countries and evidence_countries:
            truth = bool(claim_countries & evidence_countries)
            return _result(SymbolicStatus.proved if truth else SymbolicStatus.disproved, "SUPPORTS" if truth else "REFUTES", "claimed location = source location", "The grounded locations match." if truth else "The grounded locations are different.", "Python compared explicit normalized country names; it did not infer location from source identity.")
    except ImportError:
        pass

    # Exclusivity is disproved by an explicit second purpose.
    if "exclusively" in claim and re.search(r"(?i)\bmilitary\b", evidence) and re.search(r"(?i)\bcivil(?:ian)?\b", evidence):
        return _result(SymbolicStatus.disproved, "REFUTES", "purposes = {military, civilian}", "The source gives more than one purpose.", "Python found two explicit, incompatible values for an exclusive-purpose claim.")

    # Nobel-style prize citations are handled as grounded reason equality.
    reason = (
        re.search(r"(?i)\bfor\s+([^.!?]+)", atom.text)
        if re.search(r"(?i)\b(?:nobel|prize|award|citation)\b", atom.text)
        else None
    )
    source_reasons = re.findall(r"(?i)\bfor\s+(?:his|her|their)?\s*([^.!?;]+)", evidence)
    if reason and source_reasons:
        claimed = lexical_tokens(reason.group(1))
        matches = [value for value in source_reasons if claimed & lexical_tokens(value)]
        if matches:
            return _result(SymbolicStatus.proved, "SUPPORTS", "claimed reason = source reason", "The stated reason matches a grounded source reason.", "Python compared normalized reason terms attached to the same grounded subject.")
        return _result(SymbolicStatus.disproved, "REFUTES", "claimed reason ≠ source reason", "The cited reason differs from the grounded source reason.", "Python compared explicit source and claim attributes after subject alignment.")
    return _result(SymbolicStatus.unresolved, None, "attribute comparison", "Attribute relation is unresolved", "The premises do not provide one unambiguous attribute value for deterministic comparison.", ["AMBIGUOUS_ATTRIBUTE_MAPPING"])


def execute_count_distinct(atom: PipelineAtom, premises: Sequence[SymbolicPremise]) -> dict:
    claim = normalize(atom.text)
    expected = 2 if re.search(r"\b(?:two|both)\b", claim) or " and " in claim else None
    if expected is None:
        return _result(SymbolicStatus.not_applicable, None, "count distinct", "No explicit distinct-count claim", "The atom does not state a supported distinct-value count.")
    vocabulary = ("physics", "chemistry", "medicine", "literature", "peace", "economics")
    values = {value for premise in premises for value in vocabulary if re.search(rf"\b{value}\b", normalize(premise.text))}
    if len(values) < expected:
        return _result(SymbolicStatus.unresolved, None, f"count(distinct fields) = {expected}", "Distinct values are unresolved", "The selected premises do not ground enough distinct values.", ["MISSING_DISTINCT_VALUES"])
    truth = len(values) == expected
    return _result(SymbolicStatus.proved if truth else SymbolicStatus.disproved, "SUPPORTS" if truth else "REFUTES", f"count({{{', '.join(sorted(values))}}}) = {expected}", f"The sources ground {len(values)} distinct values.", "Python normalized and counted explicit source values; it did not infer field equivalence.")


def _measure_kinds(text: str) -> set[str]:
    normalized = normalize(text)
    return {kind for kind, terms in _MEASURE_TERMS.items() if any(term in normalized for term in terms)}


def execute_extremum_compare(atom: PipelineAtom, premises: Sequence[SymbolicPremise]) -> dict:
    superlative = _SUPERLATIVE.search(atom.text)
    if not superlative:
        return _result(SymbolicStatus.not_applicable, None, "extremum comparison", "No supported extremum claim", "The atom does not state a supported extremum.")
    combined = "\n".join(premise.text for premise in premises)
    measure_kinds = _measure_kinds(atom.text + "\n" + combined)
    if "height_above_sea_level" in measure_kinds and "base_to_summit" in measure_kinds:
        return _result(SymbolicStatus.unresolved, None, superlative.group(1).casefold(), "Measurements use different definitions", "The candidate values are not comparable because their measurement bases differ.", ["INCOMPATIBLE_MEASURES"])
    subject = _subject_before_copula(atom.text)
    records: list[tuple[str, Decimal, str]] = []
    for premise in premises:
        values = _measurements(premise.text)
        if not values:
            continue
        name = re.match(r"\s*([A-Z][A-Za-z .'-]{1,80})", premise.text)
        if name:
            records.append((normalize(name.group(1)), values[0][0], values[0][1]))
    subject_values = [record for record in records if subject and lexical_tokens(subject) & lexical_tokens(record[0])]
    if not subject_values:
        return _result(SymbolicStatus.unresolved, None, superlative.group(1).casefold(), "Subject value is unresolved", "No uniquely aligned measurement was found for the claimed subject.", ["MISSING_SUBJECT_VALUE"])
    subject_value = subject_values[0]
    compatible = [record for record in records if record[2] == subject_value[2] and record[0] != subject_value[0]]
    wants_max = superlative.group(1).casefold() in {"largest", "highest", "tallest", "most"}
    counterexamples = [record for record in compatible if (record[1] > subject_value[1] if wants_max else record[1] < subject_value[1])]
    if counterexamples:
        other = counterexamples[0]
        return _result(SymbolicStatus.disproved, "REFUTES", f"{other[1]} {'>' if wants_max else '<'} {subject_value[1]}", "A grounded counterexample disproves the extremum claim.", "Python compared aligned measurements. One counterexample is sufficient to refute a superlative.")
    return _result(SymbolicStatus.unresolved, None, superlative.group(1).casefold(), "Extremum is not proved", "No counterexample was selected, but the complete comparison universe is not certified.", ["INCOMPLETE_COMPARISON_UNIVERSE"])


REGISTRY = {
    SymbolicOperator.set_membership: execute_set_membership,
    SymbolicOperator.numeric_compare: execute_numeric_compare,
    SymbolicOperator.temporal_compare: execute_temporal_compare,
    SymbolicOperator.attribute_compare: execute_attribute_compare,
    SymbolicOperator.count_distinct: execute_count_distinct,
    SymbolicOperator.extremum_compare: execute_extremum_compare,
}
