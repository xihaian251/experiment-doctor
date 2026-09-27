"""CRDA held-out adapter: discovery granularity, seed provenance, spread semantics.

The fixture is synthetic and tiny; every expected number below is computed in this
file from the values the fixture writes, never copied from the real CRDA project.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

from experiment_doctor.adapters.crda import CRDAAdapter
from experiment_doctor.audit import audit_project
from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.rules import run_rules
from experiment_doctor.rules.base import RuleResult, RuleStatus
from experiment_doctor.scanner import scan_project, select_adapter
from experiment_doctor.schema import ExperimentProject, MetricDirection, RunStatus

SEEDS = (101, 202, 303)
MSE = (0.02, 0.01, 0.03)
AUG_MSE = (0.015, 0.012, 0.02)
P_WILCOXON = (0.001, 0.04, 0.2)
PROCEED = (True, False, True)

EXPERIMENT_PY = '''"""minimal copy of the CRDA aggregation lines the adapter cites"""
import numpy as np
def run(self):
    seeds = np.random.randint(0, 1000000, self.config.num_seeds).tolist()
    mse = baseline.evaluate(X_test, y_test, metric="mse")
    ensemble_pred = preds.mean(axis=1)
    aug_mse = ((y_test - ensemble_pred) ** 2).mean()
    delta_mse = 100.0 * (aug_mse - mse) / mse
    mse = mse  # Optuna minimises
    for metric in ['mse']:
        values = [r[metric] for r in seed_results]
        mean_val = np.nanmean(values)
        std_err_val = np.nanstd(values, ddof=1) / np.sqrt(len(values))
'''

COLLECTOR_PY = '''"""minimal copy of the CRDA collector docstring sentence"""
# It deliberately does NOT read the pre-aggregated `results.csv` `std` column,
# whose meaning is ambiguous across experiment versions (raw std in early runs,
# SEM in later runs).
'''

README_MD = """# Mini CRDA

## Headline Results (delta MSE %, lower is better)

- **Standard error.** Aggregation reports the **standard error of the mean**
  (`sample_std / sqrt(n)`, computed with `ddof=1`) over seeds.
"""


def _pop_std(values: tuple[float, ...]) -> float:
    return statistics.pstdev(values)


def _mean(values: tuple[float, ...]) -> float:
    return statistics.fmean(values)


@pytest.fixture(scope="session")
def crda_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("mini_crda")
    (root / "data").mkdir()
    (root / "data" / "mydata.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "requirements.txt").write_text("numpy==1.26.4\n", encoding="utf-8")
    (root / "README.md").write_text(README_MD, encoding="utf-8")
    src = root / "src"
    src.mkdir()
    (src / "experiment.py").write_text(EXPERIMENT_PY, encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "collect_main_experiment_results.py").write_text(COLLECTOR_PY, encoding="utf-8")

    run_dir = root / "experiments" / "mydata" / "mlp_20200101-010101"
    (run_dir / "interim_results").mkdir(parents=True)
    tag = "mydata_sample_100"
    config = {
        "timestamp": "20200101-010101",
        "experiment_name": "mlp_20200101-010101",
        "dataset_path": "../data/mydata.csv",
        "baseline": "mlp",
        "random_seed": 0,
        "num_seeds": len(SEEDS),
        "ignore_filter": True,
        "sample_sizes": [100],
        "save_models": False,
    }
    (run_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    rows = ["dataset,seed,mse,aug_mse,delta_mse,p_wilcoxon,should_proceed,features_perturbed"]
    for seed, mse, aug, p, proceed in zip(SEEDS, MSE, AUG_MSE, P_WILCOXON, PROCEED, strict=True):
        delta = 100.0 * (aug - mse) / mse
        rows.append(f"{tag},{seed},{mse},{aug},{delta},{p},{proceed},[0]")
    (run_dir / "interim_results" / f"{tag}_interim_results.csv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )
    aggregate = ["dataset,metric,mean,std"]
    for metric, values in (
        ("mse", MSE),
        ("aug_mse", AUG_MSE),
        ("delta_mse", tuple(100.0 * (a - m) / m for m, a in zip(MSE, AUG_MSE, strict=True))),
        ("p_wilcoxon", P_WILCOXON),
    ):
        aggregate.append(f"{tag},{metric},{_mean(values)},{_pop_std(values)}")
    (run_dir / "results.csv").write_text("\n".join(aggregate) + "\n", encoding="utf-8")
    return root


@pytest.fixture(scope="session")
def crda_project(crda_root: Path) -> ExperimentProject:
    adapter = CRDAAdapter(crda_root)
    project = scan_project(crda_root, adapter=adapter)
    audit_project(project)
    return project


def _rules(project: ExperimentProject) -> list[RuleResult]:
    return run_rules(project, audit_project(project))


def test_detect_needs_the_layout(tmp_path: Path, crda_root: Path) -> None:
    assert CRDAAdapter(tmp_path).detect(tmp_path) == 0.0
    (tmp_path / "experiments").mkdir()
    assert CRDAAdapter(tmp_path).detect(tmp_path) == 0.0
    score = CRDAAdapter(crda_root).detect(crda_root)
    assert score >= 0.8
    assert select_adapter(crda_root)[0].name == "crda"


def test_timestamped_directory_is_a_family_container_not_one_run(
    crda_project: ExperimentProject,
) -> None:
    assert [family.family_id for family in crda_project.families] == ["mydata_sample_100/mlp"]
    assert len(crda_project.runs) == len(SEEDS)
    assert crda_project.families[0].run_ids == [run.run_id for run in crda_project.runs]


def test_seeds_come_from_the_column_not_the_row_order(crda_project: ExperimentProject) -> None:
    runs = sorted(crda_project.runs, key=lambda run: run.run_id)
    assert [run.seed.value for run in runs] == sorted(SEEDS)
    assert all(run.seed.status is ProvenanceStatus.CONFIRMED for run in runs)
    assert all(run.seed.source is not None and "seed=" in str(run.seed.source.key) for run in runs)
    assert all(run.status is RunStatus.UNKNOWN for run in runs)
    assert all(run.repetition_index.value is None for run in runs)


def test_config_is_the_run_own_resolved_config(crda_project: ExperimentProject) -> None:
    run = crda_project.runs[0]
    assert run.resolved_config.status is ProvenanceStatus.CONFIRMED
    assert run.resolved_config.value is not None
    assert run.resolved_config.value["baseline"] == "mlp"
    assert run.resolved_config.source is not None
    assert run.resolved_config.source.path is not None
    assert run.resolved_config.source.path.endswith("config.json")
    identity = {item.family_id: item for item in audit_project(crda_project).identity}
    assert identity["mydata_sample_100/mlp"].status.value == "CONSISTENT"


def test_aggregation_parses_membership_and_spread_from_artifacts(
    crda_project: ExperimentProject,
) -> None:
    records = [record for record in crda_project.aggregations if record.metric_name == "mse"]
    assert len(records) == 1
    record = records[0]
    assert record.n == len(SEEDS)
    assert record.member_run_ids == [
        run.run_id for run in sorted(crda_project.runs, key=lambda r: r.run_id)
    ]
    assert record.excluded_run_ids == []
    assert record.reported_value == pytest.approx(_mean(MSE))
    # the fixture writes the population std; the adapter declares that basis and the
    # audit's numeric recompute agrees with it
    assert record.reported_spread == pytest.approx(_pop_std(MSE))
    assert record.recomputed_value == pytest.approx(_mean(MSE), abs=1e-9)
    assert record.recomputed_spread == pytest.approx(_pop_std(MSE), abs=1e-9)
    assert record.implemented_selection.value is not None
    assert record.membership_rule.status is ProvenanceStatus.CONFIRMED


def test_spread_semantics_conflict_is_a_fail_not_a_quiet_pass(
    crda_project: ExperimentProject,
) -> None:
    results = [rule for rule in _rules(crda_project) if rule.rule_id == "ED008"]
    assert [rule.status for rule in results] == [RuleStatus.FAIL] * 3  # one per performance metric
    rule = results[0]
    assert rule.measurements["documented_semantics"] == "standard_error"
    assert rule.measurements["implemented_semantics"] == "unknown"  # CONFLICTING carries no value


def test_requirements_never_become_a_runtime_environment(crda_project: ExperimentProject) -> None:
    for run in crda_project.runs:
        assert run.runtime_environment is None
        assert run.environment.status is ProvenanceStatus.UNKNOWN
    results = [rule for rule in _rules(crda_project) if rule.rule_id == "ED010"]
    assert [rule.status for rule in results] == [RuleStatus.INCONCLUSIVE] * len(SEEDS)
    counts = [rule.measurements["declared_environment_files"] for rule in results]
    assert all(isinstance(c, int) and c >= 0 for c in counts)


def test_no_commit_is_fabricated(crda_project: ExperimentProject) -> None:
    for run in crda_project.runs:
        assert run.code_commit.status is ProvenanceStatus.UNKNOWN
        assert run.code_repository.status is ProvenanceStatus.UNKNOWN


def test_metric_directions_and_diagnostic(crda_project: ExperimentProject) -> None:
    metrics = {metric.name: metric for metric in crda_project.runs[0].metrics}
    assert metrics["mse"].direction.value is MetricDirection.MINIMIZE
    assert metrics["delta_mse"].direction.value is MetricDirection.MINIMIZE
    assert metrics["p_wilcoxon"].direction.value is None  # UNKNOWN: a gate, not performance
    assert not any(record.metric_name == "p_wilcoxon" for record in crda_project.aggregations)
