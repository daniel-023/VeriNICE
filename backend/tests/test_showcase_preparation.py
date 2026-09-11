from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "prepare_showcase_data", ROOT / "scripts" / "prepare_showcase_data.py"
)
assert SPEC is not None and SPEC.loader is not None
prepare = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare
SPEC.loader.exec_module(prepare)


def test_excerpt_uses_complete_contiguous_sentences() -> None:
    sentences = [
        f"Sentence {index} provides complete contextual information for the recorded source passage."
        for index in range(1, 31)
    ]
    sentences[13] = "The unique focus states that the measured outcome increased in the study population."
    text = " ".join(sentences)

    excerpt, start, end = prepare.select_excerpt(
        text,
        ["unique focus", "measured outcome increased"],
        150,
        220,
        focus_anchor="unique focus",
    )

    assert text[start:end] == excerpt
    assert excerpt.startswith("Sentence ")
    assert excerpt.endswith(".")
    assert 150 <= len(excerpt.split()) <= 220


def test_excerpt_rejects_ambiguous_focus_anchor() -> None:
    text = " ".join(
        ["Repeated focus appears in a complete sentence."] * 30
    )
    with pytest.raises(RuntimeError, match="focus anchor must occur exactly once"):
        prepare.select_excerpt(
            text,
            ["Repeated focus"],
            150,
            400,
            focus_anchor="Repeated focus",
        )


def test_text_extraction_removes_only_identifiable_boilerplate_lines() -> None:
    body = b"Menu\nSign in\nThe study reports a complete evidence sentence.\nPrivacy policy"
    extracted = prepare.extract_text(body, "text/plain", "https://example.test/source")
    assert extracted == "The study reports a complete evidence sentence."


def test_source_manifest_owns_showcase_order_focus_and_policy() -> None:
    manifest = json.loads(
        (ROOT / "data" / "manifests" / "showcase-sources.json").read_text(encoding="utf-8")
    )
    profile = json.loads(
        (ROOT / "data" / "demo" / "showcase" / "bundle.json").read_text(encoding="utf-8")
    )
    configured = [*manifest["cases"], *manifest["averitecCases"]]

    assert manifest["version"] == 2
    assert profile["version"] == 2
    assert profile["policy"] == manifest["policy"]
    assert profile["caseIds"] == [item["id"] for item in configured]
    for item in configured:
        case = json.loads(
            (ROOT / "data" / "demo" / "showcase" / "cases" / f"{item['id']}.json").read_text(
                encoding="utf-8"
            )
        )
        assert case["demoFocus"] == item["demoFocus"]
