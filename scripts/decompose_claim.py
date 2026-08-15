#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from verigraph_backend.claim_decomposition import (  # noqa: E402
    DecompositionError,
    decompose_claim,
)


async def _run(claim: str) -> int:
    try:
        result = await decompose_claim(claim)
    except DecompositionError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(by_alias=True), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decompose one claim into WiCE-style atomic facts"
    )
    parser.add_argument("claim", help="claim text to decompose")
    args = parser.parse_args()
    return asyncio.run(_run(args.claim))


if __name__ == "__main__":
    raise SystemExit(main())
