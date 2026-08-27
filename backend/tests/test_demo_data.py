from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from verigraph_backend.demo_data import DemoDataError, load_demo_cases, load_private_bundle
from verigraph_backend.schemas import ReferenceLabel
from verigraph_backend.settings import ROOT


def _prepare_module():
    path = ROOT / "scripts" / "prepare_averitec_demo.py"
    spec = importlib.util.spec_from_file_location("prepare_averitec_demo", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_fallback_uses_multidocument_four_way_schema() -> None:
    path = ROOT / "data" / "demo_cases.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload) == 12
    assert all(set(row) == {"id", "claim", "documents", "label"} for row in payload)
    assert all(set(row["documents"][0]) == {"id", "title", "url", "text"} for row in payload)
    assert {row["label"] for row in payload} == {"SUPPORTED", "REFUTED"}
    assert len(load_demo_cases(path)) == 12


def test_checked_in_private_bundle_is_balanced_and_fully_described() -> None:
    store = load_private_bundle(ROOT / "data" / "demo" / "averitec")
    assert len(store.summaries) == 32
    assert Counter(case.label for case in store.summaries) == {
        label: 8 for label in ReferenceLabel
    }
    assert all(case.display_title for case in store.summaries)
    assert all(case.topics for case in store.summaries)


def _synthetic_rows(prepare):
    rows = [{"claim": "unused", "label": "Refuted", "questions": []} for _ in range(500)]
    for label, indices in prepare.CANDIDATES.items():
        source_label = next(key for key, value in prepare.SOURCE_LABELS.items() if value == label)
        for index in indices:
            rows[index] = {
                "claim": f"Case {index} reports a public policy change and a measurable outcome.",
                "label": source_label,
                "questions": [
                    {
                        "question": "What public policy change and measurable outcome were reported?",
                        "answers": [
                            {
                                "answer": "The public policy change produced a measurable outcome.",
                                "source_medium": "Web text",
                                "source_url": f"https://source.example/{index}/one",
                                "cached_source_url": f"https://archive.example/{index}/one",
                            },
                            {
                                "answer": "A second report confirms the public policy outcome.",
                                "source_medium": "Web text",
                                "source_url": f"https://source.example/{index}/two",
                                "cached_source_url": f"https://archive.example/{index}/two",
                            },
                        ],
                    }
                ],
            }
    return rows


def test_preparation_is_deterministic_balanced_and_uses_archives_first() -> None:
    prepare = _prepare_module()
    rows = _synthetic_rows(prepare)
    calls = []
    text = " ".join(
        ["The public policy change produced a measurable outcome in the official report."] * 30
    )

    def fetch(url):
        calls.append(url)
        return prepare.FetchResult(status="ok", text=text, title="Official report")

    cases, audits = prepare.prepare_catalog(rows, fetch, lambda _: None)
    assert len(cases) == 32
    assert Counter(case.label for case in cases) == {label: 8 for label in ReferenceLabel}
    assert all(len(case.documents) == 2 for case in cases)
    assert all("archive.example" in url for url in calls)
    assert len(audits) == 32


def test_bundle_writer_and_loader_validate_digest_balance_and_documents(tmp_path: Path) -> None:
    prepare = _prepare_module()
    rows = _synthetic_rows(prepare)
    text = " ".join(["Public policy change and measurable outcome are documented here."] * 35)
    cases, audits = prepare.prepare_catalog(
        rows,
        lambda _: prepare.FetchResult(status="ok", text=text, title="Source"),
        lambda _: None,
    )
    digest = prepare.write_bundle(cases, audits, tmp_path)
    store = load_private_bundle(tmp_path)
    assert len(store.summaries) == 32
    assert store.private is True
    assert (tmp_path / "bundle.sha256").read_text().strip() == digest

    case_path = next((tmp_path / "cases").glob("*.json"))
    case_path.write_text(case_path.read_text() + " ", encoding="utf-8")
    with pytest.raises(DemoDataError, match="digest mismatch"):
        load_private_bundle(tmp_path)


def test_preparation_rejects_allowlist_label_drift() -> None:
    prepare = _prepare_module()
    rows = _synthetic_rows(prepare)
    rows[prepare.CANDIDATES[ReferenceLabel.supported][0]]["label"] = "Refuted"
    with pytest.raises(RuntimeError, match="label drifted"):
        prepare.prepare_catalog(rows, lambda _: prepare.FetchResult(status="http_error"), lambda _: None)


def test_revision_and_candidate_configuration_are_pinned() -> None:
    prepare = _prepare_module()
    assert prepare.AVERITEC_REVISION == "7c62d1ec8df3fb560d6efe2b85fa191135636f81"
    assert all(len(indices) >= 12 for indices in prepare.CANDIDATES.values())
    assert prepare.CANDIDATES[ReferenceLabel.refuted][-3:] == (3, 4, 8)
    assert prepare.CANDIDATES[ReferenceLabel.not_enough_evidence][:5] == (15, 413, 26, 208, 435)
    assert prepare.DEFAULT_SOURCE == ROOT / "data" / "source" / "averitec-dev.json"
    assert prepare.DEFAULT_OUTPUT == ROOT / "data" / "demo" / "averitec"
