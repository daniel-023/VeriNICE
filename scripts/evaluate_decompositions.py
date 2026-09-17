#!/usr/bin/env python3
"""Run the live decomposer against the recorded corpus and semantic challenges.

This is an offline quality gate, not part of inference. It checks semantic
properties rather than snapshotting one exact model response.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import statistics
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = ROOT / "data" / "walkthrough" / "runs"
DECOMPOSITION_PROMPT_SOURCE = (
    ROOT / "backend" / "verinice_backend" / "claim_decomposition_prompt.py"
)
DEFAULT_CATALOGS = (
    ROOT / "data" / "demo" / "averitec" / "catalog.json",
    ROOT / "data" / "demo" / "showcase" / "catalog.json",
)
HIGH_SEVERITY_WARNINGS = {
    "DECOMPOSITION_FALLBACK",
    "MULTIPLE_NUMERIC_ASSERTIONS",
    "UNDER_DECOMPOSED",
}


CHALLENGES: tuple[dict[str, Any], ...] = (
    {
        "id": "quantified-causality",
        "claim": "Investigators concluded that a cracked insulator caused 43 signal failures.",
        "composition": "SINGLE",
        "atomCount": 1,
        "together": (("investigators", "insulator", "43", "failures"),),
        "roles": (("failures", "CAUSAL_RELATION"),),
    },
    {
        "id": "subordinate-numeric-assertions",
        "claim": "Although the reserve gained 320 nesting pairs, 75 tagged birds died during winter.",
        "composition": "AND",
        "atomCount": 2,
        "together": (("gained", "320"), ("died", "75")),
        "separate": (("320", "75"),),
        "roles": (("320", "NUMERIC_CONSTRAINT"), ("75", "NUMERIC_CONSTRAINT")),
    },
    {
        "id": "resolved-possessive",
        "claim": "Nora launched the Meridian probe in 2020 and calibrated its spectrometer in 2021.",
        "composition": "AND",
        "atomCount": 2,
        "together": (("meridian probe", "2020"), ("meridian", "spectrometer", "2021")),
        "forbiddenIn": (("spectrometer", r"\b(?:his|her|its|their)\b"),),
    },
    {
        "id": "temporal-comparison",
        "claim": "The lake froze earlier in 2025 than it did in 2024.",
        "composition": "SINGLE",
        "atomCount": 1,
        "together": (("froze", "earlier", "2025", "2024"),),
    },
    {
        "id": "coordinated-range",
        "claim": "The warning light changed from green through yellow to red.",
        "composition": "SINGLE",
        "atomCount": 1,
        "together": (("green", "yellow", "red"),),
    },
    {
        "id": "association-not-causation",
        "claim": "Longer rehearsal time correlated with fewer timing errors.",
        "composition": "SINGLE",
        "atomCount": 1,
        "roles": (("correlated", "CORE"),),
    },
    {
        "id": "reported-attribution",
        "claim": "The archivist stated the map was a later copy.",
        "composition": "SINGLE",
        "atomCount": 1,
        "roles": (("archivist", "ATTRIBUTION"),),
    },
    {
        "id": "shared-condition",
        "claim": "Provided the permit is approved, the cooperative will install solar panels and replace the boilers.",
        "composition": "AND",
        "atomCount": 2,
        "together": (("permit", "solar"), ("permit", "boilers")),
        "roles": (("solar", "CONDITIONAL"), ("boilers", "CONDITIONAL")),
    },
    {
        "id": "preserved-negation",
        "claim": "The rover never entered the western crater.",
        "composition": "SINGLE",
        "atomCount": 1,
        "together": (("never", "entered", "western crater"),),
    },
    {
        "id": "explicit-disjunction",
        "claim": "The key is inside the cabinet or beneath the desk.",
        "composition": "OR",
        "atomCount": 2,
        "together": (("key", "cabinet"), ("key", "desk")),
        "separate": (("cabinet", "desk"),),
    },
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_claim(text: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", text.casefold(), re.UNICODE))


def prompt_example_claims() -> set[str]:
    """Read prompt examples so evaluation cannot silently test seen claims."""
    source = DECOMPOSITION_PROMPT_SOURCE.read_text(encoding="utf-8")
    examples = source.partition("Examples:\n")[2].partition(
        "\n\nReturn only JSON"
    )[0]
    return {
        normalized_claim(match.group(1))
        for match in re.finditer(r"^Claim: (.+)$", examples, re.MULTILINE)
    }


def corpus_claims(catalogs: tuple[Path, ...]) -> dict[str, str]:
    claims: dict[str, str] = {}
    for path in catalogs:
        for case in read_json(path):
            claims[case["id"]] = case["claim"]
    return claims


def baseline_runs(runs_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        path.stem: read_json(path)
        for path in sorted(runs_dir.glob("*.json"))
    }


def utf16_offset(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le")) // 2


def grounding_errors(claim: str, result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for atom in result.get("atoms", []):
        source = atom.get("sourceText", "")
        start = claim.find(source)
        if start < 0:
            errors.append(f"{atom.get('id')}: sourceText is not in the claim")
            continue
        if atom.get("start") != utf16_offset(claim, start):
            errors.append(f"{atom.get('id')}: start offset is not source-grounded")
        if atom.get("end") != utf16_offset(claim, start + len(source)):
            errors.append(f"{atom.get('id')}: end offset is not source-grounded")
    return errors


def atom_with(result: dict[str, Any], term: str) -> dict[str, Any] | None:
    needle = term.casefold()
    return next(
        (atom for atom in result.get("atoms", []) if needle in atom.get("text", "").casefold()),
        None,
    )


def challenge_errors(challenge: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors = grounding_errors(challenge["claim"], result)
    atoms = result.get("atoms", [])
    if result.get("composition") != challenge["composition"]:
        errors.append(f"expected composition {challenge['composition']}")
    if len(atoms) != challenge["atomCount"]:
        errors.append(f"expected {challenge['atomCount']} obligations")
    for terms in challenge.get("together", ()):
        if not any(
            all(term.casefold() in atom.get("text", "").casefold() for term in terms)
            for atom in atoms
        ):
            errors.append("terms must remain together: " + ", ".join(terms))
    for left, right in challenge.get("separate", ()):
        left_atom = atom_with(result, left)
        right_atom = atom_with(result, right)
        if left_atom is None or right_atom is None or left_atom is right_atom:
            errors.append(f"terms must be in separate obligations: {left}, {right}")
    for anchor, role in challenge.get("roles", ()):
        atom = atom_with(result, anchor)
        if atom is None or atom.get("role") != role:
            errors.append(f"{anchor!r} must use role {role}")
    for anchor, pattern in challenge.get("forbiddenIn", ()):
        atom = atom_with(result, anchor)
        if atom is None or re.search(pattern, atom.get("text", ""), re.IGNORECASE):
            errors.append(f"{anchor!r} obligation contains unresolved reference {pattern}")
    warning_codes = {warning.get("code") for warning in result.get("warnings", [])}
    remaining = warning_codes & HIGH_SEVERITY_WARNINGS
    if remaining:
        errors.append("high-severity warnings: " + ", ".join(sorted(remaining)))
    return errors


async def request_decomposition(client: Any, claim: str) -> dict[str, Any]:
    response = await client.post("/api/v1/decompose", json={"claim": claim})
    response.raise_for_status()
    return response.json()


async def run(args: argparse.Namespace) -> int:
    try:
        import httpx
    except ImportError as error:
        raise RuntimeError("Run ./run-verinice --prepare before evaluating.") from error

    claims = corpus_claims(DEFAULT_CATALOGS)
    baselines = baseline_runs(args.runs)
    examples = prompt_example_claims()
    challenge_claims = {
        normalized_claim(challenge["claim"]): challenge["id"]
        for challenge in CHALLENGES
    }
    leaked_challenges = sorted(examples & set(challenge_claims))
    if leaked_challenges:
        leaked_ids = ", ".join(challenge_claims[claim] for claim in leaked_challenges)
        raise RuntimeError(f"Semantic challenges duplicate prompt examples: {leaked_ids}")
    demo_claims = {normalized_claim(claim): case_id for case_id, claim in claims.items()}
    leaked_examples = sorted(examples & set(demo_claims))
    if leaked_examples:
        leaked_ids = ", ".join(demo_claims[claim] for claim in leaked_examples)
        raise RuntimeError(f"Prompt examples duplicate demo claims: {leaked_ids}")
    # Two retired showcase recordings remain useful single-claim shadow cases.
    # Recover their claims only when the recording proves that its one atom is
    # the untouched whole claim; never guess a claim from a decomposition.
    for case_id, baseline in baselines.items():
        atoms = baseline.get("atoms", [])
        if case_id not in claims and len(atoms) == 1 and atoms[0].get("start") == 0:
            source = atoms[0].get("sourceText", "")
            if source and atoms[0].get("text") == source:
                claims[case_id] = source
    if len(claims) != 49 or len(baselines) != 49:
        raise RuntimeError(
            f"Expected the 49-case shadow corpus; found {len(claims)} claims and "
            f"{len(baselines)} baseline runs."
        )

    candidates: dict[str, dict[str, Any]] = {}
    challenge_results: dict[str, dict[str, Any]] = {}
    semaphore = asyncio.Semaphore(args.concurrency)
    completed = 0
    total = len(claims) + len(CHALLENGES)

    async def evaluate_one(client: Any, case_id: str, claim: str) -> tuple[str, dict[str, Any]]:
        nonlocal completed
        async with semaphore:
            result = await request_decomposition(client, claim)
        completed += 1
        print(f"[{completed}/{total}] {case_id}", flush=True)
        return case_id, result

    async with httpx.AsyncClient(base_url=args.api, timeout=args.timeout) as client:
        candidate_pairs = await asyncio.gather(
            *(evaluate_one(client, case_id, claim) for case_id, claim in claims.items())
        )
        candidates.update(candidate_pairs)
        challenge_pairs = await asyncio.gather(
            *(
                evaluate_one(client, challenge["id"], challenge["claim"])
                for challenge in CHALLENGES
            )
        )
        challenge_results.update(challenge_pairs)

    failures: list[str] = []
    for case_id, result in candidates.items():
        failures.extend(
            f"{case_id}: {error}" for error in grounding_errors(claims[case_id], result)
        )
    for challenge in CHALLENGES:
        failures.extend(
            f"challenge/{challenge['id']}: {error}"
            for error in challenge_errors(challenge, challenge_results[challenge["id"]])
        )

    baseline_mean = statistics.fmean(len(run["atoms"]) for run in baselines.values())
    candidate_mean = statistics.fmean(len(run["atoms"]) for run in candidates.values())
    baseline_high = sum(
        warning.get("code") in HIGH_SEVERITY_WARNINGS
        for run in baselines.values()
        for warning in run.get("warnings", [])
    )
    candidate_high = sum(
        warning.get("code") in HIGH_SEVERITY_WARNINGS
        for run in candidates.values()
        for warning in run.get("warnings", [])
    )
    baseline_fallbacks = sum(
        any(warning.get("code") == "DECOMPOSITION_FALLBACK" for warning in run.get("warnings", []))
        for run in baselines.values()
    )
    candidate_fallbacks = sum(
        any(warning.get("code") == "DECOMPOSITION_FALLBACK" for warning in run.get("warnings", []))
        for run in candidates.values()
    )
    repairs = sum(
        any(warning.get("code") == "DECOMPOSITION_REPAIRED" for warning in run.get("warnings", []))
        for run in candidates.values()
    )
    candidate_warning_cases = {
        case_id: [warning.get("code") for warning in run.get("warnings", [])]
        for case_id, run in candidates.items()
        if any(
            warning.get("code") in HIGH_SEVERITY_WARNINGS
            for warning in run.get("warnings", [])
        )
    }
    if candidate_fallbacks > baseline_fallbacks:
        failures.append("fallback count increased")
    if candidate_high > baseline_high:
        failures.append("high-severity warning count increased")
    if candidate_mean > baseline_mean * 1.10:
        failures.append("mean obligation count increased by more than 10%")
    if repairs / len(candidates) > 0.10:
        failures.append("conditional repair rate exceeded 10%")

    report = {
        "cases": len(candidates),
        "challenges": len(CHALLENGES),
        "baselineMeanAtoms": round(baseline_mean, 3),
        "candidateMeanAtoms": round(candidate_mean, 3),
        "baselineFallbacks": baseline_fallbacks,
        "candidateFallbacks": candidate_fallbacks,
        "baselineHighSeverityWarnings": baseline_high,
        "candidateHighSeverityWarnings": candidate_high,
        "repairs": repairs,
        "repairRate": round(repairs / len(candidates), 3),
        "candidateWarningCases": candidate_warning_cases,
        "failures": failures,
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate live claim decomposition quality")
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--concurrency", type=int, choices=range(1, 5), default=1)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
