"""Builders for audit unit tests: objects with exactly the evidence a test names."""

from __future__ import annotations

from typing import Any, Sequence

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.schema import (
    AggregationRecord,
    ArtifactRef,
    ArtifactType,
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


def attested(
    value: Any,
    path: str,
    line: int | None = None,
    status: ProvenanceStatus = ProvenanceStatus.CONFIRMED,
) -> ProvenanceField[Any]:
    """A value with the citation an evidenced field must have."""
    return ProvenanceField.of(value, status, SourceRef(path=path, line=line))


def artifact(path: str, kind: ArtifactType = ArtifactType.LOG) -> ArtifactRef:
    return ArtifactRef(path=path, artifact_type=kind)


def make_aggregation(**overrides: Any) -> AggregationRecord:
    """A published record that claims nothing: no reported number, no spread, no attestation."""
    fields: dict[str, Any] = {
        "aggregation_id": "F/f/elbo@included",
        "family_id": "F/f",
        "metric_name": "-elbo",
    }
    fields.update(overrides)
    return AggregationRecord(**fields)


def project_with(
    runs: Sequence[ExperimentRun],
    family: ExperimentFamily,
    aggregations: Sequence[AggregationRecord] = (),
    artifacts: Sequence[ArtifactRef] = (),
) -> ExperimentProject:
    return ExperimentProject(
        root="unit",
        project_id="unit",
        adapter="unit",
        families=[family],
        runs=list(runs),
        aggregations=list(aggregations),
        artifacts=list(artifacts),
    )
