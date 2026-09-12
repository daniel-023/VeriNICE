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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "data" / "demo" / "showcase"
DEFAULT_RUNS = ROOT / "data" / "walkthrough" / "runs"
DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "walkthrough"
DEFAULT_PRESENTATION_AUDIT = ROOT / "data" / "manifests" / "showcase-audit.json"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Could not read {path}: {error}") from error


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def canonical_source(value: str) -> str:
    parts = urlsplit(value)
    host = (parts.hostname or "").casefold()
    netloc = host if parts.port is None else f"{host}:{parts.port}"
    return urlunsplit(("https", netloc, parts.path or "/", urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True))), ""))


def copy_json(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def write_json(value: Any, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def word_count(value: str) -> int:
    return len(value.split())


def input_digest(case: dict[str, Any]) -> str:
    serialized = json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def grounded_text(document: str, start: int, end: int) -> str:
    encoded = document.encode("utf-16-le")
    return encoded[start * 2:end * 2].decode("utf-16-le")


def default_graph_node_count(run: dict[str, Any], atom_id: str) -> int:
    """Count the nodes shown before a visitor expands cited premises."""
    base = 1 + len(run["atoms"])
    audit = next(item for item in run["assessment"]["obligations"] if item["atomId"] == atom_id)
    selected_counts = [
        len(audit.get("supportSpanIds", [])),
        len(audit.get("refuteSpanIds", [])),
    ] if audit.get("sufficiency") == "SUFFICIENT" else [0, 0]
    evidence_nodes = sum(1 for count in selected_counts if count == 1)
    bundle_nodes = sum(1 for count in selected_counts if count >= 2)
    resolved = [
        item for item in run["reasoning"]
        if item["atomId"] == atom_id and item["status"] in {"PROVED", "DISPROVED"}
    ]
    # Each visible inference has one representative source until expanded.
    return base + evidence_nodes + 2 * bundle_nodes + 2 * len(resolved)


def validate_presentation_run(case: dict[str, Any], run: dict[str, Any], audit: dict[str, Any]) -> None:
    case_id = case["id"]
    if not audit.get("approved"):
        raise RuntimeError(f"Presentation audit has not approved: {case_id}")
    actual_atoms = [item["text"] for item in run["atoms"]]
    if actual_atoms != audit.get("expectedAtoms"):
        raise RuntimeError(f"Atomic claims do not match the presentation audit: {case_id}")
    prohibited_warnings = {"DECOMPOSITION_FALLBACK", "MISSING_ASSERTION", "UNDER_DECOMPOSED"}
    warning_codes = {item.get("code") for item in run.get("warnings", [])}
    if warning_codes & prohibited_warnings:
        raise RuntimeError(f"Decomposition contains a prohibited fallback or coverage warning: {case_id}")
    allowed_short = set(audit.get("allowedShortLocators", []))
    for atom in run["atoms"]:
        locator_words = [word for word in atom["sourceText"].split() if any(character.isalnum() for character in word)]
        if len(locator_words) < 3 and atom["id"] not in allowed_short:
            raise RuntimeError(f"Atomic claim has an unaudited short locator: {case_id}/{atom['id']}")
    expected_verdict = audit.get("referenceVerdict")
    if expected_verdict != case.get("label") or run["verdict"].get("verdict") != expected_verdict:
        raise RuntimeError(f"Recorded verdict does not match the approved reference verdict: {case_id}")
    if audit.get("requireCrossDocumentConflict"):
        support_documents: set[str] = set()
        refute_documents: set[str] = set()
        for obligation in run["assessment"]["obligations"]:
            if obligation.get("sufficiency") != "SUFFICIENT":
                continue
            documents_by_span = {
                item.get("spanId"): item.get("documentId")
                for item in obligation.get("scopeChecks", [])
            }
            support_documents.update(
                documents_by_span[span_id]
                for span_id in obligation.get("supportSpanIds", [])
                if documents_by_span.get(span_id)
            )
            refute_documents.update(
                documents_by_span[span_id]
                for span_id in obligation.get("refuteSpanIds", [])
                if documents_by_span.get(span_id)
            )
        if not support_documents or not refute_documents or not support_documents.isdisjoint(refute_documents):
            raise RuntimeError(
                f"Conflicting evidence must be decisive and come from different documents: {case_id}"
            )
    executions = run["reasoning"]
    allowed_operators = audit.get("allowedOperators")
    if isinstance(allowed_operators, list):
        allowed = set(allowed_operators)
        if any(item.get("operator") not in allowed for item in executions):
            raise RuntimeError(f"An unaudited symbolic operator is present: {case_id}")
    for required in audit.get("requiredOperators", []):
        if not any(
            item.get("operator") == required.get("operator")
            and item.get("status") == required.get("status")
            for item in executions
        ):
            raise RuntimeError(f"Required symbolic result is missing: {case_id}/{required}")
    prohibited = set(audit.get("prohibitedDecisiveOperators", []))
    if any(item.get("operator") in prohibited and item.get("status") in {"PROVED", "DISPROVED"} for item in executions):
        raise RuntimeError(f"An unexpected symbolic operator became decisive: {case_id}")
    documents = {item["id"]: item["text"] for item in case["documents"]}
    for execution in executions:
        if execution.get("premiseIds") != [item.get("id") for item in execution.get("premises", [])]:
            raise RuntimeError(f"Symbolic premise identifiers were altered: {case_id}")
        if len(execution.get("premises", [])) > 3:
            raise RuntimeError(f"Symbolic result cites excessive premises: {case_id}/{execution.get('id')}")
        for premise in execution.get("premises", []):
            document = documents.get(premise.get("documentId"))
            if document is None or grounded_text(document, premise["start"], premise["end"]) != premise.get("text"):
                raise RuntimeError(f"Symbolic premise is not source-grounded: {case_id}/{premise.get('id')}")
            list_items = premise.get("listItems", [])
            if list_items:
                if premise.get("kind") != "LIST_CERTIFICATE" or premise.get("itemCount") != len(list_items):
                    raise RuntimeError(f"Invalid displayed list certificate: {case_id}/{premise.get('id')}")
                for item in list_items:
                    if (
                        item.get("documentId") != premise.get("documentId")
                        or item.get("contentHash") != premise.get("contentHash")
                        or grounded_text(document, item["start"], item["end"]) != item.get("text")
                    ):
                        raise RuntimeError(f"Displayed list item is not source-grounded: {case_id}/{item.get('id')}")
    for obligation in run["assessment"]["obligations"]:
        missing = obligation.get("missingInformation", "")
        if isinstance(missing, bool) or str(missing).strip().casefold() in {"false", "null", "none"}:
            raise RuntimeError(f"Invalid missing-information copy: {case_id}")
        if missing and not str(missing).rstrip().endswith((".", "!", "?")):
            raise RuntimeError(f"Incomplete missing-information sentence: {case_id}")
        if any("CZ" in check.get("claimJurisdictions", []) for check in obligation.get("scopeChecks", [])) and "czech" not in case["claim"].casefold():
            raise RuntimeError(f"Common-word jurisdiction collision detected: {case_id}")
    maximum = int(audit.get("maxDefaultGraphNodes", 9))
    if any(default_graph_node_count(run, atom["id"]) > maximum for atom in run["atoms"]):
        raise RuntimeError(f"Default selected-atom graph exceeds {maximum} nodes: {case_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static VeriNICE walkthrough assets")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--presentation-audit", type=Path, default=DEFAULT_PRESENTATION_AUDIT)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--all", action="store_true", help="Publish every approved demo case.")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless every case has a validated recorded run.",
    )
    args = parser.parse_args()

    audit_payload = read_json(args.presentation_audit)
    if audit_payload.get("version") != 2:
        raise RuntimeError("Presentation audit must use schema version 2")
    presentation_audits = {
        item["id"]: item for item in audit_payload.get("cases", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    catalog_path = args.bundle / "catalog.json"
    profile_path = args.bundle / "bundle.json"
    cases_dir = args.bundle / "cases"
    catalog = read_json(catalog_path)
    profile = read_json(profile_path)
    if not isinstance(catalog, list) or not catalog:
        raise RuntimeError("Demo catalog must be a non-empty JSON array")
    policy = profile.get("policy")
    configured_case_ids = profile.get("caseIds")
    if profile.get("kind") != "SHOWCASE" or profile.get("version") != 2:
        raise RuntimeError("Walkthrough source must be a version 2 showcase bundle")
    if not isinstance(policy, dict) or not isinstance(configured_case_ids, list):
        raise RuntimeError("Showcase bundle lacks its ordered case list or policy")

    summaries_by_id = {
        summary.get("id"): summary
        for summary in catalog
        if isinstance(summary, dict) and isinstance(summary.get("id"), str)
    }
    selected_ids = args.case_ids or (
        list(summaries_by_id) if args.all else configured_case_ids
    )
    unknown = [case_id for case_id in selected_ids if case_id not in summaries_by_id]
    if unknown:
        raise RuntimeError("Unknown demo case ids: " + ", ".join(unknown))
    selected_catalog = [summaries_by_id[case_id] for case_id in selected_ids]
    if not args.case_ids and not args.all and len(selected_catalog) != policy.get("caseCount"):
        raise RuntimeError("The public showcase does not match policy.caseCount")
    if set(presentation_audits) != set(selected_ids):
        raise RuntimeError("Presentation audit must cover the exact published case set")

    source_audit_path = args.bundle / "fetch-audit.json"
    source_audit = read_json(source_audit_path) if source_audit_path.is_file() else []
    approved_documents = {
        (item.get("caseId"), item.get("documentId"))
        for item in source_audit
        if isinstance(item, dict) and item.get("redistributionApproved") is True
    }

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
        if not case.get("demoFocus"):
            raise RuntimeError(f"Case lacks display-only demo focus metadata: {case_id}")
        source_ids = [canonical_source(item["url"]) for item in case.get("documents", [])]
        if len(source_ids) != len(set(source_ids)):
            raise RuntimeError(f"Case contains duplicate canonical sources: {case_id}")
        if case.get("origin") == "CONSTRUCTED":
            documents = case.get("documents", [])
            if len(documents) != policy.get("constructedSourcesPerCase"):
                raise RuntimeError(f"Constructed case source count does not match policy: {case_id}")
            excerpt_policy = policy.get("excerptWords", {})
            minimum_words = excerpt_policy.get("minimum")
            maximum_words = excerpt_policy.get("maximum")
            if not isinstance(minimum_words, int) or not isinstance(maximum_words, int):
                raise RuntimeError("Showcase bundle has invalid excerpt limits")
            for document in documents:
                if not all(document.get(field) for field in (
                    "publisher", "title", "url", "retrievedAt", "sourceType",
                    "sourceDescriptor", "excerptRationale", "excerptSha256",
                    "sourceSha256", "text",
                )):
                    raise RuntimeError(f"Constructed source lacks provenance: {case_id}")
                if (
                    document["sourceType"] != "SOURCE_EXCERPT"
                    or not minimum_words <= word_count(document["text"]) <= maximum_words
                ):
                    raise RuntimeError(f"Constructed source has an invalid excerpt: {case_id}")
                if hashlib.sha256(document["text"].encode("utf-8")).hexdigest() != document["excerptSha256"]:
                    raise RuntimeError(f"Constructed source excerpt hash is invalid: {case_id}")
                if (case_id, document["id"]) not in approved_documents:
                    raise RuntimeError(f"Constructed source lacks clearance metadata: {case_id}")
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
                "assessment",
                "reasoning",
                "linguistics",
                "verdict",
                "timingsSeconds",
            )
        ):
            raise RuntimeError(f"Recorded run is incomplete: {case_id}")
        if run["schemaVersion"] != 6:
            raise RuntimeError(f"Recorded run uses an unsupported schema version: {case_id}")
        if run["composition"] not in {"SINGLE", "AND", "OR"}:
            raise RuntimeError(f"Recorded run has an invalid composition: {case_id}")
        assessment = run["assessment"]
        if not isinstance(assessment, dict):
            raise RuntimeError(f"Recorded run is missing the evidence assessment: {case_id}")
        if "claimPosition" in assessment:
            raise RuntimeError(f"Recorded run contains the removed whole-claim position: {case_id}")
        if len(assessment.get("obligations", [])) != len(run["atoms"]):
            raise RuntimeError(f"Evidence assessment does not cover every atomic claim: {case_id}")
        if any(not isinstance(item.get("scopeChecks"), list) for item in assessment["obligations"]):
            raise RuntimeError(f"Recorded run is missing evidence scope checks: {case_id}")
        for item in assessment["obligations"]:
            mismatched = {
                check.get("spanId") for check in item["scopeChecks"]
                if check.get("status") == "MISMATCH"
            }
            if mismatched.intersection(item.get("supportSpanIds", []) + item.get("refuteSpanIds", [])):
                raise RuntimeError(f"Jurisdiction-mismatched evidence was selected decisively: {case_id}")
        recorded_with = run.get("recordedWith", {})
        # Runs recorded before retrieval modes existed used the current HYBRID
        # implementation. Add that deterministic provenance during publication;
        # model outputs, evidence IDs, and offsets remain untouched.
        recorded_with.setdefault("retrievalMethod", "HYBRID")
        if recorded_with["retrievalMethod"] not in {"HYBRID", "SEMANTIC", "LEXICAL"}:
            raise RuntimeError(f"Recorded run has an invalid retrieval method: {case_id}")
        if recorded_with.get("pipelineRevision") != "submission-ready-v2":
            raise RuntimeError(f"Recorded run predates the evidence-integrity pipeline: {case_id}")
        if not isinstance(recorded_with.get("inputDigest"), str) or len(recorded_with["inputDigest"]) != 64:
            raise RuntimeError(f"Recorded run lacks a source-input digest: {case_id}")
        if recorded_with["inputDigest"] != input_digest(case):
            raise RuntimeError(f"Recorded run does not match the current claim and sources: {case_id}")
        if "nliModel" in recorded_with or "deberta" in json.dumps(run).lower():
            raise RuntimeError(f"Recorded run contains stale DeBERTa metadata: {case_id}")
        if not isinstance(run["reasoning"], list):
            raise RuntimeError(f"Recorded run is missing symbolic reasoning output: {case_id}")
        if any(not isinstance(item.get("program"), dict) or item["program"].get("version") != 1 for item in run["reasoning"]):
            raise RuntimeError(f"Recorded run is missing typed symbolic programs: {case_id}")
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
        if not isinstance(verdict, dict) or verdict.get("aggregationSchemaVersion") != 3:
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
        audit_by_atom = {item["atomId"]: item for item in assessment["obligations"]}
        for item in verdict["obligations"]:
            if audit_by_atom[item["obligationId"]].get("sufficiency") == "SUFFICIENT":
                continue
            assessed_edges = [
                edge for edge in item.get("supportEdgeIds", []) + item.get("refuteEdgeIds", [])
                if ":evidence:" in edge or ":inference:bundle:" in edge
            ]
            if assessed_edges:
                raise RuntimeError(f"Insufficient evidence produced decisive graph edges: {case_id}")
        timings = run["timingsSeconds"]
        if not isinstance(timings, dict) or any(
            not isinstance(timings.get(key), (int, float)) or timings[key] < 0
            for key in (
                "decomposition",
                "retrievalAndLinguistics",
                "evidenceAssessment",
                "symbolicReasoning",
                "aggregation",
                "total",
            )
        ):
            raise RuntimeError(f"Recorded run is missing valid latency timings: {case_id}")
        validate_presentation_run(case, run, presentation_audits[case_id])
        output_run_path = output / "runs" / run_path.name
        write_json(run, output_run_path)
        run_digests[case_id] = sha256(output_run_path)

    if args.require_complete and missing_runs:
        raise RuntimeError(
            "Recorded walkthrough is incomplete. Missing runs: " + ", ".join(missing_runs)
        )

    manifest = {
        "bundleDigest": (args.bundle / "bundle.sha256").read_text(encoding="utf-8").strip(),
        "caseIds": selected_ids,
        "caseCount": len(selected_catalog),
        "policy": policy,
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
