"""The provenance invariants that make an absent field different from a wrong one."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from experiment_doctor.provenance import (
    EvidenceCounts,
    ProvenanceField,
    ProvenanceStatus,
    SourceRef,
)
from experiment_doctor.schema import MetricDirection


def test_provenance_status() -> None:
    field = ProvenanceField.of(7, ProvenanceStatus.CONFIRMED, SourceRef(path="a.yml", line=3))
    assert field.value == 7 and field.status is ProvenanceStatus.CONFIRMED
    assert field.source is not None and field.source.path == "a.yml"

    unknown = ProvenanceField[int].unknown(note="nothing recorded it")
    assert unknown.value is None and unknown.has_value is False

    # UNKNOWN may not smuggle a value in: absence must stay absence.
    with pytest.raises(ValidationError):
        ProvenanceField(value=1, status=ProvenanceStatus.UNKNOWN)
    # CONFIRMED/SUPPORTED may not float free of a citation.
    with pytest.raises(ValidationError):
        ProvenanceField(value=1, status=ProvenanceStatus.CONFIRMED)
    with pytest.raises(ValidationError):
        ProvenanceField(value="x", status=ProvenanceStatus.SUPPORTED)
    # INFERRED is allowed without a source because it declares its own weakness.
    inferred = ProvenanceField.of(
        MetricDirection.MINIMIZE, ProvenanceStatus.INFERRED, note="name heuristic"
    )
    assert inferred.source is None and inferred.confidence_note == "name heuristic"


def test_conflicting_provenance() -> None:
    left = SourceRef(path="run_0_config.yml", key="seed")
    right = SourceRef(path="slurm_log.txt", key="seed")
    field = ProvenanceField[int].conflicting([left, right], note="the two records disagree")

    assert field.status is ProvenanceStatus.CONFLICTING
    assert field.value is None, "a conflicted field must not assert either value"
    assert field.source is not None
    assert "run_0_config.yml" in (field.source.note or "")
    assert "slurm_log.txt" in (field.source.note or "")

    counts = EvidenceCounts()
    for item in (
        ProvenanceField.of(1, ProvenanceStatus.CONFIRMED, left),
        ProvenanceField.of(2, ProvenanceStatus.SUPPORTED, right),
        ProvenanceField.of(3, ProvenanceStatus.INFERRED),
        ProvenanceField.unknown(),
        field,
    ):
        counts.add(item)

    assert (counts.total, counts.confirmed, counts.supported, counts.inferred) == (5, 1, 1, 1)
    assert (counts.unknown, counts.conflicting, counts.with_value) == (1, 1, 3)
