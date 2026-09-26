#!/usr/bin/env python3
"""External acceptance run: the TorchSSL adapter against the real public project.

Read-only, and nothing runs by default.  Point it at the clone and the retrieved logs:

    python scripts/run_torchssl_acceptance.py \
        --repo /path/to/acceptance1-torchssl/repo \
        --logs-root /path/to/acceptance1-torchssl/downloads/logs \
        --reported-table examples/torchssl_reported_table.json \
        -o acceptance-torchssl.json

Expectations live here and nowhere under ``src/``.  They are of two kinds:

* structural facts about the selected subset (two families, three seeds each), which
  the plan fixes before any artifact is read;
* arithmetic recomputed independently in this file with :mod:`statistics`, from the
  per-run metric values the adapter extracted, so a match means the adapter's numbers
  survive a second implementation rather than being echoed back.

The published cells are an *input* handed to the adapter, never read as an oracle here:
this script checks that an independent recomputation rounds onto them and that the
spread the project's prose names a "standard error" would NOT.

Exit code is 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from experiment_doctor.adapters.torchssl import (  # noqa: E402
    METRIC_BEST,
    METRIC_LAST,
    TorchSSLAdapter,
)
from experiment_doctor.audit import audit_project  # noqa: E402
from experiment_doctor.provenance import ProvenanceStatus  # noqa: E402
from experiment_doctor.scanner import scan_project, select_adapter  # noqa: E402
from experiment_doctor.schema import (  # noqa: E402
    ComparisonStatus,
    ExperimentProject,
    MetricDirection,
    RunStatus,
    SpreadBasis,
    TerminationCause,
)

# ---- the planned subset (expectations, never inputs) ---------------------------
FAMILIES = ["fixmatch/cifar10_250", "flexmatch/cifar10_250"]
SEEDS = [0, 1, 2]
RUNS = {
    family: [f"{family.split('/')[0]}_cifar10_250_{seed}" for seed in SEEDS] for family in FAMILIES
}
#: Keys the log records per run but which are run bookkeeping, not experiment identity.
PER_RUN_KEYS = {"seed", "save_name", "c", "dist_url"}
#: Published CIFAR-10 / 250-label cells, for the arithmetic the prose invites.
PUBLISHED_DECIMALS = 2


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


def _metric(run: Any, name: str) -> Any:
    return next(record for record in run.metrics if record.name == name)


def _values(project: ExperimentProject, family: str, metric_name: str) -> list[float]:
    return [
        float(_metric(run, metric_name).value.value)
        for run in project.runs
        if run.family_id == family and _metric(run, metric_name).value.has_value
    ]


def evaluate(project: ExperimentProject, logs_root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    result = audit_project(project)
    runs = {run.run_id: run for run in project.runs}

    checks.append(
        _check("adapter_selected", project.adapter == "torchssl", "torchssl", project.adapter)
    )
    auto, score = select_adapter(Path(project.root))
    checks.append(
        _check(
            "adapter_auto_detected",
            auto.name == "torchssl" and score >= 0.9,
            ["torchssl", True],
            [auto.name, score >= 0.9],
            detail=f"detection score {score:.2f}",
        )
    )
    checks.append(
        _check(
            "selected_subset",
            [family.family_id for family in project.families] == FAMILIES,
            FAMILIES,
            [family.family_id for family in project.families],
            detail="exactly the two planned methods on CIFAR-10 / 250 labels, nothing else",
        )
    )
    checks.append(
        _check(
            "runs_per_family",
            all(len(project.runs_of(family)) == 3 for family in FAMILIES),
            3,
            {family: len(project.runs_of(family)) for family in FAMILIES},
        )
    )
    checks.append(
        _check(
            "run_identity",
            sorted(runs) == sorted(id_ for family in FAMILIES for id_ in RUNS[family]),
            sorted(id_ for family in FAMILIES for id_ in RUNS[family]),
            sorted(runs),
        )
    )
    checks.append(
        _check(
            "runs_completed",
            all(run.status is RunStatus.COMPLETED_INCLUDED for run in project.runs),
            "COMPLETED_INCLUDED",
            sorted({run.status.value for run in project.runs}),
        )
    )

    # -- seeds: this project records them, and the tool must say CONFIRMED
    seed_map = {run.run_id: run.seed for run in project.runs}
    checks.append(
        _check(
            "seeds_confirmed_from_the_log",
            all(field.status is ProvenanceStatus.CONFIRMED for field in seed_map.values()),
            "CONFIRMED",
            sorted({field.status.value for field in seed_map.values()}),
            detail="the Arguments dump inside each log, not the directory name",
        )
    )
    checks.append(
        _check(
            "seed_values_are_the_three_recorded_seeds",
            all(
                seed_map[run_id].value == SEEDS[index]
                for family in FAMILIES
                for index, run_id in enumerate(RUNS[family])
            ),
            SEEDS,
            {run_id: seed_map[run_id].value for run_id in sorted(seed_map)},
        )
    )
    cited = sorted({str(field.source.path) for field in seed_map.values() if field.source})
    checks.append(
        _check(
            "seeds_cite_a_log_file",
            len(cited) == 6 and all("log.txt" in path for path in cited),
            "one log.txt per run",
            cited,
        )
    )
    seeds_audit = {item.family_id: item for item in result.seeds}
    checks.append(
        _check(
            "seed_check_reports_no_gap",
            all(
                item.runs_with_unknown_seed == 0
                and item.runs_with_conflicting_seed == 0
                and item.distinct_seeds == 3
                for item in seeds_audit.values()
            ),
            {"unknown": 0, "conflicting": 0, "distinct": 3},
            {
                family: [
                    item.runs_with_unknown_seed,
                    item.runs_with_conflicting_seed,
                    item.distinct_seeds,
                ]
                for family, item in seeds_audit.items()
            },
        )
    )

    # -- run identity across the three seeds
    identity = {item.family_id: item for item in result.identity}
    checks.append(
        _check(
            "family_identity_consistent",
            all(item.status == "CONSISTENT" for item in identity.values()),
            "CONSISTENT",
            {family: item.status for family, item in identity.items()},
        )
    )
    diffs: dict[str, set[str]] = {}
    for family in FAMILIES:
        configs = [runs[run_id].resolved_config.value for run_id in RUNS[family]]
        keys = [set(config or {}) for config in configs]
        reference = keys[0] if keys else set()
        diffs[family] = set().union(*(key ^ reference for key in keys))
        checks.append(
            _check(
                f"config_present_and_confirmed[{family}]",
                all(
                    runs[run_id].resolved_config.status is ProvenanceStatus.CONFIRMED
                    for run_id in RUNS[family]
                ),
                "CONFIRMED",
                sorted({runs[run_id].resolved_config.status.value for run_id in RUNS[family]}),
            )
        )
    checks.append(
        _check(
            "effective_config_identical_once_per_run_keys_are_removed",
            all(not difference for difference in diffs.values()),
            [],
            {family: sorted(difference) for family, difference in diffs.items()},
            detail="every argument except the four below is byte-identical across the seeds, so the "
            "three runs are repetitions of one configuration",
        )
    )
    withheld_note = " ".join(
        str(runs[run_id].resolved_config.confidence_note)
        for family in FAMILIES
        for run_id in [RUNS[family][0]]
    )
    checks.append(
        _check(
            "per_run_keys_are_withheld_and_documented",
            all(key in withheld_note for key in sorted(PER_RUN_KEYS)),
            sorted(PER_RUN_KEYS),
            [key for key in sorted(PER_RUN_KEYS) if key in withheld_note],
            detail="seed, run id and config path live on their own fields; dist_url is a launcher "
            "port allocation (scripts/config_generator.py)",
        )
    )

    # -- what the tool must refuse to assert
    checks.append(
        _check(
            "code_commit_stays_unknown",
            all(
                run.code_commit.status is ProvenanceStatus.UNKNOWN and not run.code_commit.has_value
                for run in project.runs
            ),
            "UNKNOWN",
            sorted({run.code_commit.status.value for run in project.runs}),
            detail="no artifact records the commit; the clone HEAD does not stand in for it",
        )
    )
    checks.append(
        _check(
            "environment_declared_not_confirmed",
            all(run.environment.status is ProvenanceStatus.SUPPORTED for run in project.runs),
            "SUPPORTED",
            sorted({run.environment.status.value for run in project.runs}),
            detail=str(next(iter(runs.values())).environment.value),
        )
    )
    checks.append(
        _check(
            "command_and_repetition_index_unknown",
            all(
                run.command.status is ProvenanceStatus.UNKNOWN
                and run.repetition_index.status is ProvenanceStatus.UNKNOWN
                for run in project.runs
            ),
            ["UNKNOWN", "UNKNOWN"],
            sorted({run.command.status.value for run in project.runs})
            + sorted({run.repetition_index.status.value for run in project.runs}),
        )
    )
    checks.append(
        _check(
            "entrypoint_inferred_not_confirmed",
            all(run.entrypoint.status is ProvenanceStatus.INFERRED for run in project.runs),
            "INFERRED",
            sorted({run.entrypoint.status.value for run in project.runs}),
            detail="the README documents the invocation; the logs do not record it",
        )
    )

    # -- best vs last
    directions = {record.direction.status.value for run in project.runs for record in run.metrics}
    checks.append(
        _check(
            "metric_direction_confirmed_from_code",
            all(
                _metric(run, name).direction.value is MetricDirection.MAXIMIZE
                and _metric(run, name).direction.status is ProvenanceStatus.CONFIRMED
                for run in project.runs
                for name in (METRIC_BEST, METRIC_LAST)
            ),
            "CONFIRMED/MAXIMIZE",
            sorted(directions),
        )
    )
    gaps = {
        family: [
            round(
                _metric(runs[id_], METRIC_BEST).value.value
                - _metric(runs[id_], METRIC_LAST).value.value,
                4,
            )
            for id_ in RUNS[family]
        ]
        for family in FAMILIES
    }
    checks.append(
        _check(
            "best_is_never_below_last",
            all(value >= 0 for values in gaps.values() for value in values),
            ">= 0",
            gaps,
        )
    )
    checks.append(
        _check(
            "selection_policy_moves_the_number",
            all(
                _values(project, family, METRIC_BEST)
                and statistics.fmean(_values(project, family, METRIC_BEST))
                > statistics.fmean(_values(project, family, METRIC_LAST))
                for family in FAMILIES
            ),
            "mean(best) > mean(last)",
            {
                family: [
                    round(statistics.fmean(_values(project, family, METRIC_BEST)), 4),
                    round(statistics.fmean(_values(project, family, METRIC_LAST)), 4),
                ]
                for family in FAMILIES
            },
            detail="the published table reports the best checkpoint, never the last one",
        )
    )

    # -- membership: 3 included / 0 excluded, nothing manufactured
    membership = {item.family_id: item for item in result.membership}
    checks.append(
        _check(
            "membership_all_included",
            all(
                item.included == 3 and item.excluded == 0 and item.unknown_membership == 0
                for item in membership.values()
            ),
            {"included": 3, "excluded": 0},
            {
                family: [item.included, item.excluded, item.unknown_membership]
                for family, item in membership.items()
            },
        )
    )
    checks.append(
        _check(
            "membership_rule_evidenced",
            all(
                item.rule_status == ProvenanceStatus.SUPPORTED.value for item in membership.values()
            ),
            "SUPPORTED",
            sorted({item.rule_status for item in membership.values()}),
            detail="read off scripts/average_log.py's own loop, not from prose",
        )
    )

    # -- aggregation arithmetic, recomputed a second time here
    records = {record.aggregation_id: record for record in project.aggregations}
    for family in FAMILIES:
        record = records[f"{family}/{METRIC_BEST}@included"]
        values = _values(project, family, METRIC_BEST)
        mean = statistics.fmean(values)
        spread = statistics.pstdev(values)
        checks.append(
            _check(
                f"member_set[{family}]",
                record.member_run_ids == RUNS[family] and record.excluded_run_ids == [],
                RUNS[family],
                [record.member_run_ids, record.excluded_run_ids],
            )
        )
        checks.append(
            _check(
                f"mean_recomputed[{family}]",
                record.mean is not None and math.isclose(record.mean, mean, rel_tol=1e-12),
                round(mean, 6),
                record.mean,
                detail=f"independent fmean over {values}",
            )
        )
        checks.append(
            _check(
                f"std_recomputed[{family}]",
                record.std is not None and math.isclose(record.std, spread, rel_tol=1e-9),
                round(spread, 6),
                record.std,
                detail="population std (ddof=0), the project's own np.std default",
            )
        )
        checks.append(
            _check(
                f"spread_basis[{family}]",
                record.spread_basis is SpreadBasis.STANDARD_DEVIATION
                and record.std_ddof == 0
                and record.display_multiplier == 1.0
                and record.recomputed_spread is not None
                and math.isclose(record.recomputed_spread, spread, rel_tol=1e-12),
                "standard_deviation x1",
                [record.spread_basis.value, record.std_ddof, record.display_multiplier],
            )
        )
        checks.append(
            _check(
                f"termination_cause[{family}]",
                all(
                    runs[id_].termination_cause.value is TerminationCause.ITERATION_CAP
                    and runs[id_].termination_cause.status is ProvenanceStatus.CONFIRMED
                    for id_ in RUNS[family]
                ),
                "ITERATION_CAP/CONFIRMED",
                sorted({f"{runs[id_].termination_cause.value}" for id_ in RUNS[family]}),
            )
        )
        checks.append(
            _check(
                f"log_sha256_matches_the_download_manifest[{family}]",
                all(_manifest_ok(runs[id_], logs_root) for id_ in RUNS[family]),
                "manifest sha256 == recomputed sha256 == recorded artifact sha256",
                {id_: _manifest_state(runs[id_], logs_root) for id_ in RUNS[family]},
            )
        )

    # -- published comparison, and the counterfactual the prose invites
    matched = [
        record
        for record in project.aggregations
        if record.metric_name == METRIC_BEST and record.comparison_status is ComparisonStatus.MATCH
    ]
    checks.append(
        _check(
            "published_cells_match",
            len(matched) == 2 and all(record.n == 3 for record in matched),
            2,
            [record.aggregation_id for record in matched],
        )
    )
    checks.append(
        _check(
            "no_reported_cell_mismatches",
            not [
                record
                for record in project.aggregations
                if record.comparison_status is ComparisonStatus.MISMATCH
            ],
            [],
            [
                record.aggregation_id
                for record in project.aggregations
                if record.comparison_status is ComparisonStatus.MISMATCH
            ],
        )
    )
    for record in project.aggregations:
        if record.metric_name != METRIC_BEST or record.reported_spread is None:
            continue
        assert record.recomputed_spread is not None and record.n
        standard_error = record.recomputed_spread / math.sqrt(record.n)
        checks.append(
            _check(
                f"published_spread_is_not_a_standard_error[{record.family_id}]",
                abs(standard_error - record.reported_spread) > record.spread_tolerance,
                "std/sqrt(N) outside the published cell",
                [round(standard_error, PUBLISHED_DECIMALS), record.reported_spread],
                detail="README.md:58 calls the published +/- 'standard errors'; the project's own "
                "aggregation code writes np.std, which is what recomputed here",
            )
        )
        checks.append(
            _check(
                f"published_spread_rounds_onto_the_recomputed_std[{record.family_id}]",
                round(record.recomputed_spread, PUBLISHED_DECIMALS)
                == round(record.reported_spread, PUBLISHED_DECIMALS),
                record.reported_spread,
                round(record.recomputed_spread, PUBLISHED_DECIMALS),
            )
        )
        checks.append(
            _check(
                f"published_mean_rounds_onto_the_recomputed_mean[{record.family_id}]",
                record.recomputed_value is not None
                and round(record.recomputed_value, PUBLISHED_DECIMALS) == record.reported_value,
                record.reported_value,
                round(record.recomputed_value or float("nan"), PUBLISHED_DECIMALS),
            )
        )
    counterfactual_last = [
        record.aggregation_id
        for record in project.aggregations
        if record.metric_name == METRIC_LAST
        and record.comparison_status is ComparisonStatus.UNKNOWN
    ]
    checks.append(
        _check(
            "counterfactual_last_reduction_has_no_published_cell",
            len(counterfactual_last) == 2,
            2,
            counterfactual_last,
            detail="the last-checkpoint reduction is reported so the policy gap is measurable; "
            "the project published nothing to compare it against",
        )
    )
    checks.append(
        _check(
            "declared_repetitions_not_assumed",
            all(
                family.declared_repetitions.status is ProvenanceStatus.UNKNOWN
                for family in project.families
            ),
            "UNKNOWN",
            sorted({f.declared_repetitions.status.value for f in project.families}),
            detail="README.md:58 claims seeds 0,1,2 for all experiments while the shipped "
            "config_generator.py:192 generates seeds=[0]; the artifacts settle neither way",
        )
    )
    return checks


def _manifest_entry(run_id: str, logs_root: Path) -> dict[str, Any]:
    manifest = logs_root / "download_manifest.json"
    if not manifest.is_file():
        return {}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return data.get("files", {}).get(f"{run_id}/log.txt", {})


def _manifest_ok(run: Any, logs_root: Path) -> bool:
    state = _manifest_state(run, logs_root)
    return len(set(state.values())) == 1 and "" not in state.values()


def _manifest_state(run: Any, logs_root: Path) -> dict[str, str]:
    entry = _manifest_entry(run.run_id, logs_root)
    log = next((item for item in run.artifacts if item.path.endswith("log.txt")), None)
    path = logs_root / run.run_id / "log.txt"
    recomputed = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
    return {
        "manifest": str(entry.get("sha256", "")),
        "recorded": str(log.sha256 if log else ""),
        "recomputed": recomputed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, required=True, help="read-only TorchSSL clone")
    parser.add_argument(
        "--logs-root", type=Path, required=True, help="directory holding <run>/log.txt"
    )
    parser.add_argument(
        "--reported-table",
        type=Path,
        default=None,
        help="JSON transcription of the published cells to compare against",
    )
    parser.add_argument("-o", "--output", type=Path, default=Path("acceptance-torchssl.json"))
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    logs_root = args.logs_root.resolve()
    if not repo.is_dir() or not logs_root.is_dir():
        parser.error("--repo and --logs-root must both be existing directories")
    if not (repo / "scripts" / "average_log.py").is_file():
        parser.error(f"{repo} does not look like a TorchSSL clone (no scripts/average_log.py)")

    root = logs_root.parent if logs_root.parent != logs_root else logs_root
    adapter = TorchSSLAdapter(
        root,
        repo_root=repo,
        logs_root=logs_root,
        reported_table=args.reported_table,
    )
    project = scan_project(root, adapter=adapter)
    checks = evaluate(project, logs_root)

    passed = sum(1 for check in checks if check["passed"])
    payload = {
        "inputs": {
            "repo": str(repo),
            "logs_root": str(logs_root),
            "reported_table": str(args.reported_table) if args.reported_table else None,
            "root": str(root),
        },
        "oracle": "planned TorchSSL subset + independent statistics recomputation (expectations only)",
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
