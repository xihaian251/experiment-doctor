"""Builders for audit unit tests: objects with exactly the evidence a test names."""

from __future__ import annotations

from typing import Any, Sequence

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.schema import (
    AggregationRecord,
    ExperimentFamily,
    ExperimentProject,
    ExperimentRun,
    FamilyKind,
    MetricDirection,
    MetricRecord,
    RunStatus,
)


def make_run(run_id: str, family_id: str = "F/f", **overrides: Any) -> ExperimentRun:
    """A run asserting nothing beyond its identity, unless overridden."""
    fields: dict[str, Any] = {"run_id": run_id, "family_id": family_id, "status": RunStatus.UNKNOWN}
    fields.update(overrides)
    return ExperimentRun(**fields)


def make_family(family_id: str = "F/f", **overrides: Any) -> ExperimentFamily:
    fields: dict[str, Any] = {
        "family_id": family_id,
        "name": family_id.rsplit("/", 1)[-1],
        "kind": FamilyKind.EVALUATION,
        "primary_metric": "-elbo",
    }
    fields.update(overrides)
    return ExperimentFamily(**fields)


def evidenced_seed(value: int) -> ProvenanceField[int]:
    return ProvenanceField.of(
        value, ProvenanceStatus.CONFIRMED, SourceRef(path="seeded_config.yml")
    )


def confirmed_direction(direction: MetricDirection) -> ProvenanceField[MetricDirection]:
    return ProvenanceField.of(
        direction, ProvenanceStatus.CONFIRMED, SourceRef(path="fetch.py", line=1)
    )


def metric(name: str, value: float) -> MetricRecord:
    return MetricRecord(
        name=name,
        value=ProvenanceField.of(value, ProvenanceStatus.CONFIRMED, SourceRef(path=f"{name}.csv")),
        status=ProvenanceStatus.CONFIRMED,
    )


def project_with(
    runs: Sequence[ExperimentRun],
    family: ExperimentFamily,
    aggregations: Sequence[AggregationRecord] = (),
) -> ExperimentProject:
    return ExperimentProject(
        root="unit",
        project_id="unit",
        adapter="unit",
        families=[family],
        runs=list(runs),
        aggregations=list(aggregations),
    )
