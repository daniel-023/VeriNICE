#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urldefrag, urlparse

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from verigraph_backend.demo_data import bundle_digest  # noqa: E402
from verigraph_backend.schemas import (  # noqa: E402
    DemoCase,
    DemoDocument,
    ReferenceLabel,
)


AVERITEC_REVISION = "7c62d1ec8df3fb560d6efe2b85fa191135636f81"
DEFAULT_SOURCE = ROOT / "data" / "source" / "averitec-dev.json"
DEFAULT_SOURCE_REVISION = ROOT / "data" / "source" / "averitec-dev.revision"
DEFAULT_OUTPUT = ROOT / "data" / "demo" / "averitec"
DEFAULT_CACHE = ROOT / "data" / "cache" / "averitec_fetch"
DEFAULT_SEED_CACHE = ROOT / "data" / "cache" / "averitec_seed.jsonl"
MIN_DOCUMENT_WORDS = 175
MAX_DOCUMENTS_PER_CASE = 8
MAX_HTML_BYTES = 5_000_000
MIN_CASES_PER_LABEL = 5
MAX_CASES_PER_LABEL = 6
USER_AGENT = "VeriGraph-demo/0.4 (offline research dataset preparation)"


CANDIDATES: Dict[ReferenceLabel, Sequence[int]] = {
    ReferenceLabel.supported: (34, 77, 144, 146, 158, 453, 125, 319, 392, 145, 323, 161),
    ReferenceLabel.refuted: (44, 91, 168, 171, 239, 439, 180, 280, 419, 420, 495, 89),
    ReferenceLabel.not_enough_evidence: (15, 82, 142, 394, 413, 498, 26, 208, 428, 435, 229, 233),
    ReferenceLabel.conflicting_evidence: (60, 100, 259, 360, 404, 423, 10, 18, 58, 303, 480, 496),
}

SOURCE_LABELS = {
    "Supported": ReferenceLabel.supported,
    "Refuted": ReferenceLabel.refuted,
    "Not Enough Evidence": ReferenceLabel.not_enough_evidence,
    "Conflicting Evidence/Cherrypicking": ReferenceLabel.conflicting_evidence,
}

TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
HTML_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class FetchResult:
    status: str
    text: str = ""
    title: str = ""
    error: str = ""
    method: str = ""


def _tokens(value: str) -> set[str]:
    return {
        match.group(0).casefold()
        for match in TOKEN_PATTERN.finditer(value)
        if len(match.group(0)) > 2
    }


def _word_count(value: str) -> int:
    return len(value.split())


def _canonical_url(value: str) -> str:
    return urldefrag(value.strip())[0]


def _canonical_source_url(value: str) -> str:
    url = _canonical_url(value)
    match = re.match(
        r"^https?://web\.archive\.org/web/[^/]+/(https?://.+)$",
        url,
        flags=re.IGNORECASE,
    )
    return _canonical_url(match.group(1)) if match else url


def _raw_wayback_url(value: str) -> Optional[str]:
    url = _canonical_url(value)
    match = re.match(
        r"^(https?://web\.archive\.org/web/)(\d+)/(https?://.+)$",
        url,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return f"{match.group(1)}{match.group(2)}id_/{match.group(3)}"


def _title_from_html(page_html: str, url: str) -> str:
    match = HTML_TITLE_PATTERN.search(page_html)
    if match:
        title = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
        if title:
            return title[:300]
    return urlparse(url).netloc or "Evidence source"


def _clean_extracted_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    output: List[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if output and not previous_blank:
                output.append("")
            previous_blank = True
            continue
        output.append(line)
        previous_blank = False
    return "\n".join(output).strip()


def extract_html(page_html: str, url: str) -> FetchResult:
    try:
        import trafilatura
    except ImportError as error:
        raise RuntimeError(
            "Dataset preparation requires trafilatura. Install the backend data extra."
        ) from error
    extracted = trafilatura.extract(
        page_html,
        include_comments=False,
        include_images=False,
        include_links=False,
        favor_recall=True,
    )
    text = _clean_extracted_text(extracted or "")
    if not text:
        return FetchResult(status="extraction_failed", error="No article text found")
    return FetchResult(
        status="ok",
        text=text,
        title=_title_from_html(page_html, url),
    )


class HttpFetcher:
    def __init__(
        self,
        cache_dir: Path,
        *,
        timeout: float = 15.0,
        retries: int = 2,
        offline: bool = False,
        throttle_seconds: float = 0.35,
    ) -> None:
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.retries = max(1, retries)
        self.offline = offline
        self.throttle_seconds = throttle_seconds
        self._last_request = 0.0
        self._throttle_lock = threading.Lock()
        self._client_lock = threading.Lock()
        self._clients: List[httpx.Client] = []
        self._thread_local = threading.local()
        self._client_options = dict(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )

    def _client(self) -> httpx.Client:
        client = getattr(self._thread_local, "client", None)
        if client is None:
            client = httpx.Client(**self._client_options)
            self._thread_local.client = client
            with self._client_lock:
                self._clients.append(client)
        return client

    def close(self) -> None:
        for client in self._clients:
            client.close()

    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.json"

    def _load_cache(self, url: str) -> Optional[FetchResult]:
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            return FetchResult(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError):
            return None

    def _save_cache(self, url: str, result: FetchResult) -> None:
        if result.status not in {
            "ok",
            "not_found",
            "invalid_content_type",
            "invalid_url",
            "http_error",
        }:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path(url).write_text(
            json.dumps(result.__dict__, ensure_ascii=False), encoding="utf-8"
        )

    def _throttle(self) -> None:
        with self._throttle_lock:
            wait = self.throttle_seconds - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def seed_jsonl(self, path: Path) -> int:
        # Seeding is a one-time bootstrap. Re-reading every extracted document on
        # each deterministic retry is expensive on cloud-backed workspaces.
        if any(self.cache_dir.glob("*.json")) or not path.is_file():
            return 0
        seeded = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            url = _canonical_url(str(row.get("url", "")))
            text = _clean_extracted_text(str(row.get("text", "")))
            if row.get("status") != "ok" or not url.startswith(("http://", "https://")) or not text:
                continue
            if self._load_cache(url) is not None:
                continue
            result = FetchResult(
                status="ok",
                text=text,
                title=urlparse(url).netloc or "Evidence source",
                method="prior_offline_cache",
            )
            self._save_cache(url, result)
            seeded += 1
        return seeded

    def fetch(self, url: str) -> FetchResult:
        cached = self._load_cache(url)
        if cached is not None:
            return cached
        if self.offline:
            return FetchResult(status="missing_cache", error="Not present in offline cache")

        last_error = ""
        for attempt in range(self.retries):
            self._throttle()
            try:
                response = self._client().get(url)
                if response.status_code == 404:
                    result = FetchResult(status="not_found", error="HTTP 404")
                    self._save_cache(url, result)
                    return result
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                    time.sleep(2**attempt)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "html" not in content_type:
                    result = FetchResult(
                        status="invalid_content_type",
                        error=f"Expected HTML, got {content_type or 'unknown'}",
                    )
                    self._save_cache(url, result)
                    return result
                if len(response.content) > MAX_HTML_BYTES:
                    result = FetchResult(
                        status="invalid_content_type",
                        error=f"HTML response exceeded {MAX_HTML_BYTES} bytes",
                    )
                    self._save_cache(url, result)
                    return result
                result = extract_html(response.text, str(response.url))
                result = FetchResult(**{**result.__dict__, "method": "http"})
                self._save_cache(url, result)
                return result
            except httpx.InvalidURL as error:
                result = FetchResult(status="invalid_url", error=str(error))
                self._save_cache(url, result)
                return result
            except httpx.TimeoutException:
                last_error = f"Timed out after {self.timeout:g}s"
            except httpx.HTTPError as error:
                last_error = str(error)
            if attempt + 1 < self.retries:
                time.sleep(2**attempt)
        result = FetchResult(status="http_error", error=last_error or "Fetch failed")
        self._save_cache(url, result)
        return result

    def wayback_url(self, url: str) -> Optional[str]:
        if self.offline:
            return None
        self._throttle()
        try:
            response = self._client().get(
                "https://archive.org/wayback/available", params={"url": url}
            )
            response.raise_for_status()
            closest = (
                response.json().get("archived_snapshots", {}).get("closest", {})
            )
            snapshot = closest.get("url") if closest.get("available") else None
            if isinstance(snapshot, str) and snapshot.startswith("http://"):
                snapshot = "https://" + snapshot[len("http://") :]
            return snapshot if isinstance(snapshot, str) else None
        except (httpx.HTTPError, ValueError):
            return None


def _source_groups(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for question in row.get("questions", []) or []:
        question_text = (question.get("question") or "").strip()
        for answer in question.get("answers", []) or []:
            if answer.get("source_medium") != "Web text":
                continue
            source_url = (answer.get("source_url") or "").strip()
            if not source_url.startswith(("http://", "https://")):
                continue
            archived_source_url = _canonical_url(source_url)
            canonical = _canonical_source_url(source_url)
            group = groups.setdefault(
                canonical,
                {
                    "source_url": canonical,
                    "cached_urls": [],
                    "evidence_text": [],
                },
            )
            cached_url = (answer.get("cached_source_url") or "").strip()
            if cached_url.startswith(("http://", "https://")):
                cached_url = _canonical_url(cached_url)
                if cached_url not in group["cached_urls"]:
                    group["cached_urls"].append(cached_url)
                raw_cached_url = _raw_wayback_url(cached_url)
                if raw_cached_url and raw_cached_url not in group["cached_urls"]:
                    group["cached_urls"].append(raw_cached_url)
            if archived_source_url != canonical and archived_source_url not in group["cached_urls"]:
                group["cached_urls"].append(archived_source_url)
                raw_source_url = _raw_wayback_url(archived_source_url)
                if raw_source_url and raw_source_url not in group["cached_urls"]:
                    group["cached_urls"].append(raw_source_url)
            answer_text = (answer.get("answer") or "").strip()
            group["evidence_text"].append(f"{question_text} {answer_text}".strip())
    return list(groups.values())


def _is_relevant(claim: str, evidence_text: Sequence[str], document: str) -> bool:
    document_tokens = _tokens(document)
    query_tokens = _tokens(" ".join([claim, *evidence_text]))
    overlap = document_tokens.intersection(query_tokens)
    if len(overlap) >= min(8, max(3, len(query_tokens) // 12)):
        return True
    normalized_document = re.sub(r"\s+", " ", document).casefold()
    return any(
        len(answer) >= 24
        and re.sub(r"\s+", " ", answer).casefold() in normalized_document
        for answer in evidence_text
    )


def prepare_case(
    index: int,
    row: Dict[str, Any],
    fetch: Callable[[str], FetchResult],
    wayback_resolver: Callable[[str], Optional[str]],
) -> Tuple[Optional[DemoCase], Dict[str, Any]]:
    expected_label = SOURCE_LABELS.get(row.get("label"))
    audit: Dict[str, Any] = {
        "sourceIndex": index,
        "caseId": f"averitec-dev-{index:04d}",
        "label": expected_label.value if expected_label else row.get("label"),
        "claim": row.get("claim", ""),
        "sources": [],
        "accepted": False,
    }
    if expected_label is None:
        audit["reason"] = "unsupported_label"
        return None, audit

    def prepare_source(group: Dict[str, Any]) -> Tuple[Optional[DemoDocument], Dict[str, Any]]:
        source_audit: Dict[str, Any] = {
            "sourceUrl": group["source_url"],
            "attempts": [],
            "accepted": False,
        }
        attempt_urls = [*group["cached_urls"]]
        if group["source_url"] not in attempt_urls:
            attempt_urls.append(group["source_url"])
        result: Optional[FetchResult] = None
        resolved_url = ""
        for method, url in (("dataset_archive", url) for url in attempt_urls[:-1]):
            candidate = fetch(url)
            source_audit["attempts"].append(
                {"url": url, "method": method, "status": candidate.status, "error": candidate.error}
            )
            if candidate.status == "ok":
                result, resolved_url = candidate, url
                break
        if result is None:
            original = attempt_urls[-1]
            candidate = fetch(original)
            source_audit["attempts"].append(
                {"url": original, "method": "original", "status": candidate.status, "error": candidate.error}
            )
            if candidate.status == "ok":
                result, resolved_url = candidate, original
        if result is None:
            snapshot = wayback_resolver(group["source_url"])
            if snapshot:
                candidate = fetch(snapshot)
                source_audit["attempts"].append(
                    {"url": snapshot, "method": "wayback_lookup", "status": candidate.status, "error": candidate.error}
                )
                if candidate.status == "ok":
                    result, resolved_url = candidate, snapshot

        if result is None:
            source_audit["reason"] = "fetch_failed"
        elif _word_count(result.text) < MIN_DOCUMENT_WORDS:
            source_audit["reason"] = "document_too_short"
            source_audit["wordCount"] = _word_count(result.text)
        elif not _is_relevant(row.get("claim", ""), group["evidence_text"], result.text):
            source_audit["reason"] = "gold_evidence_not_grounded"
            source_audit["wordCount"] = _word_count(result.text)
        else:
            document_id = "doc-" + hashlib.sha256(
                group["source_url"].encode("utf-8")
            ).hexdigest()[:12]
            document = DemoDocument(
                id=document_id,
                title=result.title or urlparse(group["source_url"]).netloc or "Evidence source",
                url=group["source_url"],
                text=result.text,
            )
            source_audit.update(
                {
                    "accepted": True,
                    "resolvedUrl": resolved_url,
                    "wordCount": _word_count(result.text),
                    "sha256": hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
                }
            )
            return document, source_audit
        return None, source_audit

    groups = _source_groups(row)
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(groups)))) as executor:
        source_results = list(executor.map(prepare_source, groups))
    documents: List[DemoDocument] = []
    for document, source_audit in source_results:
        audit["sources"].append(source_audit)
        if document is not None and len(documents) < MAX_DOCUMENTS_PER_CASE:
            documents.append(document)

    if len(documents) < 2:
        audit["reason"] = "fewer_than_two_accepted_documents"
        return None, audit
    case = DemoCase(
        id=audit["caseId"],
        claim=row.get("claim", ""),
        documents=documents,
        label=expected_label,
    )
    audit["accepted"] = True
    audit["documentCount"] = len(documents)
    return case, audit


def prepare_catalog(
    rows: Sequence[Dict[str, Any]],
    fetch: Callable[[str], FetchResult],
    wayback_resolver: Callable[[str], Optional[str]],
) -> Tuple[List[DemoCase], List[Dict[str, Any]]]:
    cases: List[DemoCase] = []
    audits: List[Dict[str, Any]] = []
    counts: Dict[ReferenceLabel, int] = defaultdict(int)
    for label, indices in CANDIDATES.items():
        for index in indices:
            if counts[label] >= MAX_CASES_PER_LABEL:
                break
            if index >= len(rows):
                raise RuntimeError(f"AVeriTeC dev split is missing index {index}")
            row = rows[index]
            actual_label = SOURCE_LABELS.get(row.get("label"))
            if actual_label != label:
                raise RuntimeError(
                    f"AVeriTeC case {index} label drifted from {label.value} to {row.get('label')!r}"
                )
            case, audit = prepare_case(index, row, fetch, wayback_resolver)
            audits.append(audit)
            if case is not None:
                cases.append(case)
                counts[label] += 1
            print(
                f"[{label.value}] AVeriTeC dev {index}: "
                f"{'accepted' if case is not None else audit.get('reason', 'rejected')}",
                flush=True,
            )
        if counts[label] < MIN_CASES_PER_LABEL:
            raise RuntimeError(
                f"Only {counts[label]} valid {label.value} cases were recovered; five are required"
            )
    return cases, audits


def write_bundle(cases: Sequence[DemoCase], audits: Sequence[Dict[str, Any]], output: Path) -> str:
    output.mkdir(parents=True, exist_ok=True)
    cases_dir = output / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    expected_names = {f"{case.id}.json" for case in cases}
    for stale_path in cases_dir.glob("*.json"):
        if stale_path.name not in expected_names:
            stale_path.unlink()
    summaries = [case.summary().model_dump(mode="json", by_alias=True) for case in cases]
    (output / "catalog.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for case in cases:
        (cases_dir / f"{case.id}.json").write_text(
            json.dumps(case.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    (output / "fetch-audit.json").write_text(
        json.dumps(list(audits), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    digest = bundle_digest(output)
    (output / "bundle.sha256").write_text(digest + "\n", encoding="utf-8")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the multidocument AVeriTeC demo bundle")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-revision", type=Path, default=DEFAULT_SOURCE_REVISION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--seed-cache", type=Path, default=DEFAULT_SEED_CACHE)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    if not args.source.is_file():
        raise RuntimeError(
            f"AVeriTeC dev split is missing at {args.source}. Place the pinned source file there "
            "or pass --source explicitly."
        )
    if not args.source_revision.is_file():
        raise RuntimeError(
            f"AVeriTeC revision marker is missing at {args.source_revision}. It must contain "
            f"{AVERITEC_REVISION}."
        )
    revision = args.source_revision.read_text(encoding="utf-8").strip()
    if revision != AVERITEC_REVISION:
        raise RuntimeError(
            f"AVeriTeC revision changed: expected {AVERITEC_REVISION}, got {revision}"
        )
    rows = json.loads(args.source.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise RuntimeError("AVeriTeC source must be a JSON array")

    fetcher = HttpFetcher(
        args.cache_dir,
        timeout=args.timeout,
        retries=args.retries,
        offline=args.offline,
    )
    seeded = fetcher.seed_jsonl(args.seed_cache)
    if seeded:
        print(f"Seeded {seeded} previously extracted source documents into the fetch cache.", flush=True)
    try:
        cases, audits = prepare_catalog(rows, fetcher.fetch, fetcher.wayback_url)
    except Exception:
        args.output.mkdir(parents=True, exist_ok=True)
        partial_audits = locals().get("audits", [])
        (args.output / "fetch-audit.json").write_text(
            json.dumps(partial_audits, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        raise
    finally:
        fetcher.close()
    digest = write_bundle(cases, audits, args.output)
    counts = defaultdict(int)
    for case in cases:
        counts[case.label.value] += 1
    print(f"Prepared {len(cases)} AVeriTeC cases at {args.output}")
    print(json.dumps(dict(counts), indent=2, sort_keys=True))
    print(f"Bundle digest: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
