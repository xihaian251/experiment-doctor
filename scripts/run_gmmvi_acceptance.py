#!/usr/bin/env python3
"""Golden acceptance run for the gmmvi Experiment 3 adapter.

Read-only.  Nothing in this file runs by default and no path is baked in: pass the
repository and the artifact directory explicitly, e.g.

    python scripts/run_gmmvi_acceptance.py \
        --repo /path/to/gmmvi_reproducibility \
        --data-root /path/to/extracted/evaluations/results \
        --reported-table examples/gmmvi_reported_table.json \
        -o acceptance.json

The expected numbers below are the Phase 0 forensic oracle.  They are test
expectations only: they exist in this file and nowhere under ``src/``, and the tool
recomputes every one of them from the project's own artifacts.  The published-table
transcription is not read here either -- it is handed to the adapter as an input file,
so a comparison can only match if the recomputation from run CSVs lands on it.

Exit code is 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from experiment_doctor.adapters.gmmvi import GMMVIAdapter  # noqa: E402
from experiment_doctor.audit import audit_project  # noqa: E402
from experiment_doctor.provenance import ProvenanceStatus  # noqa: E402
from experiment_doctor.scanner import scan_project  # noqa: E402
from experiment_doctor.schema import (  # noqa: E402
    ComparisonStatus,
    ExperimentProject,
    FamilyKind,
    RunStatus,
)

# ---- Phase 0 oracle (expectations, never inputs) -------------------------------
TOTAL_RUNS = 3483
FAMILIES = 205
EVAL_FAMILIES = 107
SEARCH_FAMILIES = 98
EVALUATION_RUNS = 1090
INCLUDED_RUNS = 1068
EXCLUDED_RUNS = 22
AGGREGATIONS = 219

NORMAL_FAMILY = "Planar4_EVAL/samtrux_planar_4"
EXCLUDED_FAMILY = "Planar4_EVAL/sepyfux_planar_4"
EXCLUDED_FAMILY_INCLUDED = 5
EXCLUDED_FAMILY_TOTAL_SLOTS = 10
FAMILIES_WITH_README_CLAIM = {
    "Planar4_EVAL/sepyfux_planar_4",
    "Planar4_EVAL/sepyrux_planar_4",
    "Planar4_EVAL/zamtrux_planar_4",
    "TALOS_EVAL/sepyfux_talos",
    "TALOS_EVAL/sepyrux_talos",
}
ALWAYS_UNKNOWN_FIELDS = (
    "seed",
    "code_commit",
    "tracker_run_id",
    "parent_run_id",
    "start_time",
    "end_time",
    "repetition_index",
)


def _check(
    name: str, passed: bool, expected: Any, observed: Any, detail: str = ""
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "expected": expected,
        "observed": observed,
        "detail": detail,
    }


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _direction_gaps(project: ExperimentProject) -> list[str]:
    """Evaluation families holding a metric whose direction is not code-evidenced."""
    gaps: list[str] = []
    for family in project.families:
        if family.kind is not FamilyKind.EVALUATION:
            continue
        for run in project.runs_of(family.family_id):
            if any(
                metric.direction.status is not ProvenanceStatus.CONFIRMED for metric in run.metrics
            ):
                gaps.append(family.family_id)
                break
    return gaps


def evaluate(project: ExperimentProject) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    runs = project.runs
    eval_families = [f for f in project.families if f.kind is FamilyKind.EVALUATION]
    search_families = [f for f in project.families if f.kind is FamilyKind.HYPERPARAMETER_SEARCH]
    eval_run_ids = {
        run.run_id for family in eval_families for run in project.runs_of(family.family_id)
    }

    checks.append(
        _check("adapter_selected", project.adapter == "gmmvi-exp3", "gmmvi-exp3", project.adapter)
    )
    checks.append(_check("total_runs", len(runs) == TOTAL_RUNS, TOTAL_RUNS, len(runs)))
    checks.append(
        _check("total_families", len(project.families) == FAMILIES, FAMILIES, len(project.families))
    )
    checks.append(
        _check(
            "family_split",
            (len(eval_families), len(search_families)) == (EVAL_FAMILIES, SEARCH_FAMILIES),
            [EVAL_FAMILIES, SEARCH_FAMILIES],
            [len(eval_families), len(search_families)],
        )
    )
    checks.append(
        _check(
            "evaluation_runs",
            len(eval_run_ids) == EVALUATION_RUNS,
            EVALUATION_RUNS,
            len(eval_run_ids),
        )
    )

    included = [r for r in runs if r.included_in_aggregation.value is True]
    excluded = [r for r in runs if r.included_in_aggregation.value is False]
    checks.append(
        _check(
            "membership_counts",
            (len(included), len(excluded)) == (INCLUDED_RUNS, EXCLUDED_RUNS),
            [INCLUDED_RUNS, EXCLUDED_RUNS],
            [len(included), len(excluded)],
            "every membership flag comes from the .csv / .csv.bad suffix on disk",
        )
    )
    statuses = {r.status for r in excluded}
    checks.append(
        _check(
            "excluded_status_vocabulary",
            statuses == {RunStatus.COMPLETED_EXCLUDED},
            [RunStatus.COMPLETED_EXCLUDED.value],
            sorted(status.value for status in statuses),
            "no artifact distinguishes an OOM-killed run from a completed outlier one",
        )
    )

    for field in ALWAYS_UNKNOWN_FIELDS:
        states = {getattr(run, field).status for run in runs}
        values = [getattr(run, field).value for run in runs]
        checks.append(
            _check(
                f"unknown_stays_unknown:{field}",
                states == {ProvenanceStatus.UNKNOWN} and all(value is None for value in values),
                "UNKNOWN with no value, for every run",
                sorted(state.value for state in states),
            )
        )

    checks.append(
        _check(
            "aggregation_records",
            len(project.aggregations) == AGGREGATIONS,
            AGGREGATIONS,
            len(project.aggregations),
        )
    )

    normal = project.family(NORMAL_FAMILY)
    normal_runs = project.runs_of(NORMAL_FAMILY)
    checks.append(
        _check(
            "normal_family",
            normal is not None
            and len(normal_runs) == 10
            and all(run.included_in_aggregation.value is True for run in normal_runs)
            and normal.declared_repetitions.value == 10,
            "10 runs, all included, declared repetitions 10",
            None
            if normal is None
            else [
                len(normal_runs),
                sum(1 for r in normal_runs if r.included_in_aggregation.value),
                normal.declared_repetitions.value,
            ],
        )
    )

    excluded_family = project.family(EXCLUDED_FAMILY)
    ef_runs = project.runs_of(EXCLUDED_FAMILY)
    ef_in = sum(1 for r in ef_runs if r.included_in_aggregation.value is True)
    ef_ex = sum(1 for r in ef_runs if r.included_in_aggregation.value is False)
    checks.append(
        _check(
            "excluded_family_reconstruction",
            excluded_family is not None
            and len(ef_runs) == EXCLUDED_FAMILY_TOTAL_SLOTS
            and (ef_in, ef_ex)
            == (EXCLUDED_FAMILY_INCLUDED, EXCLUDED_FAMILY_TOTAL_SLOTS - EXCLUDED_FAMILY_INCLUDED),
            [
                EXCLUDED_FAMILY_TOTAL_SLOTS,
                EXCLUDED_FAMILY_INCLUDED,
                EXCLUDED_FAMILY_TOTAL_SLOTS - EXCLUDED_FAMILY_INCLUDED,
            ],
            [None if excluded_family is None else len(ef_runs), ef_in, ef_ex],
        )
    )

    records = {record.aggregation_id: record for record in project.aggregations}
    inc = records.get(f"{EXCLUDED_FAMILY}/-elbo@included")
    allc = records.get(f"{EXCLUDED_FAMILY}/-elbo@all_completed")
    checks.append(
        _check(
            "both_memberships_recomputed",
            inc is not None
            and allc is not None
            and inc.n == EXCLUDED_FAMILY_INCLUDED
            and allc.n == EXCLUDED_FAMILY_TOTAL_SLOTS
            and _finite(allc.recomputed_value)
            and _finite(allc.recomputed_spread)
            and allc.membership_rule.status is ProvenanceStatus.INFERRED,
            "included N=5 and all_completed N=10, both recomputed",
            None
            if not (inc and allc)
            else [
                inc.n,
                allc.n,
                allc.recomputed_value,
                allc.recomputed_spread,
                allc.membership_rule.status.value,
            ],
            "the counterfactual membership is INFERRED because the project never aggregated it",
        )
    )

    claimed = {
        run.family_id
        for run in runs
        if run.included_in_aggregation.value is False
        and run.exclusion_reason.status is ProvenanceStatus.SUPPORTED
    }
    checks.append(
        _check(
            "readme_claim_coverage",
            claimed == FAMILIES_WITH_README_CLAIM,
            sorted(FAMILIES_WITH_README_CLAIM),
            sorted(claimed),
            "these are the families the project prose gives a cause for; the typo'd bullet still binds",
        )
    )

    gaps = _direction_gaps(project)
    checks.append(
        _check(
            "metric_direction_evidenced",
            not gaps,
            "no evaluation family with an unevidenced metric direction",
            gaps,
        )
    )

    with_reported = [record for record in project.aggregations if record.has_reported]
    if with_reported:
        matched = [r for r in with_reported if r.comparison_status is ComparisonStatus.MATCH]
        mismatched = [r for r in with_reported if r.comparison_status is ComparisonStatus.MISMATCH]
        checks.append(
            _check(
                "reported_vs_recomputed",
                not mismatched and len(matched) == len(with_reported),
                f"all {len(with_reported)} supplied cells MATCH",
                {
                    "match": len(matched),
                    "mismatch": len(mismatched),
                    "other": len(with_reported) - len(matched) - len(mismatched),
                },
                "counts by comparison status",
            )
        )
    else:
        checks.append(
            _check(
                "reported_vs_recomputed",
                True,
                "skipped: no --reported-table given",
                "comparison stays UNKNOWN",
            )
        )
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--repo", required=True, type=Path, help="gmmvi repository checkout (read-only)"
    )
    parser.add_argument(
        "--data-root", required=True, type=Path, help="directory holding the *_EVAL result folders"
    )
    parser.add_argument(
        "--reported-table", type=Path, default=None, help="published cells to compare against"
    )
    parser.add_argument("-o", "--output", type=Path, default=Path("acceptance.json"))
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    data_root = args.data_root.resolve()
    if not repo.is_dir() or not data_root.is_dir():
        parser.error("--repo and --data-root must both be existing directories")
    try:
        root = Path(os.path.commonpath([str(repo), str(data_root)]))
    except ValueError:  # different drives on Windows: keep the repo as the report root
        root = repo

    adapter = GMMVIAdapter(
        root, repo_root=repo, results_root=data_root, reported_table=args.reported_table
    )
    project = scan_project(root, adapter=adapter)
    audit_project(project)
    checks = evaluate(project)

    passed = sum(1 for check in checks if check["passed"])
    payload = {
        "inputs": {
            "repo": str(repo),
            "data_root": str(data_root),
            "reported_table": str(args.reported_table) if args.reported_table else None,
        },
        "oracle": "Phase 0 forensic reconstruction of gmmvi Experiment 3 (expectations only)",
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
    }
    if args.output.parent != Path(""):
        args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    for check in checks:
        print(f"[{'PASS' if check['passed'] else 'FAIL'}] {check['name']}: {check['observed']}")
    print(f"\n{passed}/{len(checks)} checks passed -> {args.output}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
