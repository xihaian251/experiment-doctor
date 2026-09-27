"""Release packaging locks (v0.1.0).

These tests pin the identities that must survive the wheel/sdist boundary:
the single version source, the CLI entry point target, the ten-rule registry,
the four shipped adapters, and the report JSON round-trip.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import tomllib
from pathlib import Path

import pytest

import experiment_doctor
from experiment_doctor.adapters import available_adapters
from experiment_doctor.audit import audit_project
from experiment_doctor.report import report_payload
from experiment_doctor.rules import RULES
from experiment_doctor.rules.base import RuleResult
from experiment_doctor.schema import ExperimentProject
from tests.builders import make_aggregation, make_family, make_run, project_with

RELEASE_VERSION = "0.1.0"

PYPROJECT = tomllib.loads(
    (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text("utf-8")
)


def test_version_is_frozen_and_single_sourced() -> None:
    assert experiment_doctor.__version__ == RELEASE_VERSION
    # the distribution version must not also live in pyproject: one source only
    assert "version" in PYPROJECT["project"]["dynamic"]
    assert (
        PYPROJECT["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        == "experiment_doctor.__version__"
    )


def test_installed_metadata_version_agrees() -> None:
    try:
        meta = importlib.metadata.version("experiment-doctor")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("source-tree run: the distribution is not installed")
    assert meta == experiment_doctor.__version__


def test_cli_entry_point_target_is_callable() -> None:
    target = PYPROJECT["project"]["scripts"]["experiment-doctor"]
    module_name, _, attr = target.partition(":")
    module = importlib.import_module(module_name)
    assert callable(getattr(module, attr))


def test_rule_registry_is_exactly_ed001_to_ed010_in_order() -> None:
    assert [rule.rule_id for rule in RULES] == [f"ED{i:03d}" for i in range(1, 11)]


def test_adapter_registry_ships_the_four_expected_adapters() -> None:
    assert {spec.name for spec in available_adapters()} == {
        "generic",
        "gmmvi-exp3",
        "torchssl",
        "crda",
    }


def test_report_json_round_trip_preserves_rules_and_provenance() -> None:
    run = make_run("F/f/seed-1")
    aggregation = make_aggregation(family_id="F/f", metric_name="elbo")
    project = project_with([run], make_family(run_ids=[run.run_id]), aggregations=[aggregation])
    audit = audit_project(project)
    from experiment_doctor.rules import run_rules

    rules = run_rules(project, audit)
    restored = json.loads(json.dumps(report_payload(project, audit, rules)))

    # report.json deliberately replaces the project-level artifact list with a count
    project_back = ExperimentProject.model_validate(restored["project"])
    assert project_back == project.model_copy(update={"artifacts": []})
    assert restored["project"]["artifact_count"] == len(project.artifacts)
    results_back = [RuleResult.model_validate(item) for item in restored["rules"]]
    assert [r.status.value for r in results_back] == [r.status.value for r in rules]
    assert {r.rule_id for r in results_back} == {f"ED{i:03d}" for i in range(1, 11)}
