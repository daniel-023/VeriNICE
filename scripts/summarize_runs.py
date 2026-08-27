#!/usr/bin/env python3
"""Summarise recorded VeriGraph runs against the AVeriTeC reference labels.

This is a descriptive summary of the demonstration set, not a benchmark
evaluation. Reference labels are dataset metadata: they never enter the
pipeline, and nothing here is calibrated, tuned, or selected against them.

    python3 scripts/summarize_runs.py                    # markdown to stdout
    python3 scripts/summarize_runs.py --output artifacts/evaluation-table.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = ROOT / "data" / "walkthrough" / "runs"
DEFAULT_CATALOG = ROOT / "data" / "demo" / "averitec" / "catalog.json"

LABELS = ("SUPPORTED", "REFUTED", "NOT_ENOUGH_EVIDENCE", "CONFLICTING_EVIDENCE")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit(f"Could not read {path}: {error}")


def recorded_verdict(run: dict[str, Any]) -> str:
    """Return the authoritative aggregation result from a schema-v2 recording."""
    recorded = run.get("verdict")
    if isinstance(recorded, dict) and recorded.get("verdict") in LABELS:
        return recorded["verdict"]
    raise SystemExit(
        f"Recorded run {run.get('caseId', '<unknown>')} has no valid schema-v1 aggregation result. "
        "Re-record the walkthrough."
    )


def render(runs_dir: Path, catalog_path: Path) -> str:
    catalog = read_json(catalog_path)
    reference = {case["id"]: case["label"] for case in catalog}
    run_paths = sorted(runs_dir.glob("*.json"))
    if not run_paths:
        raise SystemExit(
            f"No recorded runs in {runs_dir}. Run ./run-verigraph --record-walkthrough first."
        )

    rows: list[tuple[str, int, str, str, str]] = []
    relations = Counter()
    atom_counts = Counter()
    predicted = Counter()
    confusion: Counter[tuple[str, str]] = Counter()
    schema_versions = Counter()
    typed_roles = Counter()
    decomposition_quality = Counter()

    for path in run_paths:
        run = read_json(path)
        case_id = run["caseId"]
        schema_versions[run.get("schemaVersion", "pre-v2")] += 1
        atom_counts[len(run["atoms"])] += 1
        for atom in run["atoms"]:
            typed_roles[atom.get("role", "untyped")] += 1
        linguistics = run.get("linguistics", {})
        summaries = linguistics.get("summaries", []) if isinstance(linguistics, dict) else []
        claim_warnings = set(linguistics.get("claimWarnings", [])) if isinstance(linguistics, dict) else set()
        decomposition_warnings = {item.get("code") for item in run.get("warnings", []) if isinstance(item, dict)}
        atom_warnings = {
            warning
            for summary in summaries
            if isinstance(summary, dict)
            for warning in summary.get("warnings", [])
        }
        decomposition_quality["claims"] += 1
        decomposition_quality["obligations"] += len(run["atoms"])
        decomposition_quality["atomicity_pass"] += sum(
            1 for summary in summaries
            if "MULTIPLE_PROPOSITION_FRAMES" not in set(summary.get("warnings", []))
        )
        decomposition_quality["sufficiency_pass"] += sum(
            1 for summary in summaries
            if summary.get("analysisStatus") == "complete"
            and not ({"UNRESOLVED_SUBJECT", "UNRESOLVED_PREDICATE"} & set(summary.get("warnings", [])))
        )
        decomposition_quality["coverage_pass"] += not bool(
            {"UNDER_DECOMPOSED"} & decomposition_warnings
            or {"CLAIM_FRAME_NOT_COVERED"} & claim_warnings
        )
        decomposition_quality["fabrication_pass"] += not bool(
            {"SOURCE_TEXT_NOT_FOUND", "SOURCE_TEXT_AMBIGUOUS"} & decomposition_warnings
        )
        normalized_atoms = [" ".join(atom.get("text", "").casefold().split()) for atom in run["atoms"]]
        decomposition_quality["redundancy_pass"] += len(normalized_atoms) == len(set(normalized_atoms))
        decomposition_quality["readability_pass"] += sum(
            1 for atom in run["atoms"]
            if atom.get("text", "").strip().endswith((".", "?", "!"))
            and len(atom.get("text", "").split()) >= 3
        )
        decomposition_quality["audit_warning_count"] += len(claim_warnings | atom_warnings)
        for item in run["classifications"]:
            for relation in item["relations"]:
                relations[relation["relation"]] += 1
        verdict = recorded_verdict(run)
        label = reference.get(case_id, "UNKNOWN")
        predicted[verdict] += 1
        confusion[(label, verdict)] += 1
        composition = run.get("composition") or ("AND" if len(run["atoms"]) > 1 else "SINGLE")
        rows.append((case_id, len(run["atoms"]), composition, label, verdict))

    agreement = sum(1 for _, _, _, label, verdict in rows if label == verdict)
    total = len(rows)
    lines: list[str] = []
    add = lines.append

    add("# Demonstration set summary")
    add("")
    add("<!-- Generated by scripts/summarize_runs.py. Do not edit by hand. -->")
    add("")
    add("This is a descriptive summary of the recorded demonstration set. It is not a")
    add("benchmark evaluation: there is no held-out split, no calibration, no tuned")
    add("threshold, and no comparison system. AVeriTeC reference labels are dataset")
    add("metadata and never enter the pipeline.")
    add("")
    add("## Set composition")
    add("")
    add("| Property | Value |")
    add("| --- | ---: |")
    add(f"| Cases recorded | {total} |")
    add(f"| Run schema versions | {', '.join(f'{k} ({v})' for k, v in sorted(schema_versions.items(), key=str))} |")
    for label in LABELS:
        add(f"| Reference `{label}` | {sum(1 for _, _, _, ref, _ in rows if ref == label)} |")
    add(f"| Obligations per case | {min(atom_counts)}–{max(atom_counts)} |")
    add("")

    add("## Obligation typing")
    add("")
    add("| Role | Obligations |")
    add("| --- | ---: |")
    for role, count in typed_roles.most_common():
        add(f"| `{role}` | {count} |")
    add("")

    add("## Decomposition quality diagnostics")
    add("")
    add("These deterministic diagnostics use FactLens-aligned dimensions. They are")
    add("auditable proxies, not human ratings or the FactLens model evaluator.")
    add("")
    obligations = decomposition_quality["obligations"] or 1
    claims = decomposition_quality["claims"] or 1
    add("| Dimension | Passing | Unit |")
    add("| --- | ---: | --- |")
    add(f"| Atomicity | {decomposition_quality['atomicity_pass']}/{obligations} | obligations |")
    add(f"| Sufficiency | {decomposition_quality['sufficiency_pass']}/{obligations} | obligations |")
    add(f"| Coverage | {decomposition_quality['coverage_pass']}/{claims} | claims |")
    add(f"| Fabrication guard | {decomposition_quality['fabrication_pass']}/{claims} | claims |")
    add(f"| Non-redundancy | {decomposition_quality['redundancy_pass']}/{claims} | claims |")
    add(f"| Readability | {decomposition_quality['readability_pass']}/{obligations} | obligations |")
    add(f"| Linguistic audit warnings | {decomposition_quality['audit_warning_count']} | warnings |")
    add("")

    add("## Sentence-level NLI relations")
    add("")
    total_relations = sum(relations.values()) or 1
    add("| Relation | Count | Share |")
    add("| --- | ---: | ---: |")
    for relation in ("ENTAILMENT", "CONTRADICTION", "NEUTRAL"):
        count = relations[relation]
        add(f"| `{relation}` | {count} | {count / total_relations:.1%} |")
    add("")

    add("## Verdict against the reference label")
    add("")
    add(f"Agreement: **{agreement}/{total}** ({agreement / total:.1%}).")
    add("")
    add("| Reference \\ verdict | " + " | ".join(f"`{label}`" for label in LABELS) + " |")
    add("| --- | " + " | ".join("---:" for _ in LABELS) + " |")
    for label in LABELS:
        cells = " | ".join(str(confusion[(label, verdict)]) for verdict in LABELS)
        add(f"| `{label}` | {cells} |")
    add("")

    add("## Per case")
    add("")
    add("| Case | Obligations | Composition | Reference | Verdict | |")
    add("| --- | ---: | --- | --- | --- | --- |")
    for case_id, atoms, composition, label, verdict in rows:
        mark = "match" if label == verdict else ""
        add(f"| `{case_id}` | {atoms} | {composition} | {label} | {verdict} | {mark} |")
    add("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, help="Write markdown here instead of stdout.")
    args = parser.parse_args()

    report = render(args.runs, args.catalog)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
