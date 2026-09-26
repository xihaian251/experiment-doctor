"""Evidence-graded provenance primitives.

Every suspicious field in an ExperimentRun is a :class:`ProvenanceField`, so the
tool can never present a reconstructed value as if it were recorded by the project.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


class ProvenanceStatus(str, Enum):
    """How well the value of a field is evidenced by project artifacts."""

    CONFIRMED = "CONFIRMED"
    SUPPORTED = "SUPPORTED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"


#: Statuses whose value must be backed by a concrete artifact reference.
_NEEDS_SOURCE = {ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED}


class SourceRef(BaseModel):
    """Where a value came from: file path, key/column/line, or artifact id."""

    path: str | None = None
    key: str | None = None
    line: int | None = None
    artifact_id: str | None = None
    note: str | None = None

    def describe(self) -> str:
        parts: list[str] = []
        if self.path is not None:
            parts.append(self.path)
        if self.line is not None:
            parts.append(f"L{self.line}")
        if self.key is not None:
            parts.append(f"[{self.key}]")
        if self.artifact_id is not None:
            parts.append(f"#{self.artifact_id}")
        return " ".join(parts) if parts else "<no source>"


class ProvenanceField(BaseModel, Generic[T]):
    """A value plus its evidence grade and citation.

    Invariants:

    * ``UNKNOWN`` carries no value (the field is absent from the evidence).
    * ``CONFIRMED``/``SUPPORTED`` must cite a source; without evidence there is
      no confirmation.
    * ``INFERRED`` is the ceiling for anything derived by a heuristic (e.g. a
      metric direction guessed from its name).
    """

    value: T | None = None
    status: ProvenanceStatus = ProvenanceStatus.UNKNOWN
    source: SourceRef | None = None
    confidence_note: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> ProvenanceField[T]:
        if self.status is ProvenanceStatus.UNKNOWN and self.value is not None:
            raise ValueError("UNKNOWN provenance fields must not carry a value")
        if self.status in _NEEDS_SOURCE and self.source is None:
            raise ValueError(f"{self.status.value} provenance fields require a source")
        return self

    @classmethod
    def unknown(cls, note: str | None = None) -> ProvenanceField[T]:
        return cls(value=None, status=ProvenanceStatus.UNKNOWN, confidence_note=note)

    @classmethod
    def of(
        cls,
        value: T,
        status: ProvenanceStatus,
        source: SourceRef | None = None,
        note: str | None = None,
    ) -> ProvenanceField[T]:
        return cls(value=value, status=status, source=source, confidence_note=note)

    @classmethod
    def conflicting(cls, sources: list[SourceRef], note: str | None = None) -> ProvenanceField[T]:
        """Value not assertable because the artifacts disagree."""
        joined = SourceRef(note="; ".join(s.describe() for s in sources)) if sources else None
        return cls(
            value=None,
            status=ProvenanceStatus.CONFLICTING,
            source=joined,
            confidence_note=note,
        )

    @property
    def has_value(self) -> bool:
        return self.value is not None


def unknown_field() -> ProvenanceField[Any]:
    return ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)


class EvidenceCounts(BaseModel):
    """Field-level provenance coverage: counts per evidence status."""

    total: int = 0
    confirmed: int = 0
    supported: int = 0
    inferred: int = 0
    unknown: int = 0
    conflicting: int = 0
    with_value: int = 0
    note: str | None = Field(default=None)

    def add(self, field: ProvenanceField[Any]) -> None:
        self.total += 1
        if field.has_value:
            self.with_value += 1
        match field.status:
            case ProvenanceStatus.CONFIRMED:
                self.confirmed += 1
            case ProvenanceStatus.SUPPORTED:
                self.supported += 1
            case ProvenanceStatus.INFERRED:
                self.inferred += 1
            case ProvenanceStatus.UNKNOWN:
                self.unknown += 1
            case ProvenanceStatus.CONFLICTING:
                self.conflicting += 1
