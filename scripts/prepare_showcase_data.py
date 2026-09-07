#!/usr/bin/env python3
"""Prepare the source-grounded 18-case VeriTrace showcase.

Network access is restricted to this offline preparation command. Runtime code
loads only the immutable bundle produced here.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
import trafilatura


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "manifests" / "showcase-sources.json"
DEFAULT_AVERITEC = ROOT / "data" / "demo" / "averitec"
DEFAULT_OUTPUT = ROOT / "data" / "demo" / "showcase"
DEFAULT_CACHE = ROOT / "data" / "cache" / "showcase_sources"
CURATED_AVERITEC = (
    ("averitec-dev-0146", "CURRENT_AFFAIRS"),
    ("averitec-dev-0392", "GEOGRAPHY"),
    ("averitec-dev-0142", "SCIENCE"),
)

AVERITEC_FOCUS = {
    "averitec-dev-0142": "INSUFFICIENT_EVIDENCE",
    "averitec-dev-0146": "DIRECT_EVIDENCE",
    "averitec-dev-0392": "DECOMPOSITION",
}

CONSTRUCTED_FOCUS = {
    "showcase-science-brain-10-percent": "DIRECT_EVIDENCE",
    "showcase-science-shaving": "DECOMPOSITION",
    "showcase-science-lightning": "DIRECT_EVIDENCE",
    "showcase-history-einstein": "ATTRIBUTE_COMPARISON",
    "showcase-history-curie": "DISTINCT_VALUE_COUNT",
    "showcase-history-viking-helmet": "ATTRIBUTE_COMPARISON",
    "showcase-geography-canberra": "EXTREMUM",
    "showcase-geography-everest": "EXTREMUM",
    "showcase-geography-eiffel": "ATTRIBUTE_COMPARISON",
    "showcase-technology-iphone": "TEMPORAL_COMPARISON",
    "showcase-technology-web": "DIRECT_EVIDENCE",
    "showcase-technology-gps": "ATTRIBUTE_COMPARISON",
    "showcase-current-nato": "TEMPORAL_COMPARISON",
    "showcase-current-unsc": "SET_MEMBERSHIP",
    "showcase-current-who": "DECOMPOSITION",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def bundle_digest(bundle: Path) -> str:
    files = [bundle / "catalog.json", *sorted((bundle / "cases").glob("*.json")), bundle / "metadata.json", bundle / "bundle.json"]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(bundle).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def fetch_source(source: dict[str, Any], cache: Path, refresh: bool) -> tuple[bytes, str, str, str]:
    key = hashlib.sha256(source["url"].encode()).hexdigest()
    body_path, meta_path = cache / f"{key}.bin", cache / f"{key}.json"
    if body_path.is_file() and meta_path.is_file() and not refresh:
        metadata = read_json(meta_path)
        return (
            body_path.read_bytes(), metadata["contentType"],
            metadata["retrievedAt"], metadata.get("method", "CACHE"),
        )
    method = "DIRECT"
    try:
        response = requests.get(
            source["url"], timeout=45,
            headers={"User-Agent": "Mozilla/5.0 (compatible; VeriTrace academic demo preparation/1.0)"},
        )
        use_reader = bool(source.get("forceReader")) or response.status_code >= 400
    except requests.RequestException:
        use_reader = True
        response = None
    if use_reader:
        # Some authoritative sites block non-browser clients. Jina's reader is
        # an offline-preparation fallback only; attribution remains the
        # canonical publisher URL and runtime never contacts either service.
        response = requests.get(f"https://r.jina.ai/http://{source['url'].split('://', 1)[1]}", timeout=90)
        method = "JINA_READER"
    assert response is not None
    response.raise_for_status()
    content_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    cache.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(response.content)
    retrieved_at = date.today().isoformat()
    write_json(meta_path, {"url": source["url"], "contentType": content_type, "retrievedAt": retrieved_at, "method": method})
    return response.content, content_type, retrieved_at, method


def extract_text(body: bytes, content_type: str, url: str) -> str:
    if content_type.startswith("text/plain") or content_type.startswith("text/markdown"):
        raw = body.decode("utf-8", errors="replace")
        raw = re.sub(r"(?m)^Markdown Content:\s*$", "", raw)
        raw = re.sub(r"(?m)^Title:.*$|^URL Source:.*$|^Published Time:.*$", "", raw)
        raw = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", raw)
        raw = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", raw)
    elif "pdf" in content_type or urlsplit(url).path.casefold().endswith(".pdf"):
        from pypdf import PdfReader
        raw = "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(body)).pages)
    else:
        raw = trafilatura.extract(
            body,
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_recall=True,
            output_format="txt",
        ) or ""
    return re.sub(r"[ \t]+", " ", raw.replace("\r\n", "\n").replace("\r", "\n")).strip()


def select_excerpt(text: str, anchors: list[str], minimum: int, maximum: int) -> tuple[str, int, int]:
    words = list(re.finditer(r"\S+", text))
    if len(words) < minimum:
        raise RuntimeError(f"source contains only {len(words)} extracted words")
    target = min(maximum, max(minimum, 240))
    normalized = text.casefold()
    anchor_positions = [normalized.find(anchor.casefold()) for anchor in anchors]
    if any(position < 0 for position in anchor_positions):
        missing = [anchor for anchor, position in zip(anchors, anchor_positions) if position < 0]
        raise RuntimeError("required anchors were not extracted: " + ", ".join(missing))
    first_anchor = min(anchor_positions)
    first_anchor_word = min(
        range(len(words)), key=lambda index: abs(words[index].start() - first_anchor)
    )
    # Keep a short lead-in for readability without allowing navigation or form
    # boilerplate far above the cited passage to dominate the excerpt.
    start_word = max(0, min(first_anchor_word - 30, len(words) - target))
    end_word = min(len(words), start_word + target)
    start, end = words[start_word].start(), words[end_word - 1].end()
    excerpt = text[start:end]
    if not all(anchor.casefold() in excerpt.casefold() for anchor in anchors):
        first = min(anchor_positions)
        last = max(position + len(anchor) for position, anchor in zip(anchor_positions, anchors))
        first_word = max(0, next(index for index, word in enumerate(words) if word.end() >= first) - 30)
        last_word = next((index for index, word in enumerate(words) if word.start() > last), len(words))
        if last_word - first_word > maximum:
            raise RuntimeError("anchors cannot fit in one 150-400 word contiguous excerpt")
        end_word = min(len(words), max(first_word + minimum, last_word + 30))
        start_word = max(0, end_word - maximum)
        start, end = words[start_word].start(), words[end_word - 1].end()
        excerpt = text[start:end]
    count = len(excerpt.split())
    if not minimum <= count <= maximum:
        raise RuntimeError(f"selected excerpt has {count} words")
    return excerpt, start, end


def summary(case: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in case.items() if key != "documents"} | {
        "documents": [{key: value for key, value in document.items() if key != "text"} for document in case["documents"]]
    }


def prepare_constructed(config: dict[str, Any], cache: Path, refresh: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    minimum, maximum = config["excerptWords"]["minimum"], config["excerptWords"]["maximum"]
    cases, audit = [], []
    for case_config in config["cases"]:
        documents = []
        for index, source in enumerate(case_config["sources"], start=1):
            if not source.get("redistributionApproved"):
                raise RuntimeError(f"source has not been approved for excerpt use: {source['url']}")
            body, content_type, retrieved_at, method = fetch_source(source, cache, refresh)
            full_text = extract_text(body, content_type, source["url"])
            try:
                excerpt, start, end = select_excerpt(full_text, source["anchors"], minimum, maximum)
            except RuntimeError as error:
                raise RuntimeError(f"{case_config['id']} / {source['url']}: {error}") from error
            source_hash, excerpt_hash = digest_text(full_text), digest_text(excerpt)
            document_id = f"doc-{hashlib.sha256(source['url'].encode()).hexdigest()[:12]}"
            documents.append({
                "id": document_id,
                "title": source["title"],
                "url": source["url"],
                "layout": "PROSE",
                "publisher": source["publisher"],
                "retrievedAt": retrieved_at,
                "sourceType": "SOURCE_EXCERPT",
                "excerptSha256": excerpt_hash,
                "sourceSha256": source_hash,
                "text": excerpt,
            })
            audit.append({
                "caseId": case_config["id"], "documentId": document_id,
                "url": source["url"], "publisher": source["publisher"],
                "retrievedAt": retrieved_at, "contentType": content_type,
                "method": method,
                "sourceWords": len(full_text.split()), "excerptWords": len(excerpt.split()),
                "sourceStart": start, "sourceEnd": end,
                "sourceSha256": source_hash, "excerptSha256": excerpt_hash,
                "redistributionApproved": True,
            })
        cases.append({
            "id": case_config["id"], "claim": case_config["claim"],
            "documents": documents, "label": case_config["label"],
            "displayTitle": case_config["displayTitle"], "topics": [], "challenges": [],
            "featured": False, "origin": "CONSTRUCTED", "category": case_config["category"],
            "demoFocus": CONSTRUCTED_FOCUS[case_config["id"]],
        })
    return cases, audit


def curated_averitec(bundle: Path) -> list[dict[str, Any]]:
    metadata = read_json(bundle / "metadata.json")
    cases = []
    for case_id, category in CURATED_AVERITEC:
        case = read_json(bundle / "cases" / f"{case_id}.json")
        case.update(metadata.get(case_id, {}))
        case.update({
            "origin": "AVERITEC", "category": category,
            "featured": False, "demoFocus": AVERITEC_FOCUS[case_id],
        })
        for document in case["documents"]:
            document.update({
                "publisher": urlsplit(document["url"]).hostname or "Source publisher",
                "sourceType": "FULL_SOURCE",
                "sourceSha256": digest_text(document["text"]),
                # Keep the stored payload identical to the API's explicit-null
                # serialization so walkthrough input digests are reproducible.
                "retrievedAt": document.get("retrievedAt"),
                "excerptSha256": document.get("excerptSha256"),
            })
        cases.append(case)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the VeriTrace source-grounded showcase")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--averitec", type=Path, default=DEFAULT_AVERITEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    config = read_json(args.config)
    constructed, audit = prepare_constructed(config, args.cache, args.refresh)
    cases = [*constructed, *curated_averitec(args.averitec)]
    if len(cases) != 18:
        raise RuntimeError("showcase must contain 18 cases")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "cases").mkdir(exist_ok=True)
    expected_files = {f"{case['id']}.json" for case in cases}
    for stale_case in (args.output / "cases").glob("*.json"):
        if stale_case.name not in expected_files:
            stale_case.unlink()
    for case in cases:
        write_json(args.output / "cases" / f"{case['id']}.json", case)
    write_json(args.output / "catalog.json", [summary(case) for case in cases])
    write_json(args.output / "metadata.json", {})
    write_json(args.output / "bundle.json", {"kind": "SHOWCASE", "version": 1, "caseIds": [case["id"] for case in cases]})
    write_json(args.output / "fetch-audit.json", audit)
    digest = bundle_digest(args.output)
    (args.output / "bundle.sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"Prepared {len(cases)} showcase cases at {args.output} ({digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
