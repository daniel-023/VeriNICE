from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from pydantic import TypeAdapter, ValidationError

from .schemas import DemoCase, DemoCaseSummary, ReferenceLabel
from .settings import settings


CASE_ADAPTER = TypeAdapter(DemoCase)
CASES_ADAPTER = TypeAdapter(List[DemoCase])
SUMMARIES_ADAPTER = TypeAdapter(List[DemoCaseSummary])


class DemoDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class DemoStore:
    summaries: List[DemoCaseSummary]
    cases_by_id: Dict[str, DemoCase]
    source: Path
    private: bool

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


def load_demo_cases(path: Path) -> List[DemoCase]:
    try:
        cases = CASES_ADAPTER.validate_python(_read_json(path))
    except ValidationError as error:
        raise DemoDataError(f"Invalid demo data at {path}: {error}") from error
    _validate_unique_ids(cases)
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


def _validate_private_catalog(cases: List[DemoCase]) -> None:
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
            "Private AVeriTeC catalog needs five to eight cases for every label; "
            f"invalid: {', '.join(missing)}"
        )
    for case in cases:
        if len(case.documents) < 2:
            raise DemoDataError(
                f"Prepared demo case {case.id} has fewer than two documents"
            )


def load_private_bundle(bundle_path: Path) -> DemoStore:
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
    _validate_private_catalog(cases)

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
        private=True,
    )


def _load_public_store(path: Path) -> DemoStore:
    cases = load_demo_cases(path)
    return DemoStore(
        summaries=[case.summary() for case in cases],
        cases_by_id={case.id: case for case in cases},
        source=path,
        private=False,
    )


@lru_cache(maxsize=1)
def demo_store() -> DemoStore:
    if settings.private_demo_bundle_path.is_dir():
        return load_private_bundle(settings.private_demo_bundle_path)
    if settings.require_private_catalog:
        raise DemoDataError(
            f"Required prepared demo bundle is missing at {settings.private_demo_bundle_path}"
        )
    return _load_public_store(settings.public_demo_data_path)


def demo_case_summaries() -> List[DemoCaseSummary]:
    return demo_store().summaries


def demo_case(case_id: str) -> Optional[DemoCase]:
    return demo_store().case(case_id)


def demo_cases() -> List[DemoCase]:
    store = demo_store()
    return [store.cases_by_id[summary.id] for summary in store.summaries]
