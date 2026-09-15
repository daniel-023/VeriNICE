#!/usr/bin/env python3
"""Record the current local VeriNICE pipeline for the static walkthrough."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "walkthrough" / "runs"
DEFAULT_BUNDLE_PROFILE = ROOT / "data" / "demo" / "showcase" / "bundle.json"
_AGGREGATION_SCHEMA = "VerdictAggregationRequest"
_ASSESSMENT_RESPONSE_SCHEMA = "EvidenceAssessmentResponse"
_ASSESSMENT_REQUEST_SCHEMA = "EvidenceAssessmentRequest"


def validate_api_contract(openapi: dict[str, Any]) -> None:
    """Fail before inference when the running backend predates this recorder.

    Local Uvicorn processes do not reload source changes by default.  In that
    situation the recorder and the checked-in schemas can disagree even though
    both are individually valid, and the mismatch otherwise appears only after
    the expensive decomposition, retrieval, and evidence-audit stages have run.
    """
    schemas = openapi.get("components", {}).get("schemas", {})
    aggregation = schemas.get(_AGGREGATION_SCHEMA)
    if not isinstance(aggregation, dict):
        raise RuntimeError(
            "The running backend does not expose the current verdict aggregation API. "
            "Stop the local VeriNICE process, run ./run-verinice --start again, "
            "then retry recording."
        )

    properties = aggregation.get("properties", {})
    required = set(aggregation.get("required", []))
    if (
        "claim" in properties
        or "claim" in required
        or "claimId" not in properties
        or "assessment" not in properties
        or "reasoning" not in properties
    ):
        raise RuntimeError(
            "The running backend is stale: its verdict aggregation request schema "
            "does not match the current pipeline. Stop it with Ctrl-C, run "
            "./run-verinice --start again, then rerun ./run-verinice "
            "--record-walkthrough."
        )
    assessment_response = schemas.get(_ASSESSMENT_RESPONSE_SCHEMA)
    assessment_properties = (
        assessment_response.get("properties", {})
        if isinstance(assessment_response, dict)
        else {}
    )
    if "assessment" not in assessment_properties:
        raise RuntimeError(
            "The running backend is stale: grounded evidence auditing is not exposed. "
            "Stop it with Ctrl-C, run ./run-verinice --start again, then rerun "
            "./run-verinice --record-walkthrough."
        )
    assessment_request = schemas.get(_ASSESSMENT_REQUEST_SCHEMA, {})
    assessment_request_properties = assessment_request.get("properties", {})
    if (
        "documentTitles" in assessment_request_properties
        or "caseId" not in assessment_request_properties
        or "documents" not in assessment_request_properties
    ):
        raise RuntimeError(
            "The running backend predates server-side evidence scope validation. "
            "Restart VeriNICE before recording."
        )


async def request(client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> Any:
    response = await client.request(method, path, **kwargs)
    if response.is_error:
        detail = response.text.strip()
        try:
            payload = response.json()
            if isinstance(payload, dict) and payload.get("detail"):
                detail = str(payload["detail"])
        except ValueError:
            pass
        raise RuntimeError(
            f"{method} {path} failed with HTTP {response.status_code}: {detail or 'no response detail'}"
        )
    return response.json()


async def request_with_retries(
    client: httpx.AsyncClient, method: str, path: str, *, attempts: int = 3, **kwargs: Any
) -> Any:
    for attempt in range(1, attempts + 1):
        try:
            return await request(client, method, path, **kwargs)
        except RuntimeError as error:
            if "HTTP 502" not in str(error) or attempt == attempts:
                raise
            print(f"  Retry {attempt}/{attempts - 1} for {path}: {error}", flush=True)
            await asyncio.sleep(float(attempt))
    raise AssertionError("unreachable")


def input_digest(case: dict[str, Any]) -> str:
    serialized = json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def record_case(client: httpx.AsyncClient, case_id: str, case: dict[str, Any] | None = None) -> dict[str, Any]:
    case_started = time.perf_counter()
    case = case or await request(client, "GET", f"/api/v1/demo-cases/{case_id}")
    decomposition_started = time.perf_counter()
    decomposition = None
    for attempt in range(1, 4):
        try:
            decomposition = await request(
                client, "POST", "/api/v1/decompose", json={"claim": case["claim"]}
            )
            break
        except RuntimeError as error:
            if "HTTP 502" not in str(error) or attempt == 3:
                raise
            print(
                f"  Decomposition retry {attempt}/2 for {case_id}: {error}",
                flush=True,
            )
            await asyncio.sleep(float(attempt))
    assert decomposition is not None
    decomposition_seconds = time.perf_counter() - decomposition_started
    atoms = [{"id": atom["id"], "text": atom["text"]} for atom in decomposition["atoms"]]
    retrieval_started = time.perf_counter()
    retrieval = await request(
        client,
        "POST",
        "/api/v1/retrieve",
        json={"caseId": case_id, "atoms": atoms, "retrievalMethod": "HYBRID"},
    )
    retrieval_seconds = time.perf_counter() - retrieval_started
    assessment_started = time.perf_counter()
    assessment = await request_with_retries(
        client,
        "POST",
        "/api/v1/assess-evidence",
        json={
            "claim": case["claim"],
            "caseId": case_id,
            "atoms": atoms,
            "evidence": retrieval["evidence"],
        },
    )
    assessment_seconds = time.perf_counter() - assessment_started
    reasoning_started = time.perf_counter()
    reasoning = await request_with_retries(
        client,
        "POST",
        "/api/v1/reason",
        json={
            "caseId": case_id,
            "claim": case["claim"],
            "atoms": atoms,
            "evidence": retrieval["evidence"],
            "assessment": assessment["assessment"],
        },
    )
    reasoning_seconds = time.perf_counter() - reasoning_started
    aggregation_started = time.perf_counter()
    verdict = await request(
        client,
        "POST",
        "/api/v1/aggregate-verdict",
        json={
            "claimId": case_id,
            "composition": decomposition["composition"],
            "atoms": decomposition["atoms"],
            "evidence": retrieval["evidence"],
            "assessment": assessment["assessment"],
            "reasoning": reasoning["executions"],
        },
    )
    aggregation_seconds = time.perf_counter() - aggregation_started
    return {
        "caseId": case_id,
        "schemaVersion": 7,
        "composition": decomposition["composition"],
        "warnings": decomposition["warnings"],
        "atoms": decomposition["atoms"],
        "evidence": retrieval["evidence"],
        "assessment": assessment["assessment"],
        "reasoning": reasoning["executions"],
        "verdict": verdict,
        "recordedWith": {
            "pipelineRevision": "generalized-symbolic-v5",
            "inputDigest": input_digest(case),
            "decompositionModel": decomposition["model"],
            "retrievalModel": retrieval["model"],
            "retrievalMethod": retrieval["retrievalMethod"],
            "assessmentModel": assessment["model"],
            "reasoningModel": reasoning["model"],
        },
        "timingsSeconds": {
            "decomposition": round(decomposition_seconds, 3),
            "retrieval": round(retrieval_seconds, 3),
            "evidenceAssessment": round(assessment_seconds, 3),
            "symbolicReasoning": round(reasoning_seconds, 3),
            "aggregation": round(aggregation_seconds, 3),
            "total": round(time.perf_counter() - case_started, 3),
        },
    }


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Record local VeriNICE walkthrough runs")
    parser.add_argument("--api", default="http://127.0.0.1:3000")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bundle-profile", type=Path, default=DEFAULT_BUNDLE_PROFILE)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--all", action="store_true", help="Record every approved demo case.")
    parser.add_argument("--resume", action="store_true", help="Skip already valid schema-v7 runs.")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    try:
        import httpx
    except ImportError as error:
        raise RuntimeError(
            "Run ./run-verinice --prepare first so the backend virtualenv contains httpx."
        ) from error

    args.output.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=args.api, timeout=args.timeout) as client:
        openapi = await request(client, "GET", "/openapi.json")
        validate_api_contract(openapi)
        catalog = await request(client, "GET", "/api/v1/demo-cases")
        try:
            profile = json.loads(args.bundle_profile.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(f"Could not read showcase bundle profile: {error}") from error
        configured_case_ids = profile.get("caseIds")
        if profile.get("kind") != "SHOWCASE" or not isinstance(configured_case_ids, list):
            raise RuntimeError("Walkthrough bundle profile lacks its ordered showcase case list")
        selected = args.case_ids or (
            [item["id"] for item in catalog] if args.all else configured_case_ids
        )
        valid = {item["id"] for item in catalog}
        unknown = [case_id for case_id in selected if case_id not in valid]
        if unknown:
            raise RuntimeError("Unknown demo case ids: " + ", ".join(unknown))
        for index, case_id in enumerate(selected, start=1):
            output_path = args.output / f"{case_id}.json"
            case = await request(client, "GET", f"/api/v1/demo-cases/{case_id}")
            if args.resume and output_path.is_file():
                try:
                    existing = json.loads(output_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    existing = {}
                if (
                    existing.get("schemaVersion") == 7
                    and existing.get("recordedWith", {}).get("pipelineRevision") == "generalized-symbolic-v5"
                    and existing.get("recordedWith", {}).get("inputDigest") == input_digest(case)
                    and isinstance(existing.get("assessment"), dict)
                    and isinstance(existing.get("reasoning"), list)
                    and existing.get("verdict", {}).get("aggregationSchemaVersion") == 3
                    and "claimPosition" not in existing.get("assessment", {})
                    and "linguistics" not in existing
                    and "linguisticsModel" not in existing.get("recordedWith", {})
                    and isinstance(existing.get("timingsSeconds", {}).get("retrieval"), (int, float))
                    and "deberta" not in json.dumps(existing).casefold()
                ):
                    print(f"[{index}/{len(selected)}] Keeping {case_id} (schema v7)", flush=True)
                    continue
            print(f"[{index}/{len(selected)}] Recording {case_id}", flush=True)
            run = await record_case(client, case_id, case)
            output_path.write_text(
                json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
