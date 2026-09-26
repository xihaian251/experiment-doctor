"""TorchSSL adapter: seeds, best-vs-last, and a mean +/- std the tool must not reinterpret."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from experiment_doctor.adapters.torchssl import TorchSSLAdapter, parse_namespace
from experiment_doctor.audit import audit_project
from experiment_doctor.provenance import ProvenanceStatus, SourceRef
from experiment_doctor.scanner import scan_project, select_adapter
from experiment_doctor.schema import (
    ComparisonStatus,
    ExperimentProject,
    MetricDirection,
    RunStatus,
    SpreadBasis,
    TerminationCause,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "mini_torchssl"
FIXTURE_LOGS = FIXTURE_ROOT / "logs"
FIXTURE_REPO = FIXTURE_ROOT / "repo"


def _scan(reported: str | None) -> ExperimentProject:
    adapter = TorchSSLAdapter(
        FIXTURE_ROOT,
        repo_root=FIXTURE_REPO,
        logs_root=FIXTURE_LOGS,
        reported_table=FIXTURE_ROOT / reported if reported else None,
    )
    project = scan_project(FIXTURE_ROOT, adapter=adapter)
    audit_project(project)
    return project


@pytest.fixture(scope="session")
def mini_torchssl_scan() -> Callable[[str | None], ExperimentProject]:
    cache: dict[str | None, ExperimentProject] = {}

    def scan(reported: str | None = None) -> ExperimentProject:
        if reported not in cache:
            cache[reported] = _scan(reported)
        return cache[reported]

    return scan


@pytest.fixture(scope="session")
def torchssl_project(
    mini_torchssl_scan: Callable[[str | None], ExperimentProject],
) -> ExperimentProject:
    return mini_torchssl_scan("reported_matched.json")


def test_torchssl_family_identity_is_method_dataset_and_label_budget(
    torchssl_project: ExperimentProject,
) -> None:
    project = torchssl_project
    assert [family.family_id for family in project.families] == [
        "fixmatch/cifar10_250",
        "flexmatch/cifar10_250",
    ]
    # the seed is the last name token and never part of the family key
    assert {run.family_id for run in project.runs} == {
        family.family_id for family in project.families
    }
    fixmatch = [run for run in project.runs if run.family_id == "fixmatch/cifar10_250"]
    assert sorted(run.run_id for run in fixmatch) == [
        "fixmatch_cifar10_250_0",
        "fixmatch_cifar10_250_1",
        "fixmatch_cifar10_250_2",
    ]
    assert all(run.status is RunStatus.COMPLETED_INCLUDED for run in project.runs)
    identity = {item.family_id: item for item in audit_project(project).identity}
    assert {item.status for item in identity.values()} == {"CONSISTENT"}


def test_torchssl_seed_is_confirmed_from_the_log_not_the_directory(
    torchssl_project: ExperimentProject,
) -> None:
    runs = {run.run_id: run for run in torchssl_project.runs}
    for name, seed in [("fixmatch_cifar10_250_0", 0), ("fixmatch_cifar10_250_1", 1)]:
        field = runs[name].seed
        assert field.value == seed
        assert field.status is ProvenanceStatus.CONFIRMED
        assert field.source is not None
        # the evidence is the run log's own Arguments dump, not the folder name
        assert str(field.source.path).endswith("log.txt")
        assert "Arguments.seed" in str(field.source.key)
    seeds = {item.family_id: item for item in audit_project(torchssl_project).seeds}
    assert seeds["fixmatch/cifar10_250"].runs_with_seed_evidence == 3
    assert seeds["fixmatch/cifar10_250"].distinct_seeds == 3
    assert seeds["fixmatch/cifar10_250"].runs_with_unknown_seed == 0


def test_torchssl_seed_disagreeing_with_the_directory_is_conflicting(tmp_path: Path) -> None:
    log_dir = tmp_path / "fixmatch_cifar10_250_2"
    log_dir.mkdir()
    source = (FIXTURE_LOGS / "fixmatch_cifar10_250_0" / "log.txt").read_text(encoding="utf-8")
    (log_dir / "log.txt").write_text(source.replace("seed=0", "seed=7"), encoding="utf-8")
    adapter = TorchSSLAdapter(tmp_path, repo_root=FIXTURE_REPO, logs_root=tmp_path)
    project = scan_project(tmp_path, adapter=adapter)
    (run,) = project.runs
    assert run.seed.status is ProvenanceStatus.CONFLICTING
    assert run.seed.value is None
    # v0.1 rule: a conflicting field keeps both candidate sources instead of picking one
    assert run.seed.source is not None
    note = str(run.seed.source.note)
    assert "Arguments.seed" in note
    assert "directory name" in note
    assert run.status is RunStatus.COMPLETED_INCLUDED


def _cited(source: SourceRef | None) -> str:
    """The text of the line a SourceRef cites, read back from the fixture."""
    assert source is not None
    path, line = source.path, source.line
    assert path and line is not None, source
    text = (FIXTURE_ROOT / path).read_text(encoding="utf-8").splitlines()
    return text[int(line) - 1]


def test_torchssl_best_and_last_are_separate_metrics_with_an_evidenced_direction(
    torchssl_project: ExperimentProject,
) -> None:
    runs = {run.run_id: run for run in torchssl_project.runs}
    metrics = {record.name: record for record in runs["fixmatch_cifar10_250_0"].metrics}
    assert set(metrics) == {"eval/top-1-acc@best", "eval/top-1-acc@last"}
    best = metrics["eval/top-1-acc@best"]
    assert best.value.value == pytest.approx(90.12, abs=1e-9)
    assert best.value.status is ProvenanceStatus.CONFIRMED
    assert best.step.value == 1046000
    # the project publishes the best, so it is the family's primary metric
    family = next(f for f in torchssl_project.families if f.family_id == "fixmatch/cifar10_250")
    assert family.primary_metric == "eval/top-1-acc@best"
    # best is not last: selecting the maximum instead of the cap moves the number
    assert best.value.value is not None
    last_value = metrics["eval/top-1-acc@last"].value.value
    assert last_value is not None
    assert best.value.value > last_value
    assert best.direction.value is MetricDirection.MAXIMIZE
    assert best.direction.status is ProvenanceStatus.CONFIRMED
    assert best.direction.source is not None
    assert str(best.direction.source.path).endswith("fixmatch.py")
    # the citation is a real one: the cited line states the comparison the policy uses
    cited = _cited(best.direction.source)
    assert "eval/top-1-acc" in cited and ">" in cited and "best_eval_acc" in cited


def test_torchssl_family_and_run_fields_stay_unknown_where_no_artifact_speaks(
    torchssl_project: ExperimentProject,
) -> None:
    run = next(r for r in torchssl_project.runs if r.run_id == "fixmatch_cifar10_250_0")
    # the clone's HEAD cannot stand in for the commit that ran
    assert run.code_commit.status is ProvenanceStatus.UNKNOWN
    assert run.code_commit.value is None
    assert run.repetition_index.status is ProvenanceStatus.UNKNOWN
    assert run.command.status is ProvenanceStatus.UNKNOWN
    assert run.dataset_version.status is ProvenanceStatus.UNKNOWN
    # environment.yml declares an environment; no log records the one that ran
    assert run.environment.status is ProvenanceStatus.SUPPORTED
    assert "python==3.7.10" in str(run.environment.value)
    assert "pytorch==1.7.1" in str(run.environment.value)
    assert run.termination_cause.value is TerminationCause.ITERATION_CAP
    assert run.termination_cause.status is ProvenanceStatus.CONFIRMED
    assert run.included_in_aggregation.value is True


def test_torchssl_membership_is_all_included_with_no_exclusion_mechanism(
    torchssl_project: ExperimentProject,
) -> None:
    result = audit_project(torchssl_project)
    membership = {item.family_id: item for item in result.membership}
    for family_id, item in membership.items():
        assert item.included == item.n_runs, family_id
        assert item.excluded == 0
        assert item.excluded_without_evidence == 0
        assert item.unknown_membership == 0
        assert item.rule_status == ProvenanceStatus.SUPPORTED.value
    excluded = [
        run for run in torchssl_project.runs if run.included_in_aggregation.value is not True
    ]
    assert excluded == []


def test_torchssl_aggregation_recomputes_mean_and_population_std(
    torchssl_project: ExperimentProject,
) -> None:
    records = {record.aggregation_id: record for record in torchssl_project.aggregations}
    best = records["fixmatch/cifar10_250/eval/top-1-acc@best@included"]
    assert best.statistic == "mean"
    assert best.n == 3
    assert best.values == pytest.approx([90.12, 89.88, 90.42], abs=1e-9)
    assert best.mean == pytest.approx(90.14, abs=1e-9)
    assert best.std == pytest.approx(0.22090722, abs=1e-6)
    assert best.std is not None
    # this project's published +/- is the std itself, not the standard error
    assert best.std_ddof == 0
    assert best.spread_basis is SpreadBasis.STANDARD_DEVIATION
    assert best.display_multiplier == 1.0
    assert best.recomputed_spread == pytest.approx(best.std, abs=1e-9)
    assert best.recomputed_spread != pytest.approx(best.std / (3**0.5), abs=1e-6)
    assert best.comparison_status is ComparisonStatus.MATCH
    # the counterfactual last-checkpoint reduction has no published cell to compare with
    last = records["fixmatch/cifar10_250/eval/top-1-acc@last@included"]
    assert last.mean == pytest.approx(90.023333, abs=1e-4)
    assert last.comparison_status is ComparisonStatus.UNKNOWN
    assert last.membership_rule.status is ProvenanceStatus.INFERRED


def test_torchssl_published_cells_only_match_under_the_declared_spread_basis(
    mini_torchssl_scan: Callable[[str | None], ExperimentProject],
) -> None:
    matched = mini_torchssl_scan("reported_matched.json")
    against_se = mini_torchssl_scan("reported_standard_error.json")
    key = "fixmatch/cifar10_250/eval/top-1-acc@best@included"
    left = next(r for r in matched.aggregations if r.aggregation_id == key)
    right = next(r for r in against_se.aggregations if r.aggregation_id == key)
    assert left.reported_spread == 0.22
    assert right.reported_spread == 0.13
    assert left.recomputed_spread == pytest.approx(right.recomputed_spread, abs=1e-12)
    assert left.comparison_status is ComparisonStatus.MATCH
    # reading the published spread as a standard error is a real disagreement, not noise
    assert right.comparison_status is ComparisonStatus.MISMATCH
    assert right.tolerance == pytest.approx(0.005, rel=1e-6)
    flexmatch = next(
        r for r in against_se.aggregations if r.aggregation_id.startswith("flexmatch/cifar10_250")
    )
    assert flexmatch.comparison_status is ComparisonStatus.MISMATCH


def test_torchssl_adapter_is_selected_for_its_own_layout_and_not_for_gmmvi() -> None:
    adapter, score = select_adapter(FIXTURE_ROOT)
    assert adapter.name == "torchssl"
    assert score >= 0.99
    assert isinstance(TorchSSLAdapter(FIXTURE_ROOT), TorchSSLAdapter)
    # layout discovery alone finds both halves of the project
    resolved = TorchSSLAdapter(FIXTURE_ROOT)
    assert resolved.logs_root == FIXTURE_LOGS.resolve()
    assert resolved.repo_root == FIXTURE_REPO.resolve()
    other, _ = select_adapter(FIXTURE_ROOT.parent / "mini_gmmvi")
    assert other.name != "torchssl"


def test_torchssl_effective_config_excludes_only_per_run_bookkeeping(
    torchssl_project: ExperimentProject,
) -> None:
    runs = {run.run_id: run for run in torchssl_project.runs}
    field = runs["fixmatch_cifar10_250_0"].resolved_config
    assert field.status is ProvenanceStatus.CONFIRMED
    config = field.value
    assert isinstance(config, dict)
    assert config["num_train_iter"] == 1048576
    assert config["mu"] == 7
    for key in ("seed", "save_name", "c", "dist_url"):
        assert key not in config
    assert "withheld" in str(field.confidence_note)
    # every other argument is identical across the family's runs
    assert runs["fixmatch_cifar10_250_1"].resolved_config.value == config


def test_parse_namespace_splits_on_top_level_commas_only() -> None:
    parsed = parse_namespace("a=1, b='x, y', c=True, d=[1, 2], e=None, f='it\\'s', g=0.5")
    assert parsed["a"] == 1
    assert parsed["b"] == "x, y"
    assert parsed["c"] is True
    assert parsed["d"] == "[1, 2]"
    assert parsed["e"] == "None"
    assert parsed["g"] == 0.5
    # an escaped quote closes nothing: the keys after it are still parsed
    assert parsed["f"].startswith("it")
    assert len(parsed) == 7
