#!/usr/bin/env python3
"""Record the current local VeriGraph pipeline for the static walkthrough."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from walkthrough_cases import CURATED_CASE_IDS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "walkthrough" / "runs"


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


async def record_case(client: httpx.AsyncClient, case_id: str) -> dict[str, Any]:
    case = await request(client, "GET", f"/api/v1/demo-cases/{case_id}")
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
    atoms = [{"id": atom["id"], "text": atom["text"]} for atom in decomposition["atoms"]]
    retrieval_task = request(
        client, "POST", "/api/v1/retrieve", json={"caseId": case_id, "atoms": atoms}
    )
    linguistics_task = request(
        client, "POST", "/api/v1/analyze-linguistics", json={"atoms": atoms}
    )
    retrieval, linguistics = await asyncio.gather(retrieval_task, linguistics_task)
    nli = await request(
        client,
        "POST",
        "/api/v1/classify-support",
        json={"atoms": atoms, "evidence": retrieval["evidence"]},
    )
    return {
        "caseId": case_id,
        "atoms": decomposition["atoms"],
        "evidence": retrieval["evidence"],
        "classifications": nli["classifications"],
        "linguistics": linguistics["analyses"],
        "recordedWith": {
            "decompositionModel": decomposition["model"],
            "retrievalModel": retrieval["model"],
            "nliModel": nli["model"],
            "linguisticsModel": linguistics["model"],
        },
    }


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Record local VeriGraph walkthrough runs")
    parser.add_argument("--api", default="http://127.0.0.1:3000")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--all", action="store_true", help="Record every approved demo case.")
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()

    try:
        import httpx
    except ImportError as error:
        raise RuntimeError(
            "Run ./run-verigraph --prepare first so the backend virtualenv contains httpx."
        ) from error

    args.output.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=args.api, timeout=args.timeout) as client:
        catalog = await request(client, "GET", "/api/v1/demo-cases")
        selected = args.case_ids or (
            [item["id"] for item in catalog] if args.all else list(CURATED_CASE_IDS)
        )
        valid = {item["id"] for item in catalog}
        unknown = [case_id for case_id in selected if case_id not in valid]
        if unknown:
            raise RuntimeError("Unknown demo case ids: " + ", ".join(unknown))
        for index, case_id in enumerate(selected, start=1):
            print(f"[{index}/{len(selected)}] Recording {case_id}", flush=True)
            run = await record_case(client, case_id)
            (args.output / f"{case_id}.json").write_text(
                json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
