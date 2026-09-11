#!/usr/bin/env python3
"""Prepare the source-grounded 18-case VeriNICE showcase.

Network access is restricted to this offline preparation command. Runtime code
loads only the immutable bundle produced here.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
import pysbd
import trafilatura


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "manifests" / "showcase-sources.json"
DEFAULT_AVERITEC = ROOT / "data" / "demo" / "averitec"
DEFAULT_OUTPUT = ROOT / "data" / "demo" / "showcase"
DEFAULT_CACHE = ROOT / "data" / "cache" / "showcase_sources"
REFERENCE_LABELS = {
    "SUPPORTED", "REFUTED", "NOT_ENOUGH_EVIDENCE", "CONFLICTING_EVIDENCE",
}
EXCERPT_RATIONALE = (
    "This contiguous, sentence-complete passage contains the claim-relevant evidence "
    "and nearby context while excluding unrelated page material. Follow the source link "
    "to inspect the complete publisher page."
)

BOILERPLATE_LINES = re.compile(
    r"^(?:menu|search|sign in|log in|subscribe|donate|contact us|skip to (?:main )?content|"
    r"accept(?: all)? cookies|cookie settings|privacy policy|pubmed disclaimer|"
    r"terms of (?:use|service))$",
    re.IGNORECASE,
)
BOILERPLATE_PREFIXES = re.compile(
    r"^(?:the password must be|click the button to return|create an account|"
    r"create a new password|didn.t receive a code|send new code|no account|"
    r"forgot your password|check your inbox|we have sent a verification code|"
    r"enter the code|from now on you can download|if you would also like to subscribe|"
    r"reset password|verification code|"
    r"sign in to|log in to|enable javascript|your browser does not support)",
    re.IGNORECASE,
)


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
            source["url"], timeout=source.get("timeoutSeconds", 45),
            headers={"User-Agent": "Mozilla/5.0 (compatible; VeriNICE academic demo preparation/1.0)"},
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
        pages = []
        for page in PdfReader(io.BytesIO(body)).pages:
            page_text = page.extract_text() or ""
            # PDF text layers commonly encode visual line wrapping as hard
            # newlines. Reflow those lines before sentence segmentation so a
            # rendered line cannot become a misleading evidence boundary.
            page_text = re.sub(r"(?<=\w)-\s*\n\s*(?=[a-z])", "", page_text)
            page_text = re.sub(r"(?<!\n)\n(?!\n)", " ", page_text)
            pages.append(page_text)
        raw = "\n\n".join(pages)
    else:
        raw = trafilatura.extract(
            body,
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_recall=True,
            output_format="txt",
        ) or ""
    normalized = re.sub(r"[ \t]+", " ", raw.replace("\r\n", "\n").replace("\r", "\n"))
    lines = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if stripped and (
            (len(stripped.split()) <= 12 and BOILERPLATE_LINES.fullmatch(stripped))
            or BOILERPLATE_PREFIXES.match(stripped)
        ):
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _content_units(text: str) -> list[tuple[int, int]]:
    """Return exact sentence or structured-line spans without rewriting text."""
    segmenter = pysbd.Segmenter(language="en", clean=False, char_span=True)
    units: list[tuple[int, int]] = []
    for line_match in re.finditer(r"[^\n]+", text):
        raw_line = line_match.group(0)
        leading = len(raw_line) - len(raw_line.lstrip())
        line = raw_line.strip()
        if not line:
            continue
        line_start = line_match.start() + leading
        spans = segmenter.segment(line)
        if not spans:
            units.append((line_start, line_start + len(line)))
            continue
        for span in spans:
            start, end = line_start + span.start, line_start + span.end
            if start < 0 or end <= start or text[start:end] != span.sent:
                raise RuntimeError("sentence segmentation did not preserve exact source offsets")
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            units.append((start, end))
    if not units:
        raise RuntimeError("source contains no sentence or structured-line units")
    return units


def _occurrences(text: str, needle: str) -> list[int]:
    normalized, query = text.casefold(), needle.casefold()
    return [match.start() for match in re.finditer(re.escape(query), normalized)]


def select_excerpt(
    text: str,
    anchors: list[str],
    minimum: int,
    maximum: int,
    *,
    focus_anchor: str | None = None,
) -> tuple[str, int, int]:
    if len(text.split()) < minimum:
        raise RuntimeError(f"source contains only {len(text.split())} extracted words")
    anchor_occurrences = {anchor: _occurrences(text, anchor) for anchor in anchors}
    missing = [anchor for anchor, positions in anchor_occurrences.items() if not positions]
    if missing:
        raise RuntimeError("required anchors were not extracted: " + ", ".join(missing))
    if focus_anchor:
        focus_positions = _occurrences(text, focus_anchor)
        if len(focus_positions) != 1:
            raise RuntimeError(
                f"focus anchor must occur exactly once, found {len(focus_positions)}: {focus_anchor}"
            )
        focus_position = focus_positions[0]
    else:
        focus_position = min(positions[0] for positions in anchor_occurrences.values())
    units = _content_units(text)
    selected_positions = {
        anchor: min(positions, key=lambda position: abs(position - focus_position))
        for anchor, positions in anchor_occurrences.items()
    }
    first = min(selected_positions.values())
    last = max(
        position + len(anchor)
        for anchor, position in selected_positions.items()
    )
    left = next((index for index, (_, end) in enumerate(units) if end >= first), None)
    right = next((index for index in range(len(units) - 1, -1, -1) if units[index][0] <= last), None)
    if left is None or right is None or right < left:
        raise RuntimeError("anchors could not be aligned to source sentences")

    def window_words(start_index: int, end_index: int) -> int:
        return len(text[units[start_index][0]:units[end_index][1]].split())

    if window_words(left, right) > maximum:
        raise RuntimeError(
            f"anchors cannot fit in one sentence-complete {minimum}-{maximum} word excerpt"
        )
    take_left = True
    while window_words(left, right) < minimum and (left > 0 or right + 1 < len(units)):
        if (take_left and left > 0) or right + 1 >= len(units):
            left -= 1
        else:
            right += 1
        take_left = not take_left
        if window_words(left, right) > maximum:
            raise RuntimeError("sentence-complete excerpt exceeds the maximum word count")
    start, end = units[left][0], units[right][1]
    excerpt = text[start:end]
    count = len(excerpt.split())
    if not minimum <= count <= maximum:
        raise RuntimeError(f"selected excerpt has {count} words")
    if not all(anchor.casefold() in excerpt.casefold() for anchor in anchors):
        raise RuntimeError("selected excerpt does not contain every required anchor")
    return excerpt, start, end


def summary(case: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in case.items() if key != "documents"} | {
        "documents": [{key: value for key, value in document.items() if key != "text"} for document in case["documents"]]
    }


def prepare_constructed(config: dict[str, Any], cache: Path, refresh: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    excerpt_policy = config["policy"]["excerptWords"]
    minimum, maximum = excerpt_policy["minimum"], excerpt_policy["maximum"]
    cases, audit = [], []
    for case_config in config["cases"]:
        documents = []
        for index, source in enumerate(case_config["sources"], start=1):
            if not source.get("redistributionApproved"):
                raise RuntimeError(f"source has not been approved for excerpt use: {source['url']}")
            body, content_type, retrieved_at, method = fetch_source(source, cache, refresh)
            full_text = extract_text(body, content_type, source["url"])
            if urlsplit(source["url"]).scheme != "https":
                raise RuntimeError(f"source URL must use HTTPS: {source['url']}")
            expected_domain = source.get("expectedDomain")
            if expected_domain and (urlsplit(source["url"]).hostname or "").casefold() != expected_domain.casefold():
                raise RuntimeError(f"source URL does not match expected domain {expected_domain}: {source['url']}")
            title_anchor = source.get("titleAnchor")
            if title_anchor and title_anchor.casefold() not in full_text.casefold():
                raise RuntimeError(f"configured page title was not extracted: {source['title']}")
            try:
                excerpt, start, end = select_excerpt(
                    full_text,
                    source["anchors"],
                    minimum,
                    maximum,
                    focus_anchor=source.get("focusAnchor"),
                )
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
                "sourceDescriptor": source.get("sourceDescriptor", "Institutional source"),
                "excerptRationale": EXCERPT_RATIONALE,
                "excerptSha256": excerpt_hash,
                "sourceSha256": source_hash,
                "text": excerpt,
            })
            audit.append({
                "caseId": case_config["id"], "documentId": document_id,
                "url": source["url"], "publisher": source["publisher"],
                "sourceDescriptor": source.get("sourceDescriptor", "Institutional source"),
                "retrievedAt": retrieved_at, "contentType": content_type,
                "method": method,
                "sourceWords": len(full_text.split()), "excerptWords": len(excerpt.split()),
                "sourceStart": start, "sourceEnd": end,
                "sentenceAligned": True,
                "sourceSha256": source_hash, "excerptSha256": excerpt_hash,
                "redistributionApproved": True,
            })
        cases.append({
            "id": case_config["id"], "claim": case_config["claim"],
            "documents": documents, "label": case_config["label"],
            "displayTitle": case_config["displayTitle"], "topics": [],
            "challenges": case_config.get("challenges", []),
            "featured": False, "origin": "CONSTRUCTED", "category": case_config["category"],
            "demoFocus": case_config["demoFocus"],
        })
    return cases, audit


def curated_averitec(bundle: Path, configured_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metadata = read_json(bundle / "metadata.json")
    cases = []
    for configured in configured_cases:
        case_id = configured["id"]
        case = read_json(bundle / "cases" / f"{case_id}.json")
        case.update(metadata.get(case_id, {}))
        case.update({
            "origin": "AVERITEC", "category": configured["category"],
            "featured": False, "demoFocus": configured["demoFocus"],
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
                "sourceDescriptor": document.get("sourceDescriptor", ""),
                "excerptRationale": document.get("excerptRationale", ""),
            })
        cases.append(case)
    return cases


def validate_showcase_policy(config: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    policy = config.get("policy")
    if config.get("version") != 2 or not isinstance(policy, dict):
        raise RuntimeError("showcase source manifest must use schema version 2 and define policy")
    integer_fields = (
        "caseCount", "constructedCount", "averitecCount",
        "constructedSourcesPerCase", "casesPerDisplayedCategory",
    )
    if any(not isinstance(policy.get(field), int) or policy[field] < 1 for field in integer_fields):
        raise RuntimeError("showcase policy count fields must be positive integers")
    excerpt_policy = policy.get("excerptWords", {})
    minimum, maximum = excerpt_policy.get("minimum"), excerpt_policy.get("maximum")
    if not isinstance(minimum, int) or not isinstance(maximum, int) or minimum < 1 or maximum < minimum:
        raise RuntimeError("showcase excerpt limits are invalid")
    displayed_categories = policy.get("displayedCategories")
    if not isinstance(displayed_categories, list) or not displayed_categories or len(displayed_categories) != len(set(displayed_categories)):
        raise RuntimeError("showcase displayed categories must be a non-empty unique list")
    configured_ids = [item["id"] for item in [*config["cases"], *config["averitecCases"]]]
    if len(configured_ids) != len(set(configured_ids)):
        raise RuntimeError("showcase source manifest contains duplicate case ids")
    if [case["id"] for case in cases] != configured_ids:
        raise RuntimeError("prepared showcase order does not match the source manifest")
    if len(cases) != policy["caseCount"]:
        raise RuntimeError("prepared showcase does not match policy.caseCount")
    constructed = [case for case in cases if case["origin"] == "CONSTRUCTED"]
    averitec = [case for case in cases if case["origin"] == "AVERITEC"]
    if len(constructed) != policy["constructedCount"] or len(averitec) != policy["averitecCount"]:
        raise RuntimeError("prepared showcase origin counts do not match policy")
    source_count = policy["constructedSourcesPerCase"]
    if any(len(case["documents"]) != source_count for case in constructed):
        raise RuntimeError("constructed source counts do not match showcase policy")
    displayed_counts = Counter(
        "AVERITEC" if case["origin"] == "AVERITEC" else case["category"]
        for case in cases
    )
    expected_displayed_counts = {
        category: policy["casesPerDisplayedCategory"] for category in displayed_categories
    }
    if displayed_counts != expected_displayed_counts:
        raise RuntimeError(f"showcase category distribution is invalid: {dict(displayed_counts)}")
    expected_labels = policy.get("verdictCounts")
    if not isinstance(expected_labels, dict) or set(expected_labels) != REFERENCE_LABELS:
        raise RuntimeError("showcase verdict policy must cover every reference label")
    if Counter(case["label"] for case in cases) != expected_labels:
        raise RuntimeError(f"showcase verdict distribution is invalid: {dict(Counter(case['label'] for case in cases))}")
    return policy


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the VeriNICE source-grounded showcase")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--averitec", type=Path, default=DEFAULT_AVERITEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    config = read_json(args.config)
    constructed, audit = prepare_constructed(config, args.cache, args.refresh)
    cases = [*constructed, *curated_averitec(args.averitec, config["averitecCases"])]
    policy = validate_showcase_policy(config, cases)
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
    write_json(args.output / "bundle.json", {
        "kind": "SHOWCASE", "version": 2,
        "caseIds": [case["id"] for case in cases], "policy": policy,
    })
    write_json(args.output / "fetch-audit.json", audit)
    digest = bundle_digest(args.output)
    (args.output / "bundle.sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"Prepared {len(cases)} showcase cases at {args.output} ({digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
