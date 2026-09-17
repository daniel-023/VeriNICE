#!/usr/bin/env python3
"""Summarise recorded VeriNICE runs against the AVeriTeC reference labels.

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
import statistics
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
    """Return the rule-derived verdict from a schema-v7 recording."""
    recorded = run.get("verdict")
    if isinstance(recorded, dict) and recorded.get("verdict") in LABELS:
        return recorded["verdict"]
    raise SystemExit(
        f"Recorded run {run.get('caseId', '<unknown>')} has no valid recorded verdict. "
        "Re-record the walkthrough."
    )


def assessment_only_verdict(run: dict[str, Any]) -> str:
    """Apply composition to Qwen-selected relations without symbolic rule results."""
    states: list[str] = []
    for item in run.get("assessment", {}).get("obligations", []):
        decisive = item.get("sufficiency") == "SUFFICIENT"
        support = decisive and bool(item.get("supportSpanIds"))
        refute = decisive and bool(item.get("refuteSpanIds"))
        states.append("BOTH" if support and refute else "SUPPORT" if support else "REFUTE" if refute else "NONE")
    composition = run.get("composition", "SINGLE")
    if not states:
        verdict = "NOT_ENOUGH_EVIDENCE"
    elif composition == "AND":
        verdict = "REFUTED" if "REFUTE" in states else "CONFLICTING_EVIDENCE" if "BOTH" in states else "SUPPORTED" if all(state == "SUPPORT" for state in states) else "NOT_ENOUGH_EVIDENCE"
    elif composition == "OR":
        verdict = "SUPPORTED" if "SUPPORT" in states else "CONFLICTING_EVIDENCE" if "BOTH" in states else "REFUTED" if all(state == "REFUTE" for state in states) else "NOT_ENOUGH_EVIDENCE"
    else:
        verdict = {"SUPPORT": "SUPPORTED", "REFUTE": "REFUTED", "BOTH": "CONFLICTING_EVIDENCE"}.get(states[0], "NOT_ENOUGH_EVIDENCE")
    if run.get("assessment", {}).get("materialOmission", {}).get("detected"):
        verdict = "CONFLICTING_EVIDENCE"
    return verdict


def render(runs_dir: Path, catalog_path: Path) -> str:
    catalog = read_json(catalog_path)
    reference = {case["id"]: case["label"] for case in catalog}
    run_paths = sorted(runs_dir.glob("*.json"))
    if not run_paths:
        raise SystemExit(
            f"No recorded runs in {runs_dir}. Run ./run-verinice --record-walkthrough first."
        )

    rows: list[tuple[str, int, str, str, str, str]] = []
    relations = Counter()
    relation_effects = Counter()
    symbolic = Counter()
    atom_counts = Counter()
    predicted = Counter()
    confusion: Counter[tuple[str, str]] = Counter()
    schema_versions = Counter()
    typed_roles = Counter()
    timings: dict[str, list[float]] = {}

    for path in run_paths:
        run = read_json(path)
        case_id = run["caseId"]
        schema_versions[run.get("schemaVersion", "pre-v2")] += 1
        atom_counts[len(run["atoms"])] += 1
        for atom in run["atoms"]:
            typed_roles[atom.get("role", "untyped")] += 1
        for stage, seconds in run.get("timingsSeconds", {}).items():
            if isinstance(seconds, (int, float)) and seconds >= 0:
                timings.setdefault(stage, []).append(float(seconds))
        run_relation_counts = Counter()
        for item in run.get("assessment", {}).get("obligations", []):
            run_relation_counts["SUPPORTS"] += len(item.get("supportSpanIds", []))
            run_relation_counts["REFUTES"] += len(item.get("refuteSpanIds", []))
            run_relation_counts["CONTEXT"] += len(item.get("contextSpanIds", []))
            selected_decisive = len(item.get("supportSpanIds", [])) + len(item.get("refuteSpanIds", []))
            relation_effects["DECISIVE" if item.get("sufficiency") == "SUFFICIENT" else "PROVISIONAL"] += selected_decisive
            relation_effects["SCOPE_MISMATCH"] += sum(
                check.get("status") == "MISMATCH" for check in item.get("scopeChecks", [])
            )
        relations.update(run_relation_counts)
        selected_span_count = sum(run_relation_counts.values())
        relations["NOT_SELECTED"] += max(0, sum(len(item.get("spans", [])) for item in run.get("evidence", [])) - selected_span_count)
        for execution in run.get("reasoning", []):
            symbolic[(execution.get("operator", "UNKNOWN"), execution.get("status", "UNKNOWN"))] += 1
        verdict = recorded_verdict(run)
        baseline = assessment_only_verdict(run)
        label = reference.get(case_id, "UNKNOWN")
        predicted[verdict] += 1
        confusion[(label, verdict)] += 1
        composition = run.get("composition") or ("AND" if len(run["atoms"]) > 1 else "SINGLE")
        rows.append((case_id, len(run["atoms"]), composition, label, verdict, baseline))

    agreement = sum(1 for _, _, _, label, verdict, _ in rows if label == verdict)
    baseline_agreement = sum(1 for _, _, _, label, _, baseline in rows if label == baseline)
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
        add(f"| Reference `{label}` | {sum(1 for _, _, _, ref, _, _ in rows if ref == label)} |")
    add(f"| Obligations per case | {min(atom_counts)}–{max(atom_counts)} |")
    add("")

    add("## Obligation typing")
    add("")
    add("| Role | Obligations |")
    add("| --- | ---: |")
    for role, count in typed_roles.most_common():
        add(f"| `{role}` | {count} |")
    add("")

    add("## Assessed evidence relations")
    add("")
    total_relations = sum(relations.values()) or 1
    add("| Relation | Count | Share |")
    add("| --- | ---: | ---: |")
    for relation in ("SUPPORTS", "REFUTES", "CONTEXT", "NOT_SELECTED"):
        count = relations[relation]
        add(f"| `{relation}` | {count} | {count / total_relations:.1%} |")
    add("")
    add(f"Decisive support/refute selections: **{relation_effects['DECISIVE']}**. ")
    add(f"Provisional support/refute selections: **{relation_effects['PROVISIONAL']}**. ")
    add(f"Candidates excluded for an explicit jurisdiction mismatch: **{relation_effects['SCOPE_MISMATCH']}**.")
    add("")

    add("## Symbolic operator executions")
    add("")
    add("| Operator | Status | Count |")
    add("| --- | --- | ---: |")
    for (operator, status), count in sorted(symbolic.items()):
        add(f"| `{operator}` | `{status}` | {count} |")
    add("")

    if timings:
        add("## Recorded latency")
        add("")
        add("Wall-clock seconds from the local recording laptop; these are descriptive,")
        add("not hardware-normalized benchmark measurements.")
        add("")
        add("| Stage | Median | Mean | Maximum | Cases |")
        add("| --- | ---: | ---: | ---: | ---: |")
        for stage in ("decomposition", "retrieval", "evidenceAssessment", "symbolicReasoning", "aggregation", "total"):
            values = timings.get(stage, [])
            if values:
                add(
                    f"| `{stage}` | {statistics.median(values):.2f} | "
                    f"{statistics.fmean(values):.2f} | {max(values):.2f} | {len(values)} |"
                )
        add("")

    add("## Predicted verdict against the reference label")
    add("")
    add(f"Agreement: **{agreement}/{total}** ({agreement / total:.1%}).")
    add(f"Qwen assessment-only agreement: **{baseline_agreement}/{total}** ({baseline_agreement / total:.1%}).")
    add("")
    add("| Reference \\ status | " + " | ".join(f"`{label}`" for label in LABELS) + " |")
    add("| --- | " + " | ".join("---:" for _ in LABELS) + " |")
    for label in LABELS:
        cells = " | ".join(str(confusion[(label, verdict)]) for verdict in LABELS)
        add(f"| `{label}` | {cells} |")
    add("")

    add("## Per case")
    add("")
    add("| Case | Obligations | Composition | Reference | Qwen only | Qwen + symbolic | |")
    add("| --- | ---: | --- | --- | --- | --- | --- |")
    for case_id, atoms, composition, label, verdict, baseline in rows:
        mark = "match" if label == verdict else ""
        add(f"| `{case_id}` | {atoms} | {composition} | {label} | {baseline} | {verdict} | {mark} |")
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
