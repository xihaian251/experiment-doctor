#!/usr/bin/env python3
"""Held-out acceptance run for the CRDA adapter (Acceptance #2).

Read-only.  Nothing runs by default and no repository path is baked in:

    python scripts/run_crda_acceptance.py \
        --repo /path/to/CRDA \
        --ground-truth /path/to/crda_ground_truth.json \
        -o acceptance.json

``--ground-truth`` is the independent oracle produced by
``acceptance2-crda/scripts/crda_ground_truth.py``, which parses CRDA's own
committed artifacts with stdlib code only and never imports
``experiment_doctor``.  Expectations therefore enter this script as an input
file, not as numbers copied into the adapter, and the adapter never sees them.

Exit code is 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from experiment_doctor.audit import audit_project  # noqa: E402
from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus  # noqa: E402
from experiment_doctor.rules import run_rules  # noqa: E402
from experiment_doctor.rules.base import RuleStatus  # noqa: E402
from experiment_doctor.scanner import scan_project  # noqa: E402
from experiment_doctor.schema import (  # noqa: E402
    ComparisonStatus,
    ExperimentProject,
    MetricDirection,
    SpreadBasis,
    SpreadSemantics,
)

# ---- repo-wide oracle (Phase A/D inventory; expectations, never inputs) ------
TOTAL_FAMILIES = 90
TOTAL_RUNS = 1350
TOTAL_AGGREGATIONS = 270

SELECTED_DATASET = "227_cpu_small"
SELECTED_SUBSETS = [1638, 3276, 4914, 6552, 8190]
SELECTED_BASELINES = ["mlp", "xgboost"]
SELECTED_FAMILIES = 10
SELECTED_RUNS = 150
SELECTED_AGGREGATIONS = 30
N_PER_SUBSET = 15
SEED_DOMAIN = 1_000_000  # np.random.randint(0, 1_000_000) per src/experiment.py

PERFORMANCE_METRICS = ("mse", "aug_mse", "delta_mse")

ABS_TOL = 1e-9


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


def _close(a: float | None, b: float | None, tol: float = ABS_TOL) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def _status_of(field: ProvenanceField[Any]) -> ProvenanceStatus:
    return field.status


def _rule_status(results: list[Any], rule_id: str) -> set[RuleStatus]:
    return {r.status for r in results if r.rule_id == rule_id}


def _rule_count(results: list[Any], rule_id: str) -> int:
    return sum(1 for r in results if r.rule_id == rule_id)


def evaluate(
    project: ExperimentProject, gt: dict[str, Any], results: list[Any]
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    runs = project.runs
    families = project.families
    aggregations = project.aggregations

    # --- adapter selection and repo-wide scope -----------------------------
    checks.append(_check("adapter_selected", project.adapter == "crda", "crda", project.adapter))
    checks.append(
        _check(
            "repo_scope",
            (len(families), len(runs), len(aggregations))
            == (TOTAL_FAMILIES, TOTAL_RUNS, TOTAL_AGGREGATIONS),
            [TOTAL_FAMILIES, TOTAL_RUNS, TOTAL_AGGREGATIONS],
            [len(families), len(runs), len(aggregations)],
            "9 datasets x 5 sample-size subsets x 2 baselines; 15 seed-runs and 3 metrics each",
        )
    )

    # --- the selected (blind-picked) dataset --------------------------------
    gt_fams = gt["families"]
    sel_prefix = f"{SELECTED_DATASET}_sample_"
    sel_families = [f for f in families if f.family_id.startswith(sel_prefix)]
    want_ids = {
        f"{SELECTED_DATASET}_sample_{n}/{b}" for n in SELECTED_SUBSETS for b in SELECTED_BASELINES
    }
    checks.append(
        _check(
            "selected_dataset_family_shape",
            {f.family_id for f in sel_families} == want_ids,
            sorted(want_ids),
            sorted(f.family_id for f in sel_families),
        )
    )
    sel_runs = [r for r in runs if r.family_id in want_ids]
    checks.append(
        _check(
            "selected_dataset_run_granularity",
            len(sel_runs) == SELECTED_RUNS,
            SELECTED_RUNS,
            len(sel_runs),
            "seed-level runs: one per interim CSV row, not one per experiment directory",
        )
    )

    # --- seeds: value from the CSV column, domain of the generator ----------
    gt_seeds = set(gt_fams[f"{SELECTED_DATASET}/mlp"]["seeds"]["observed_unique_seeds"])
    per_family_seeds = {
        f.family_id: {r.seed.value for r in sel_runs if r.family_id == f.family_id}
        for f in sel_families
    }
    checks.append(
        _check(
            "seeds_match_ground_truth",
            all(seeds == gt_seeds for seeds in per_family_seeds.values()),
            sorted(gt_seeds),
            {k: sorted(v) for k, v in list(per_family_seeds.items())[:1]},
            "one family shown; all ten must equal the independent seed set",
        )
    )
    all_seeds = {r.seed.value for r in sel_runs}
    checks.append(
        _check(
            "seeds_within_generator_domain",
            all(isinstance(s, int) and 0 <= s < SEED_DOMAIN for s in all_seeds)
            and len(all_seeds) == N_PER_SUBSET,
            f"15 distinct values in [0, {SEED_DOMAIN}) — the run-directory timestamp can never appear as a seed",
            sorted(all_seeds),
        )
    )
    checks.append(
        _check(
            "seed_provenance_confirmed",
            all(r.seed.status is ProvenanceStatus.CONFIRMED for r in sel_runs),
            "every seed CONFIRMED with an interim-CSV source",
            sorted({_status_of(r.seed).value for r in sel_runs}),
        )
    )

    # --- resolved config -----------------------------------------------------
    gt_cfg = gt_fams[f"{SELECTED_DATASET}/mlp"]["config"]
    cfg_ok = all(
        r.resolved_config.status is ProvenanceStatus.CONFIRMED
        and isinstance(r.resolved_config.value, dict)
        and r.resolved_config.value.get("num_seeds") == gt_cfg["declared_num_seeds"]
        and r.resolved_config.value.get("sample_sizes") == gt_cfg["sample_sizes"]
        for r in sel_runs
    )
    checks.append(
        _check(
            "resolved_config_confirmed",
            cfg_ok,
            "num_seeds=15, sample_sizes from config.json, CONFIRMED for every run",
            sorted({_status_of(r.resolved_config).value for r in sel_runs}),
            "config.json is the resolved runtime config the experiment itself wrote",
        )
    )
    checks.append(
        _check(
            "declared_seeds_match_observed",
            gt_cfg["declared_num_seeds"] == len(gt_seeds)
            and gt_fams[f"{SELECTED_DATASET}/mlp"]["seeds"]["missing_vs_declared"] == 0
            and len({r.seed.value for r in sel_runs}) == gt_cfg["declared_num_seeds"],
            "config num_seeds == observed unique seeds",
            [gt_cfg["declared_num_seeds"], len({r.seed.value for r in sel_runs})],
        )
    )

    # --- aggregation records --------------------------------------------------
    sel_aggs = [a for a in aggregations if a.family_id in want_ids]
    checks.append(
        _check(
            "aggregation_records",
            len(sel_aggs) == SELECTED_AGGREGATIONS
            and {a.metric_name for a in sel_aggs} == set(PERFORMANCE_METRICS),
            [SELECTED_AGGREGATIONS, sorted(PERFORMANCE_METRICS)],
            [len(sel_aggs), sorted({a.metric_name for a in sel_aggs})],
            "p_wilcoxon is a per-seed diagnostic and is never aggregated",
        )
    )
    checks.append(
        _check(
            "aggregation_n_is_15",
            all(a.n == N_PER_SUBSET and len(a.member_run_ids) == N_PER_SUBSET for a in sel_aggs),
            N_PER_SUBSET,
            sorted({a.n for a in sel_aggs}),
        )
    )
    fam_members = {f.family_id: set(f.run_ids) for f in sel_families}
    checks.append(
        _check(
            "membership_15_of_15",
            all(set(a.member_run_ids) == fam_members[a.family_id] for a in sel_aggs)
            and gt_fams[f"{SELECTED_DATASET}/mlp"]["aggregation"]["membership"][
                "all_interim_rows_used_by_in_run_aggregation"
            ],
            "every recorded seed row is a member of its subset aggregation",
            sum(1 for a in sel_aggs if set(a.member_run_ids) == fam_members[a.family_id]),
        )
    )
    fractions = gt_fams[f"{SELECTED_DATASET}/mlp"]["aggregation"]["membership"][
        "proceed_fraction_by_subset"
    ]
    checks.append(
        _check(
            "wilcoxon_gate_is_not_membership",
            all(f < 1.0 for f in fractions.values())
            and all(r.included_in_aggregation.value is True for r in sel_runs),
            "gate rejected seeds (fraction<1) yet nothing is excluded: ignore_filter=true",
            sorted(fractions.values()),
            "a failed safety gate must never be read as a missing member",
        )
    )

    # --- numbers vs the independent oracle ------------------------------------
    gt_by_key = {}
    for fam_name, fam in gt_fams.items():
        baseline = fam_name.split("/")[1]
        for subset, cell in fam["aggregation"]["per_subset"].items():
            for metric_name, m in cell["metrics"].items():
                gt_by_key[(f"{subset}/{baseline}", metric_name)] = m
    mean_ok = spread_ok = reported_spread_ok = 0
    for a in sel_aggs:
        m = gt_by_key.get((a.family_id, a.metric_name))
        if m is None:
            continue
        mean_ok += _close(a.recomputed_value, m["mean"])
        spread_ok += _close(a.recomputed_spread, m["population_std"])
        reported_spread_ok += _close(a.reported_spread, m["reported_std_column"])
    checks.append(
        _check(
            "means_match_ground_truth",
            mean_ok == SELECTED_AGGREGATIONS,
            f"all {SELECTED_AGGREGATIONS} recomputed means == oracle means (1e-9)",
            mean_ok,
        )
    )
    checks.append(
        _check(
            "spread_recompute_matches_population_std",
            spread_ok == SELECTED_AGGREGATIONS,
            f"all {SELECTED_AGGREGATIONS} recomputed spreads == oracle population std",
            spread_ok,
            "the artifacts' ± is numerically the population standard deviation",
        )
    )
    checks.append(
        _check(
            "reported_spread_matches_results_csv",
            reported_spread_ok == SELECTED_AGGREGATIONS,
            "reported spreads parsed verbatim from results.csv",
            reported_spread_ok,
        )
    )

    # --- declared semantics ----------------------------------------------------
    basis_ok = all(
        a.spread_basis is SpreadBasis.STANDARD_DEVIATION
        and a.std_ddof == 0
        and a.documented_spread.status is ProvenanceStatus.CONFIRMED
        and a.documented_spread.value is SpreadSemantics.STANDARD_ERROR
        and a.implemented_spread.status is ProvenanceStatus.CONFLICTING
        for a in sel_aggs
    )
    checks.append(
        _check(
            "spread_semantics_recorded_honestly",
            basis_ok,
            "basis standard_deviation/ddof 0 from the artifacts; documented SEM CONFIRMED; implemented CONFLICTING",
            [
                sorted({a.spread_basis.value for a in sel_aggs}),
                sorted({a.std_ddof for a in sel_aggs}),
                sorted({a.implemented_spread.status.value for a in sel_aggs}),
                sorted({a.documented_spread.status.value for a in sel_aggs}),
            ],
            "HEAD code computes sample SE, the collector documents a raw-std era, the artifacts are pop std",
        )
    )

    # --- rule matrix ------------------------------------------------------------
    checks.append(
        _check(
            "ed007_recompute_all_match",
            _rule_status(results, "ED007") == {RuleStatus.PASS}
            and _rule_count(results, "ED007") == TOTAL_AGGREGATIONS
            and all(a.comparison_status is ComparisonStatus.MATCH for a in aggregations),
            "270 PASS / 0 MISMATCH: mean and spread recompute from per-seed values",
            sorted(s.value for s in _rule_status(results, "ED007")),
        )
    )
    checks.append(
        _check(
            "ed008_contradiction_caught",
            _rule_status(results, "ED008") == {RuleStatus.FAIL}
            and _rule_count(results, "ED008") == TOTAL_AGGREGATIONS,
            "270 FAIL: documented SEM vs artifact-native population std is a real contradiction",
            _rule_count(results, "ED008"),
            "the only FAIL class in the run; ED007 still PASSes, so this is a semantics verdict, not a numeric one",
        )
    )
    pass_rules = ["ED001", "ED002"]
    pass_counts = {
        "ED004": TOTAL_RUNS,
        "ED005": TOTAL_AGGREGATIONS,
        "ED006": TOTAL_AGGREGATIONS,
    }
    matrix_ok = all(
        _rule_status(results, rid) == {RuleStatus.PASS} for rid in pass_rules + list(pass_counts)
    ) and (
        _rule_count(results, "ED001") == TOTAL_FAMILIES
        and _rule_count(results, "ED002") == TOTAL_FAMILIES
        and _rule_count(results, "ED004") == TOTAL_RUNS
        and _rule_count(results, "ED005") == TOTAL_AGGREGATIONS
        and _rule_count(results, "ED006") == TOTAL_AGGREGATIONS
    )
    checks.append(
        _check(
            "identity_config_metric_rules_pass",
            matrix_ok,
            "ED001/ED002 per family and ED004/ED005/ED006 per entity: all PASS",
            {
                rid: (
                    _rule_count(results, rid),
                    sorted(s.value for s in _rule_status(results, rid)),
                )
                for rid in ["ED001", "ED002", "ED004", "ED005", "ED006"]
            },
        )
    )
    commit_values = [r.code_commit.value for r in runs]
    checks.append(
        _check(
            "ed003_no_fabricated_commit",
            _rule_status(results, "ED003") == {RuleStatus.INCONCLUSIVE}
            and _rule_count(results, "ED003") == TOTAL_RUNS
            and all(v is None for v in commit_values),
            "1350 INCONCLUSIVE, no run carries a commit value",
            [_rule_count(results, "ED003"), sum(1 for v in commit_values if v is not None)],
            "clone HEAD is never presented as the provenance of archived artifacts",
        )
    )
    checks.append(
        _check(
            "ed009_termination_not_inferred",
            _rule_status(results, "ED009") == {RuleStatus.INCONCLUSIVE}
            and _rule_count(results, "ED009") == TOTAL_RUNS,
            "1350 INCONCLUSIVE",
            _rule_count(results, "ED009"),
            "absence of further rows is not evidence of a termination cause",
        )
    )
    checks.append(
        _check(
            "ed010_declaration_is_not_environment",
            RuleStatus.PASS not in _rule_status(results, "ED010")
            and _rule_status(results, "ED010") == {RuleStatus.INCONCLUSIVE}
            and all(r.runtime_environment is None for r in runs),
            "1350 INCONCLUSIVE; requirements.txt alone never PASSes ED010",
            sorted(s.value for s in _rule_status(results, "ED010")),
        )
    )

    # --- metric directions -------------------------------------------------------
    def metric(r: Any, name: str) -> Any:
        return next((m for m in r.metrics if m.name == name), None)

    dir_ok = all(
        (m := metric(r, name)) is not None
        and m.direction.status is ProvenanceStatus.CONFIRMED
        and m.direction.value is MetricDirection.MINIMIZE
        for r in sel_runs
        for name in PERFORMANCE_METRICS
    )
    checks.append(
        _check(
            "performance_directions_confirmed",
            dir_ok,
            "mse/aug_mse/delta_mse MINIMIZE, each cited to code or README prose",
            "ok" if dir_ok else "some direction not CONFIRMED",
        )
    )
    pwil = [metric(r, "p_wilcoxon") for r in sel_runs]
    checks.append(
        _check(
            "wilcoxon_direction_stays_unknown",
            all(m is not None and m.direction.status is ProvenanceStatus.UNKNOWN for m in pwil),
            "p_wilcoxon recorded as a diagnostic with UNKNOWN direction",
            sorted({m.direction.status.value for m in pwil if m}),
            "a one-sided gate p-value is not a performance metric; no direction is guessed",
        )
    )
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", required=True, type=Path, help="CRDA checkout (read-only)")
    parser.add_argument(
        "--ground-truth",
        required=True,
        type=Path,
        help="crda_ground_truth.json produced independently of experiment_doctor",
    )
    parser.add_argument("-o", "--output", type=Path, default=Path("crda_acceptance.json"))
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    if not repo.is_dir():
        parser.error("--repo must be an existing directory")
    gt = json.loads(args.ground_truth.read_text(encoding="utf-8"))

    project = scan_project(repo)
    audit = audit_project(project)
    checks = evaluate(project, gt, run_rules(project, audit))

    passed = sum(1 for c in checks if c["passed"])
    payload = {
        "inputs": {"repo": str(repo), "ground_truth": str(args.ground_truth.resolve())},
        "oracle": "independent per-seed recomputation of CRDA's committed artifacts (no experiment_doctor code)",
        "adapter": project.adapter,
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
    }
    if args.output.parent != Path(""):
        args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    for c in checks:
        print(f"[{'PASS' if c['passed'] else 'FAIL'}] {c['name']}")
    print(f"\n{passed}/{len(checks)} checks passed -> {args.output}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
