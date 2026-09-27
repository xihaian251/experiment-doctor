"""``experiment.run.json`` schema (v1 Phase 2): the run-side evidence record.

Every observable leaf is a v0.1 :class:`ProvenanceField`, so the same UNKNOWN
discipline that guards the lock guards the run record: a value without a direct
observation does not enter the file.  Exit codes are read from the wait, never
inferred; success of the *training* is not a field here at all (task book: no
inferring success from exit code, no guessing metrics from stdout).

Design anchor: ``docs/v1/EXPERIMENT_DOCTOR_V1_IMPLEMENTATION_PLAN.md``
section 4; predecessor evidence: ``PHASE1_LOCK_CAPTURE_REPORT.md``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.v1.lock.schema import EnvironmentBlock

SCHEMA_VERSION = "1.0"


def _unknown(name: str) -> ProvenanceField[Any]:
    return ProvenanceField(
        value=None,
        status=ProvenanceStatus.UNKNOWN,
        confidence_note=f"{name}: not observable at run-capture time",
    )


def observed(value: Any, note: str) -> ProvenanceField[Any]:
    """Wrap a direct observation as a CONFIRMED field."""
    return ProvenanceField.of(value, ProvenanceStatus.CONFIRMED, SourceRef(note=note))


class TerminationStatus(str, Enum):
    """How the process ended, as observed by the wrapper.

    ``SUCCESS`` means "the process exited 0" -- a fact about the exit status,
    never a claim that the training converged or is trustworthy.
    """

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    INTERRUPTED = "INTERRUPTED"
    UNKNOWN = "UNKNOWN"


class LockReference(BaseModel):
    """Pointer from the run record back to the lock it was executed under."""

    lock_hash: ProvenanceField[str] = _unknown("lock_reference.lock_hash")
    lock_path: ProvenanceField[str] = _unknown("lock_reference.lock_path")


class ExecutionBlock(BaseModel):
    command: ProvenanceField[list[str]] = _unknown("execution.command")
    cwd: ProvenanceField[str] = _unknown("execution.cwd")
    pid: ProvenanceField[int] = _unknown("execution.pid")
    start_time: ProvenanceField[str] = _unknown("execution.start_time")
    end_time: ProvenanceField[str] = _unknown("execution.end_time")
    exit_code: ProvenanceField[int] = _unknown("execution.exit_code")


class RuntimeBlock(BaseModel):
    stdout_path: ProvenanceField[str] = _unknown("runtime.stdout_path")
    stderr_path: ProvenanceField[str] = _unknown("runtime.stderr_path")
    timeout_status: ProvenanceField[str] = _unknown("runtime.timeout_status")
    timeout_seconds: ProvenanceField[float] = _unknown("runtime.timeout_seconds")


class ArtifactsBlock(BaseModel):
    created_files: ProvenanceField[dict[str, str]] = _unknown("artifacts.created_files")
    modified_files: ProvenanceField[dict[str, str]] = _unknown("artifacts.modified_files")
    note: ProvenanceField[str] = _unknown("artifacts.note")


class ExperimentRunRecord(BaseModel):
    """One record per execution; written by ``experiment-doctor run``."""

    schema_version: str = SCHEMA_VERSION
    lock_reference: LockReference = Field(default_factory=LockReference)
    execution: ExecutionBlock = Field(default_factory=ExecutionBlock)
    runtime: RuntimeBlock = Field(default_factory=RuntimeBlock)
    artifacts: ArtifactsBlock = Field(default_factory=ArtifactsBlock)
    environment: EnvironmentBlock = Field(default_factory=EnvironmentBlock)
    termination_status: TerminationStatus = TerminationStatus.UNKNOWN
    run_hash: str | None = None

    def body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"run_hash"})

    def canonical_json(self) -> str:
        """Same canonicalization contract as the lock (Phase 1 report §1.1)."""
        return json.dumps(self.body(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def compute_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def seal(self) -> ExperimentRunRecord:
        return self.model_copy(update={"run_hash": self.compute_hash()})

    def fields(self) -> Iterator[tuple[str, ProvenanceField[Any]]]:
        for block_name, block in (
            ("lock_reference", self.lock_reference),
            ("execution", self.execution),
            ("runtime", self.runtime),
            ("artifacts", self.artifacts),
            ("environment", self.environment),
        ):
            for field_name, field in vars(block).items():
                if isinstance(field, ProvenanceField):
                    yield f"{block_name}.{field_name}", field
