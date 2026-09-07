from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from types import SimpleNamespace
from collections import Counter
from pathlib import Path

import pytest

from verigraph_backend.demo_data import DemoDataError, load_demo_cases, load_private_bundle
from verigraph_backend.schemas import DemoCategory, DemoOrigin, ReferenceLabel
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
    assert all(set(row["documents"][0]) >= {"id", "title", "url", "text"} for row in payload)
    assert {row["label"] for row in payload} == {"SUPPORTED", "REFUTED"}
    assert len(load_demo_cases(path)) == 12


def test_checked_in_private_bundle_is_balanced_and_fully_described() -> None:
    bundle = ROOT / "data" / "demo" / "averitec"
    store = load_private_bundle(bundle)
    assert len(store.summaries) == 32
    assert Counter(case.label for case in store.summaries) == {
        label: 8 for label in ReferenceLabel
    }
    assert all(case.display_title for case in store.summaries)
    assert all(case.topics for case in store.summaries)

    audit_by_case = {
        item["caseId"]: item
        for item in json.loads((bundle / "fetch-audit.json").read_text(encoding="utf-8"))
        if item.get("accepted")
    }
    documents = [document for case in store.cases_by_id.values() for document in case.documents]
    assert len(documents) == 77
    ndf = store.cases_by_id["averitec-dev-0034"]
    assert len(ndf.documents) == 4
    prepare = _prepare_module()
    assert len({prepare._source_identity_url(document.url) for document in ndf.documents}) == 4
    for case in store.cases_by_id.values():
        source_by_url = {
            source["sourceUrl"]: source
            for source in audit_by_case[case.id]["sources"]
            if source.get("accepted")
        }
        for document in case.documents:
            assert len(document.text.split()) >= 175
            assert (
                hashlib.sha256(document.text.encode("utf-8")).hexdigest()
                == source_by_url[document.url]["sha256"]
            )
            assert "AVERITEC HUMAN-ANNOTATED EVIDENCE CARD" not in document.text
            assert "RECOVERED SOURCE TEXT" not in document.text


def test_showcase_bundle_has_fifteen_constructed_and_three_averitec_cases() -> None:
    bundle = ROOT / "data" / "demo" / "showcase"
    store = load_private_bundle(bundle)
    assert len(store.summaries) == 18
    assert sum(case.origin == DemoOrigin.constructed for case in store.summaries) == 15
    assert sum(case.origin == DemoOrigin.averitec for case in store.summaries) == 3
    assert {case.category for case in store.summaries} == set(DemoCategory)
    assert {case.id for case in store.summaries if case.origin == DemoOrigin.averitec} == {
        "averitec-dev-0142", "averitec-dev-0146", "averitec-dev-0392",
    }
    assert all(case.demo_focus is not None for case in store.summaries)
    assert not any(case.featured for case in store.summaries)
    for case in store.cases_by_id.values():
        if case.origin != DemoOrigin.constructed:
            continue
        assert len(case.documents) == 2
        assert len({document.url for document in case.documents}) == 2
        for document in case.documents:
            assert 150 <= len(document.text.split()) <= 400
            assert document.publisher and document.retrieved_at
            assert hashlib.sha256(document.text.encode()).hexdigest() == document.excerpt_sha256
    assert store.cases_by_id["showcase-history-curie"].claim == (
        "Marie Curie won Nobel Prizes in two different scientific fields."
    )


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
    assert all(
        tuple(prepare.CANDIDATES[label][:8]) == tuple(published)
        for label, published in prepare.PUBLISHED_CASES.items()
    )
    assert prepare.PUBLISHED_CASES[ReferenceLabel.refuted][-3:] == (3, 4, 8)
    assert prepare.PUBLISHED_CASES[ReferenceLabel.not_enough_evidence][:5] == (15, 413, 26, 208, 435)
    assert prepare.DEFAULT_SOURCE == ROOT / "data" / "source" / "averitec-dev.json"
    assert prepare.DEFAULT_OUTPUT == ROOT / "data" / "demo" / "averitec"


def test_source_groups_include_pdf_evidence_but_not_unextractable_media() -> None:
    prepare = _prepare_module()
    row = {
        "questions": [
            {
                "question": "Which organizations are on the official list?",
                "answers": [
                    {
                        "answer": "The target is not on the list.",
                        "source_medium": "PDF",
                        "source_url": "https://authority.example/list.pdf",
                    },
                    {
                        "answer": "Spoken only in a video.",
                        "source_medium": "Video",
                        "source_url": "https://video.example/watch",
                    },
                ],
            }
        ]
    }

    groups = prepare._source_groups(row)

    assert [group["source_url"] for group in groups] == [
        "https://authority.example/list.pdf"
    ]
    assert groups[0]["evidence_text"] == [
        "Which organizations are on the official list? The target is not on the list."
    ]


def test_source_groups_deduplicate_percent_encoded_query_values() -> None:
    prepare = _prepare_module()
    row = {"questions": [{"question": "Listed?", "answers": [
        {"answer": "Yes", "source_medium": "Web text", "source_url": "https://eur-lex.europa.eu/legal-content/en/TXT/?uri=CELEX:32020D1132"},
        {"answer": "Yes", "source_medium": "Web text", "source_url": "https://EUR-LEX.EUROPA.EU/legal-content/en/TXT/?uri=CELEX%3A32020D1132"},
    ]}]}
    groups = prepare._source_groups(row)
    assert len(groups) == 1
    assert groups[0]["source_url"].endswith("uri=CELEX:32020D1132")


def test_prepared_documents_use_source_text_without_annotation_leakage() -> None:
    prepare = _prepare_module()
    row = {
        "claim": "The program improved the measured outcome.",
        "label": "Supported",
        "justification": "This gold explanation must not enter the evidence.",
        "questions": [
            {
                "question": "Did the program improve the measured outcome?",
                "answers": [
                    {
                        "answer": "The measured outcome improved after the program.",
                        "source_medium": "Web text",
                        "source_url": "https://source.example/program",
                    },
                    {
                        "answer": "A second source reported the same improvement.",
                        "source_medium": "Web text",
                        "source_url": "https://source.example/second",
                    },
                ],
            }
        ],
    }
    source_text = " ".join(
        ["The program and its measured outcome are described in this report."] * 30
    )

    case, audit = prepare.prepare_case(
        7,
        row,
        lambda _: prepare.FetchResult(status="ok", text=source_text, title="Report"),
        lambda _: None,
    )

    assert case is not None
    assert audit["accepted"] is True
    assert all(document.text == source_text for document in case.documents)
    combined = "\n".join(document.text for document in case.documents)
    assert "Did the program improve" not in combined
    assert "The measured outcome improved" not in combined
    assert "This gold explanation" not in combined
    assert "SUPPORTED" not in combined
    assert all("annotatedEvidenceSha256" not in source for source in audit["sources"])


def test_private_bundle_rejects_annotation_card_text(tmp_path: Path) -> None:
    prepare = _prepare_module()
    rows = _synthetic_rows(prepare)
    source_text = " ".join(
        ["Public policy change and measurable outcome are documented here."] * 35
    )
    cases, audits = prepare.prepare_catalog(
        rows,
        lambda _: prepare.FetchResult(status="ok", text=source_text, title="Source"),
        lambda _: None,
    )
    prepare.write_bundle(cases, audits, tmp_path)
    case_path = next((tmp_path / "cases").glob("*.json"))
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload["documents"][0]["text"] = (
        "AVERITEC HUMAN-ANNOTATED EVIDENCE CARD\n" + payload["documents"][0]["text"]
    )
    case_path.write_text(json.dumps(payload), encoding="utf-8")
    prepare.write_bundle(
        [prepare.DemoCase.model_validate(json.loads(path.read_text(encoding="utf-8")))
         for path in sorted((tmp_path / "cases").glob("*.json"))],
        audits,
        tmp_path,
    )

    with pytest.raises(DemoDataError, match="annotation-card text"):
        load_private_bundle(tmp_path)


def test_pdf_extraction_uses_selectable_text_and_preserves_metadata_title(monkeypatch) -> None:
    prepare = _prepare_module()

    class FakeReader:
        metadata = {"/Title": "Official designated entities"}
        pages = [
            SimpleNamespace(extract_text=lambda: "Entity One\nEntity Two"),
            SimpleNamespace(extract_text=lambda: "Entity Three"),
        ]

        def __init__(self, stream, strict=False):
            assert stream.read().startswith(b"%PDF-")
            assert strict is False

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))

    result = prepare.extract_pdf(b"%PDF-synthetic", "https://authority.example/list.pdf")

    assert result.status == "ok"
    assert result.title == "Official designated entities"
    assert "Entity One" in result.text
    assert "Entity Three" in result.text


def test_pdf_extraction_reflows_unambiguous_word_per_line_text(monkeypatch) -> None:
    prepare = _prepare_module()
    extracted = "\n".join(f"word{index}" for index in range(120))

    class FakeReader:
        metadata = {"/Title": "Word-per-line PDF"}
        pages = [SimpleNamespace(extract_text=lambda: extracted)]

        def __init__(self, stream, strict=False):
            pass

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))

    result = prepare.extract_pdf(b"%PDF-word-lines", "https://authority.example/report.pdf")

    assert result.status == "ok"
    assert result.text == " ".join(f"word{index}" for index in range(120))


def test_word_per_line_reflow_preserves_normal_lists() -> None:
    prepare = _prepare_module()
    source = "Complete list\n\nAlpha\nBeta\nGamma"

    assert prepare._reflow_word_per_line_text(source) == source


def test_pdf_extraction_rejects_image_only_documents(monkeypatch) -> None:
    prepare = _prepare_module()

    class FakeReader:
        metadata = None
        pages = [SimpleNamespace(extract_text=lambda: "")]

        def __init__(self, stream, strict=False):
            pass

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))

    result = prepare.extract_pdf(b"%PDF-image", "https://authority.example/image.pdf")

    assert result.status == "extraction_failed"
    assert "No selectable PDF text" in result.error


def test_pdf_support_retries_legacy_html_only_cache_entry(tmp_path: Path) -> None:
    prepare = _prepare_module()
    fetcher = prepare.HttpFetcher(tmp_path, offline=True)
    url = "https://authority.example/list.pdf"
    fetcher._save_cache(
        url,
        prepare.FetchResult(
            status="invalid_content_type",
            error="Expected HTML, got application/pdf",
        ),
    )

    assert fetcher._load_cache(url) is None


def test_oversized_structured_pdf_compacts_every_named_target(monkeypatch) -> None:
    prepare = _prepare_module()
    targets = [f"TARGET {index:04d} WITH A DISTINCT OFFICIAL NAME" for index in range(40)]
    repeated_notes = "Administrative details " * 12_000
    extracted = repeated_notes + "\n" + "\n".join(
        f"Name 6:\n{target}\n1:\nn/a\n2:\nn/a\n3:\nn/a\n4:\nn/a\n5:\nn/a."
        for target in targets
    )
    assert len(extracted) > prepare.MAX_DOCUMENT_CHARACTERS

    class FakeReader:
        metadata = {"/Title": "Complete official list"}
        pages = [SimpleNamespace(extract_text=lambda: extracted)]

        def __init__(self, stream, strict=False):
            pass

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))

    result = prepare.extract_pdf(b"%PDF-list", "https://authority.example/list.pdf")

    assert result.status == "ok"
    assert len(result.text) <= prepare.MAX_DOCUMENT_CHARACTERS
    assert "40 unique targets" in result.text
    assert all(target in result.text for target in targets)
    assert "Administrative details" not in result.text


def test_legacy_oversized_pdf_cache_is_compacted_on_load(tmp_path: Path) -> None:
    prepare = _prepare_module()
    targets = [f"TARGET {index:04d}" for index in range(25)]
    extracted = "Administrative details " * 12_000 + "\n" + "\n".join(
        f"Name 6:\n{target}\n1:\nn/a\n2:\nn/a\n3:\nn/a\n4:\nn/a\n5:\nn/a."
        for target in targets
    )
    fetcher = prepare.HttpFetcher(tmp_path, offline=True)
    url = "https://authority.example/legacy-list.pdf"
    fetcher._save_cache(
        url,
        prepare.FetchResult(
            status="ok",
            text=extracted,
            title="Legacy official list",
            method="http_pdf",
        ),
    )

    result = fetcher._load_cache(url)

    assert result is not None
    assert result.method == "cached_pdf_compaction"
    assert all(target in result.text for target in targets)
    assert len(result.text) <= prepare.MAX_DOCUMENT_CHARACTERS


def test_wayback_resolution_is_reused_offline(tmp_path: Path) -> None:
    prepare = _prepare_module()
    source = "https://publisher.example/article"
    snapshot = "https://web.archive.org/web/20200101000000/https://publisher.example/article"
    (tmp_path / "wayback-resolutions.json").write_text(
        json.dumps({source: snapshot}), encoding="utf-8"
    )

    fetcher = prepare.HttpFetcher(tmp_path, offline=True)

    assert fetcher.wayback_url(source) == snapshot
