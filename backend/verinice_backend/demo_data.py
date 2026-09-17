from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import TypeAdapter, ValidationError

from .schemas import DemoCase, DemoCaseSummary, DemoCategory, DemoOrigin, DemoSourceType, ReferenceLabel
from .settings import settings


CASE_ADAPTER = TypeAdapter(DemoCase)
CASES_ADAPTER = TypeAdapter(List[DemoCase])
SUMMARIES_ADAPTER = TypeAdapter(List[DemoCaseSummary])

_ANNOTATION_LEAK_MARKERS = (
    "AVERITEC HUMAN-ANNOTATED EVIDENCE CARD",
    "These question-answer statements were written by AVeriTeC annotators",
    "RECOVERED SOURCE TEXT",
)


class DemoDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class DemoStore:
    summaries: List[DemoCaseSummary]
    cases_by_id: Dict[str, DemoCase]
    source: Path
    prepared: bool

    def case(self, case_id: str) -> Optional[DemoCase]:
        return self.cases_by_id.get(case_id)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DemoDataError(f"Could not read demo data at {path}: {error}") from error
    except ValueError as error:
        raise DemoDataError(f"Invalid JSON at {path}: {error}") from error


def _validate_unique_ids(cases: Iterable[DemoCase]) -> None:
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise DemoDataError(f"Duplicate demo case id: {case.id}")
        seen.add(case.id)


def _validate_source_only_documents(cases: Iterable[DemoCase]) -> None:
    for case in cases:
        for document in case.documents:
            if any(marker in document.text for marker in _ANNOTATION_LEAK_MARKERS):
                raise DemoDataError(
                    f"Prepared demo document {case.id}/{document.id} contains "
                    "AVeriTeC annotation-card text"
                )


def canonical_source_identity(value: str) -> str:
    parts = urlsplit(value.strip())
    host = (parts.hostname or "").casefold()
    netloc = host if parts.port is None else f"{host}:{parts.port}"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)), doseq=True)
    return urlunsplit(("https", netloc, parts.path or "/", query, ""))


def _validate_unique_sources(cases: Iterable[DemoCase]) -> None:
    for case in cases:
        identities = [canonical_source_identity(document.url) for document in case.documents]
        if len(identities) != len(set(identities)):
            raise DemoDataError(f"Prepared demo case {case.id} contains duplicate canonical sources")


def load_demo_cases(path: Path) -> List[DemoCase]:
    try:
        cases = CASES_ADAPTER.validate_python(_read_json(path))
    except ValidationError as error:
        raise DemoDataError(f"Invalid demo data at {path}: {error}") from error
    _validate_unique_ids(cases)
    _validate_source_only_documents(cases)
    _validate_unique_sources(cases)
    if not cases:
        raise DemoDataError(f"Demo data at {path} contains no cases")
    return cases


def bundle_digest(bundle_path: Path) -> str:
    files = [bundle_path / "catalog.json"] + sorted(
        (bundle_path / "cases").glob("*.json")
    )
    metadata_path = bundle_path / "metadata.json"
    if metadata_path.is_file():
        files.append(metadata_path)
    profile_path = bundle_path / "bundle.json"
    if profile_path.is_file():
        files.append(profile_path)
    if not all(path.is_file() for path in files):
        raise DemoDataError(f"Demo bundle at {bundle_path} is incomplete")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(bundle_path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _apply_bundle_metadata(cases: List[DemoCase], bundle_path: Path) -> List[DemoCase]:
    metadata_path = bundle_path / "metadata.json"
    if not metadata_path.is_file():
        return cases
    raw = _read_json(metadata_path)
    if not isinstance(raw, dict):
        raise DemoDataError(f"Demo metadata at {metadata_path} must be an object")
    unknown = sorted(set(raw) - {case.id for case in cases})
    if unknown:
        raise DemoDataError("Demo metadata references unknown cases: " + ", ".join(unknown))
    enriched: List[DemoCase] = []
    for case in cases:
        values = case.model_dump(mode="json", by_alias=True)
        item = raw.get(case.id, {})
        if not isinstance(item, dict):
            raise DemoDataError(f"Demo metadata for {case.id} must be an object")
        values.update(item)
        try:
            enriched.append(CASE_ADAPTER.validate_python(values))
        except ValidationError as error:
            raise DemoDataError(f"Invalid demo metadata for {case.id}: {error}") from error
    return enriched


def _validate_prepared_catalog(cases: List[DemoCase], bundle_path: Path) -> None:
    profile_path = bundle_path / "bundle.json"
    profile = _read_json(profile_path) if profile_path.is_file() else {"kind": "AVERITEC"}
    if profile.get("kind") == "SHOWCASE":
        policy = profile.get("policy")
        if profile.get("version") != 2 or not isinstance(policy, dict):
            raise DemoDataError("Showcase bundle must use schema version 2 and include its policy")

        def policy_count(name: str) -> int:
            value = policy.get(name)
            if not isinstance(value, int) or value < 1:
                raise DemoDataError(f"Showcase policy {name} must be a positive integer")
            return value

        expected_ids = profile.get("caseIds")
        if not isinstance(expected_ids, list) or [case.id for case in cases] != expected_ids:
            raise DemoDataError("Showcase catalog does not match its ordered case allowlist")
        if len(cases) != policy_count("caseCount"):
            raise DemoDataError("Showcase catalog does not match policy.caseCount")
        constructed = [case for case in cases if case.origin == DemoOrigin.constructed]
        if len(constructed) != policy_count("constructedCount"):
            raise DemoDataError("Showcase constructed count does not match policy")
        if any(case.category is None for case in cases):
            raise DemoDataError("Every showcase case requires a category")
        if len(cases) - len(constructed) != policy_count("averitecCount"):
            raise DemoDataError("Showcase AVeriTeC count does not match policy")
        displayed_categories = policy.get("displayedCategories")
        if not isinstance(displayed_categories, list) or len(displayed_categories) != len(set(displayed_categories)):
            raise DemoDataError("Showcase displayedCategories must be a unique list")
        valid_displayed_categories = {category.value for category in DemoCategory} | {"AVERITEC"}
        if set(displayed_categories) != valid_displayed_categories:
            raise DemoDataError("Showcase displayedCategories do not match the supported UI categories")
        displayed_counts = Counter(
            "AVERITEC" if case.origin == DemoOrigin.averitec else case.category.value
            for case in cases
        )
        expected_displayed_counts = {
            category: policy_count("casesPerDisplayedCategory")
            for category in displayed_categories
        }
        if displayed_counts != expected_displayed_counts:
            raise DemoDataError("Showcase displayed category counts do not match policy")
        raw_expected_labels = policy.get("verdictCounts")
        try:
            expected_labels = {
                ReferenceLabel(label): count for label, count in raw_expected_labels.items()
            }
        except (AttributeError, TypeError, ValueError) as error:
            raise DemoDataError("Showcase verdictCounts policy is invalid") from error
        if set(expected_labels) != set(ReferenceLabel):
            raise DemoDataError("Showcase verdictCounts must cover every reference label")
        if any(not isinstance(count, int) or count < 0 for count in expected_labels.values()):
            raise DemoDataError("Showcase verdictCounts values must be non-negative integers")
        if Counter(case.label for case in cases) != expected_labels:
            raise DemoDataError("Showcase verdict distribution does not match policy")
        source_count = policy_count("constructedSourcesPerCase")
        excerpt_policy = policy.get("excerptWords", {})
        minimum_words, maximum_words = excerpt_policy.get("minimum"), excerpt_policy.get("maximum")
        if (
            not isinstance(minimum_words, int)
            or not isinstance(maximum_words, int)
            or minimum_words < 1
            or maximum_words < minimum_words
        ):
            raise DemoDataError("Showcase excerptWords policy is invalid")
        for case in constructed:
            if len(case.documents) != source_count:
                raise DemoDataError(f"Constructed case {case.id} source count does not match policy")
            for document in case.documents:
                if document.source_type != DemoSourceType.source_excerpt:
                    raise DemoDataError(f"Constructed source {case.id}/{document.id} must be an excerpt")
                if (
                    not document.publisher
                    or not document.retrieved_at
                    or not document.source_descriptor
                    or not document.excerpt_rationale
                ):
                    raise DemoDataError(
                        f"Constructed source {case.id}/{document.id} lacks required source details"
                    )
                if not minimum_words <= len(document.text.split()) <= maximum_words:
                    raise DemoDataError(
                        f"Constructed source {case.id}/{document.id} does not satisfy excerpt policy"
                    )
                if hashlib.sha256(document.text.encode("utf-8")).hexdigest() != document.excerpt_sha256:
                    raise DemoDataError(f"Constructed source {case.id}/{document.id} has an invalid excerpt hash")
        return
    if not 20 <= len(cases) <= 32:
        raise DemoDataError("Prepared AVeriTeC catalog must contain 20 to 32 cases")
    counts = Counter(case.label for case in cases)
    missing = [
        label.value
        for label in ReferenceLabel
        if not 5 <= counts.get(label, 0) <= 8
    ]
    if missing:
        raise DemoDataError(
            "Prepared AVeriTeC catalog needs five to eight cases for every label; "
            f"invalid: {', '.join(missing)}"
        )
    for case in cases:
        if len(case.documents) < 2:
            raise DemoDataError(
                f"Prepared demo case {case.id} has fewer than two documents"
            )


def load_prepared_bundle(bundle_path: Path) -> DemoStore:
    catalog_path = bundle_path / "catalog.json"
    try:
        summaries = SUMMARIES_ADAPTER.validate_python(_read_json(catalog_path))
    except ValidationError as error:
        raise DemoDataError(f"Invalid demo catalog at {catalog_path}: {error}") from error
    cases: List[DemoCase] = []
    for summary in summaries:
        case_path = bundle_path / "cases" / f"{summary.id}.json"
        try:
            case = CASE_ADAPTER.validate_python(_read_json(case_path))
        except ValidationError as error:
            raise DemoDataError(f"Invalid demo case at {case_path}: {error}") from error
        if case.summary() != summary:
            raise DemoDataError(f"Catalog metadata does not match {case_path}")
        cases.append(case)
    cases = _apply_bundle_metadata(cases, bundle_path)
    summaries = [case.summary() for case in cases]
    _validate_unique_ids(cases)
    _validate_source_only_documents(cases)
    _validate_unique_sources(cases)
    _validate_prepared_catalog(cases, bundle_path)

    actual_digest = bundle_digest(bundle_path)
    digest_path = bundle_path / "bundle.sha256"
    recorded_digest = digest_path.read_text(encoding="utf-8").strip() if digest_path.exists() else ""
    expected_digest = settings.expected_bundle_digest or recorded_digest
    if not expected_digest:
        raise DemoDataError("Prepared demo bundle has no expected digest")
    if actual_digest != expected_digest:
        raise DemoDataError(
            f"Prepared demo bundle digest mismatch: expected {expected_digest}, got {actual_digest}"
        )
    return DemoStore(
        summaries=summaries,
        cases_by_id={case.id: case for case in cases},
        source=bundle_path,
        prepared=True,
    )


def _load_public_store(path: Path) -> DemoStore:
    cases = load_demo_cases(path)
    return DemoStore(
        summaries=[case.summary() for case in cases],
        cases_by_id={case.id: case for case in cases},
        source=path,
        prepared=False,
    )


@lru_cache(maxsize=1)
def demo_store() -> DemoStore:
    if settings.prepared_demo_bundle_path.is_dir():
        return load_prepared_bundle(settings.prepared_demo_bundle_path)
    if settings.require_prepared_catalog:
        raise DemoDataError(
            f"Required prepared demo bundle is missing at {settings.prepared_demo_bundle_path}"
        )
    return _load_public_store(settings.public_demo_data_path)


def demo_case_summaries() -> List[DemoCaseSummary]:
    return demo_store().summaries


def demo_case(case_id: str) -> Optional[DemoCase]:
    return demo_store().case(case_id)


def demo_cases() -> List[DemoCase]:
    store = demo_store()
    return [store.cases_by_id[summary.id] for summary in store.summaries]
