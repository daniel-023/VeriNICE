#!/usr/bin/env python3
"""Publish an approved local demo bundle as static walkthrough assets.

The Vercel build never calls the FastAPI service. This script copies the exact
case payloads and only accepts runs recorded by ``record_walkthrough.py``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from walkthrough_cases import CURATED_CASE_IDS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "data" / "demo" / "averitec"
DEFAULT_RUNS = ROOT / "data" / "walkthrough" / "runs"
DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "walkthrough"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Could not read {path}: {error}") from error


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def copy_json(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static VeriGraph walkthrough assets")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--all", action="store_true", help="Publish every approved demo case.")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless every case has a validated recorded run.",
    )
    args = parser.parse_args()

    catalog_path = args.bundle / "catalog.json"
    cases_dir = args.bundle / "cases"
    catalog = read_json(catalog_path)
    if not isinstance(catalog, list) or not catalog:
        raise RuntimeError("Demo catalog must be a non-empty JSON array")

    summaries_by_id = {
        summary.get("id"): summary
        for summary in catalog
        if isinstance(summary, dict) and isinstance(summary.get("id"), str)
    }
    selected_ids = args.case_ids or (
        list(summaries_by_id) if args.all else list(CURATED_CASE_IDS)
    )
    unknown = [case_id for case_id in selected_ids if case_id not in summaries_by_id]
    if unknown:
        raise RuntimeError("Unknown demo case ids: " + ", ".join(unknown))
    selected_catalog = [summaries_by_id[case_id] for case_id in selected_ids]

    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    for child in output.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    (output / "cases").mkdir()
    (output / "runs").mkdir(parents=True)
    (output / "catalog.json").write_text(
        json.dumps(selected_catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata_path = args.bundle / "metadata.json"
    if metadata_path.is_file():
        metadata = read_json(metadata_path)
        selected_metadata = {
            case_id: metadata[case_id]
            for case_id in selected_ids
            if case_id in metadata
        }
        (output / "metadata.json").write_text(
            json.dumps(selected_metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    missing_runs: list[str] = []
    run_digests: dict[str, str] = {}
    for summary in selected_catalog:
        case_id = summary["id"]
        case_path = cases_dir / f"{case_id}.json"
        case = read_json(case_path)
        if case.get("id") != case_id:
            raise RuntimeError(f"Case payload does not match catalog id: {case_id}")
        copy_json(case_path, output / "cases" / case_path.name)

        run_path = args.runs / f"{case_id}.json"
        if not run_path.is_file():
            missing_runs.append(case_id)
            continue
        run = read_json(run_path)
        if run.get("caseId") != case_id:
            raise RuntimeError(f"Recorded run does not match case id: {case_id}")
        if not all(
            key in run
            for key in (
                "schemaVersion",
                "composition",
                "warnings",
                "atoms",
                "evidence",
                "classifications",
                "linguistics",
                "verdict",
            )
        ):
            raise RuntimeError(f"Recorded run is incomplete: {case_id}")
        if run["schemaVersion"] != 2:
            raise RuntimeError(f"Recorded run uses an unsupported schema version: {case_id}")
        if run["composition"] not in {"SINGLE", "AND", "OR"}:
            raise RuntimeError(f"Recorded run has an invalid composition: {case_id}")
        if any("role" not in atom for atom in run["atoms"]):
            raise RuntimeError(f"Recorded run has atoms without roles: {case_id}")
        linguistics = run["linguistics"]
        if not isinstance(linguistics, dict) or linguistics.get("schemaVersion") != 2:
            raise RuntimeError(f"Recorded run has an unsupported linguistic schema: {case_id}")
        if not all(key in linguistics for key in ("claimAnalysis", "analyses", "summaries", "claimWarnings")):
            raise RuntimeError(f"Recorded run is missing linguistic audit data: {case_id}")
        if len(linguistics["analyses"]) != len(run["atoms"]) or len(linguistics["summaries"]) != len(run["atoms"]):
            raise RuntimeError(f"Recorded run has incomplete linguistic atom data: {case_id}")
        verdict = run["verdict"]
        if not isinstance(verdict, dict) or verdict.get("aggregationSchemaVersion") != 1:
            raise RuntimeError(f"Recorded run has an unsupported verdict schema: {case_id}")
        if verdict.get("verdict") not in {
            "SUPPORTED",
            "REFUTED",
            "NOT_ENOUGH_EVIDENCE",
            "CONFLICTING_EVIDENCE",
        }:
            raise RuntimeError(f"Recorded run has an invalid verdict: {case_id}")
        if len(verdict.get("obligations", [])) != len(run["atoms"]):
            raise RuntimeError(f"Recorded verdict does not cover every obligation: {case_id}")
        copy_json(run_path, output / "runs" / run_path.name)
        run_digests[case_id] = sha256(run_path)

    if args.require_complete and missing_runs:
        raise RuntimeError(
            "Recorded walkthrough is incomplete. Missing runs: " + ", ".join(missing_runs)
        )

    manifest = {
        "bundleDigest": (args.bundle / "bundle.sha256").read_text(encoding="utf-8").strip(),
        "caseCount": len(selected_catalog),
        "recordedCaseCount": len(run_digests),
        "runDigests": run_digests,
        "missingRuns": missing_runs,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Built {len(selected_catalog)} walkthrough cases with {len(run_digests)} recorded runs at {output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
