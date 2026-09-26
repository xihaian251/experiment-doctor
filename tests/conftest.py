"""Shared fixtures: the miniature gmmvi project used for adapter end-to-end tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from experiment_doctor.adapters.gmmvi import GMMVIAdapter
from experiment_doctor.audit import audit_project
from experiment_doctor.scanner import scan_project
from experiment_doctor.schema import ExperimentProject

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "mini_gmmvi"

#: The fixture's repo/ and extracted/ halves, mirroring the real archive layout.
FIXTURE_REPO = FIXTURE_ROOT / "repo"
FIXTURE_RESULTS = FIXTURE_ROOT / "extracted" / "evaluations" / "results"


def _mini_scan(reported: Path | None) -> ExperimentProject:
    adapter = GMMVIAdapter(
        FIXTURE_ROOT,
        repo_root=FIXTURE_REPO,
        results_root=FIXTURE_RESULTS,
        reported_table=reported,
    )
    project = scan_project(FIXTURE_ROOT, adapter=adapter)
    audit_project(project)
    return project


@pytest.fixture(scope="session")
def mini_scan() -> Callable[[str | None], ExperimentProject]:
    """Scan the miniature project; pass a reported-table file name to compare against."""
    cache: dict[str | None, ExperimentProject] = {}

    def scan(reported: str | None = None) -> ExperimentProject:
        if reported not in cache:
            cache[reported] = _mini_scan(FIXTURE_ROOT / reported if reported else None)
        return cache[reported]

    return scan


@pytest.fixture(scope="session")
def mini_project(mini_scan: Callable[[str | None], ExperimentProject]) -> ExperimentProject:
    return mini_scan("reported_matched.json")


@pytest.fixture(scope="session")
def mini_project_plain(mini_scan: Callable[[str | None], ExperimentProject]) -> ExperimentProject:
    return mini_scan(None)


@pytest.fixture(scope="session")
def mini_project_mismatch(
    mini_scan: Callable[[str | None], ExperimentProject],
) -> ExperimentProject:
    return mini_scan("reported_mismatch.json")
