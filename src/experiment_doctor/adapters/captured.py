"""Captured-evidence adapter (v1 Phase 4): an evidence bundle -> the v0.1 audit model.

``experiment-doctor init`` and ``run`` already grade every leaf they write.  This
adapter is a translator, not a second observer: it carries each ``ProvenanceField``
across with its evidence grade intact and relocates the citation onto the bundle
file the value was read from, so a rule can attach a claim to a run-local artifact.

It opens nothing else.  It reads no log line, so no metric can enter here (an
unlabelled ``accuracy=99`` in stdout is not a metric of record), and no exit code
is read as an experiment outcome -- ``TerminationStatus`` says how the *process*
ended, which is not one of the causes ``TerminationCause`` enumerates.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.scanner import (
    AdapterSpec,
    ExperimentAdapter,
    make_artifact_ref,
    register,
    relative,
)
from experiment_doctor.schema import (
    ArtifactRef,
    ArtifactRole,
    ArtifactType,
    ExperimentFamily,
    ExperimentRun,
    FamilyKind,
    RunStatus,
    RuntimeEnvironment,
    TerminationCause,
)
from experiment_doctor.v1.lock.schema import ExperimentLock
from experiment_doctor.v1.run.runner import (
    BUNDLE_DIRNAME,
    RUN_FILENAME,
    STDERR_FILENAME,
    STDOUT_FILENAME,
)
from experiment_doctor.v1.run.schema import ExperimentRunRecord, TerminationStatus

T = TypeVar("T")

LOCK_FILENAME = "experiment.lock.json"

#: The wrapper inflicts a wall-clock deadline itself, so a timeout is the one stop
#: cause it can state without interpreting anything.  Every other end of process
#: says nothing about why the experiment stopped.
_CAUSE_BY_TERMINATION: dict[TerminationStatus, TerminationCause] = {
    TerminationStatus.TIMEOUT: TerminationCause.TIME_LIMIT,
}
_STATUS_BY_TERMINATION: dict[TerminationStatus, RunStatus] = {
    TerminationStatus.TIMEOUT: RunStatus.TRUNCATED_TIME_LIMIT,
}


def _read_model(model: type[BaseModel], path: Path) -> Any | None:
    """Parse one bundle file, or None when it is absent or unreadable.

    A corrupt evidence file must not raise out of ``detect()``: the bundle stays
    visible to ``verify``, which is the component that reports damage.
    """
    try:
        return model.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, ValidationError):
        return None


def _find_bundle(root: Path) -> Path | None:
    """Locate the bundle: ``root/experiment-evidence/``, or ``root`` itself."""
    nested = root / BUNDLE_DIRNAME
    if (nested / LOCK_FILENAME).is_file() or (nested / RUN_FILENAME).is_file():
        return nested
    if (root / LOCK_FILENAME).is_file() or (root / RUN_FILENAME).is_file():
        return root
    return None


def _transfer(field: ProvenanceField[T], path: str, key: str) -> ProvenanceField[T]:
    """Carry a bundle field into the audit schema with its grade untouched.

    Only an already-evidenced field gets a file citation, and the citation states
    where the value is written down -- never what it proves.  UNKNOWN and
    CONFLICTING fields cross over exactly as the bundle recorded them.
    """
    if field.status not in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED):
        return field.model_copy()
    note = field.source.note if field.source is not None else None
    source = SourceRef(path=path, key=key, note=note)
    return field.model_copy(update={"source": source})


def _joined(field: ProvenanceField[Any], path: str, key: str, sep: str) -> ProvenanceField[str]:
    """Render a list-valued bundle field as the single string the schema asks for."""
    if field.status not in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED):
        return ProvenanceField.unknown(note=field.confidence_note)
    value = field.value
    text = sep.join(str(item) for item in value) if isinstance(value, list) else str(value)
    original = field.source.note if field.source is not None else None
    note = f"rendered from a list; {original}" if original else "rendered from a list"
    return ProvenanceField.of(
        text, field.status, SourceRef(path=path, key=key, note=note), field.confidence_note
    )


def _epoch(field: ProvenanceField[str], path: str, key: str) -> ProvenanceField[float]:
    """Re-express a recorded UTC timestamp as the seconds-since-epoch v0.1 stores.

    A format conversion of an observed value, not a reconstruction of an
    unobserved one: an unparseable or absent timestamp stays UNKNOWN.
    """
    if field.status not in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED):
        return ProvenanceField.unknown(note=field.confidence_note)
    try:
        stamp = datetime.fromisoformat(str(field.value))
    except (TypeError, ValueError):
        return ProvenanceField.unknown(
            note=f"{key}: recorded timestamp {field.value!r} is not ISO-8601"
        )
    note = f"recorded as {field.value}"
    source = SourceRef(path=path, key=key, note=note)
    return ProvenanceField.of(stamp.timestamp(), field.status, source)


class CapturedProjectAdapter(ExperimentAdapter):
    """One evidence bundle: one lock, one run record, one family, one run."""

    name = "captured"

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._bundle: Path | None = None
        self._lock: ExperimentLock | None = None
        self._record: ExperimentRunRecord | None = None
        self._loaded = False

    def describe(self) -> str:
        return (
            "captured: reads experiment.lock.json + experiment.run.json written by "
            "experiment-doctor init/run and transfers each field with its evidence grade "
            "intact; emits no metric, no experiment outcome and no upgraded provenance"
        )

    @property
    def notes(self) -> list[str]:
        return [
            "scope: one bundle directory holds one lock and one run record, so this "
            "adapter discovers exactly one family of one run; it does not search the tree "
            "for further bundles",
            "the bundle carries no method, task or dataset name, so run identity (ED001) "
            "cannot be compared and stays UNKNOWN rather than being read off the directory",
            "metrics are absent by design: v1 Phase 2 captures stdout and stderr as logs "
            "and reads no value out of them",
        ]

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._bundle = _find_bundle(self.root)
        if self._bundle is None:
            return
        self._lock = _read_model(ExperimentLock, self._bundle / LOCK_FILENAME)
        self._record = _read_model(ExperimentRunRecord, self._bundle / RUN_FILENAME)

    def detect(self, root: Path) -> float:
        self._load()
        if self._bundle is None:
            return 0.0
        if self._lock is not None and self._record is not None:
            return 1.0
        # A bundle missing either half is still a bundle; audit what exists and let
        # the provenance of the missing half report UNKNOWN.
        return 0.7

    def _lock_source(self) -> str:
        if self._bundle is None:
            return LOCK_FILENAME
        return relative(self.root, self._bundle / LOCK_FILENAME)

    def _run_source(self) -> str:
        if self._bundle is None:
            return RUN_FILENAME
        return relative(self.root, self._bundle / RUN_FILENAME)

    def _family_id(self) -> str:
        if self._lock is not None:
            identity = self._lock.identity.experiment_id
            if identity.has_value and identity.value:
                return str(identity.value)
        if self._bundle is None:
            return "captured"
        return relative(self.root, self._bundle)

    def _run_id(self) -> str:
        return f"{self._family_id()}#{Path(self._run_source()).name}"

    def _artifact_refs(self) -> list[ArtifactRef]:
        """The bundle's own files, typed and roled by what they are for."""
        if self._bundle is None:
            return []
        roles: dict[str, tuple[ArtifactType, ArtifactRole]] = {
            LOCK_FILENAME: (ArtifactType.CONFIG, ArtifactRole.CONFIG),
            RUN_FILENAME: (ArtifactType.SUMMARY, ArtifactRole.RESULT),
            STDOUT_FILENAME: (ArtifactType.LOG, ArtifactRole.LOG),
            STDERR_FILENAME: (ArtifactType.LOG, ArtifactRole.LOG),
        }
        refs: list[ArtifactRef] = []
        for name, (kind, role) in roles.items():
            path = self._bundle / name
            if not path.is_file():
                continue
            ref = make_artifact_ref(self.root, path)
            refs.append(ref.model_copy(update={"artifact_type": kind, "artifact_role": role}))
        return refs

    def discover_families(self, root: Path) -> list[ExperimentFamily]:
        self._load()
        if self._bundle is None or (self._lock is None and self._record is None):
            return []
        family_id = self._family_id()
        return [
            ExperimentFamily(
                family_id=family_id,
                name=Path(family_id).name,
                kind=FamilyKind.UNKNOWN,
                result_dir=relative(self.root, self._bundle) if self._bundle else None,
                declared_repetitions=ProvenanceField.unknown(
                    note="a captured bundle holds one execution and declares no repetition count"
                ),
                membership_rule=ProvenanceField.unknown(
                    note="nothing in the bundle states which aggregation this run joined"
                ),
                run_ids=[self._run_id()],
            )
        ]

    def discover_runs(self, root: Path) -> list[ExperimentRun]:
        self._load()
        if self._bundle is None or (self._lock is None and self._record is None):
            return []
        run = ExperimentRun(
            run_id=self._run_id(),
            family_id=self._family_id(),
            result_slot_index=None,
            status=RunStatus.UNKNOWN,
            artifacts=self._artifact_refs(),
        )
        lock, record = self._lock, self._record
        if lock is not None:
            self._apply_lock(run, lock)
        if record is not None:
            self._apply_record(run, record, lock)
        return [run]

    def _apply_lock(self, run: ExperimentRun, lock: ExperimentLock) -> None:
        src = self._lock_source()
        run.seed = _transfer(lock.randomness.seed, src, "randomness.seed")
        run.seed_derivation = _transfer(lock.randomness.seed_source, src, "randomness.seed_source")
        run.code_repository = _transfer(lock.code.repository, src, "code.repository")
        run.code_commit = _transfer(lock.code.commit, src, "code.commit")
        run.code_dirty = _transfer(lock.code.dirty, src, "code.dirty")
        run.config_source = _joined(
            lock.configuration.config_files, src, "configuration.config_files", ", "
        )
        run.resolved_config = ProvenanceField.unknown(
            note=(
                f"{src}: the lock records config file paths and their content hashes, never the "
                "merged values the process trained under"
            )
        )
        run.dataset = ProvenanceField.unknown(
            note=(
                f"{src}: dataset.paths names files where declared; it is not a dataset identity "
                "and was not read as one"
            )
        )
        run.dataset_version = ProvenanceField.unknown(
            note="no bundle artifact names a dataset version"
        )

    def _apply_record(
        self, run: ExperimentRun, record: ExperimentRunRecord, lock: ExperimentLock | None
    ) -> None:
        src = self._run_source()
        if record.execution.command.has_value:
            run.command = _joined(record.execution.command, src, "execution.command", " ")
        elif run.command.status is ProvenanceStatus.UNKNOWN and lock is not None:
            # Nothing executed, so the declared command is the only one on record.
            run.command = _transfer(
                lock.execution.command, self._lock_source(), "execution.command"
            )
        run.start_time = _epoch(record.execution.start_time, src, "execution.start_time")
        run.end_time = _epoch(record.execution.end_time, src, "execution.end_time")
        budget = record.runtime.timeout_seconds
        if budget.status in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED):
            # The deadline the wrapper set for this run is the budget it died against.
            run.compute_budget = _transfer(
                ProvenanceField.of(
                    f"wall-clock limit of {budget.value}s set by the run wrapper",
                    budget.status,
                    budget.source,
                    budget.confidence_note,
                ),
                src,
                "runtime.timeout_seconds",
            )
        self._apply_termination(run, record, src)
        run.runtime_environment = self._runtime(record, src)

    @staticmethod
    def _apply_termination(run: ExperimentRun, record: ExperimentRunRecord, src: str) -> None:
        status = record.termination_status
        cause = _CAUSE_BY_TERMINATION.get(status)
        if cause is None:
            # Recorded in the note, never in the value: an exit code is a fact about
            # the process, not one of the reasons the schema enumerates for a run
            # having stopped.
            run.termination_cause = ProvenanceField.unknown(
                note=(
                    f"{src}: the wrapper observed termination_status={status.value}, which "
                    "describes how the process ended, not why the experiment stopped"
                )
            )
            return
        run.termination_cause = ProvenanceField.of(
            cause,
            ProvenanceStatus.CONFIRMED,
            SourceRef(path=src, key="runtime.timeout_status", note="deadline set by the wrapper"),
        )
        mapped = _STATUS_BY_TERMINATION.get(status)
        if mapped is not None:
            run.status = mapped

    @staticmethod
    def _runtime(record: ExperimentRunRecord, src: str) -> RuntimeEnvironment:
        env = record.environment
        return RuntimeEnvironment(
            python_version=_transfer(env.python_version, src, "environment.python_version"),
            framework_versions=_transfer(env.packages, src, "environment.packages"),
            cuda_version=ProvenanceField.unknown(
                note="no bundle artifact records an accelerator or CUDA version"
            ),
            hardware=ProvenanceField.unknown(note="no bundle artifact records the hardware"),
            os=_transfer(env.platform, src, "environment.platform"),
            source_artifacts=[SourceRef(path=src, note="environment block of the run record")],
        )

    def code_repository(self) -> ArtifactRef | None:
        return None


def spec() -> AdapterSpec:
    return AdapterSpec(
        name="captured",
        description=CapturedProjectAdapter(Path(".")).describe(),
        factory=CapturedProjectAdapter,
    )


def install() -> None:
    register(spec())


__all__ = [
    "CapturedProjectAdapter",
    "install",
    "spec",
]
