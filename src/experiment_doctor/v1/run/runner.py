"""``experiment-doctor run``: execute a command and record what was observed.

Capture-only wrapper.  Values enter the record through observation alone:

* exit code comes from ``wait()``, never from reading logs;
* termination status describes the *process*, never the experiment's science
  (exit 0 is recorded as SUCCESS "process exited 0", not "training worked");
* artifact membership comes from a before/after tree diff of sha256s;
* anything not observable (a spawn that never happened, a child still running
  after a failed kill) stays UNKNOWN with a note.

The lock is verified against its own canonical hash before the run so the
lock -> run provenance chain cannot silently reference tampered evidence.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus
from experiment_doctor.v1.capture import environment, runtime
from experiment_doctor.v1.lock.schema import ExperimentLock
from experiment_doctor.v1.lock.writer import LOCK_FILENAME, hash_file
from experiment_doctor.v1.run.schema import (
    ArtifactsBlock,
    EnvironmentBlock,
    ExecutionBlock,
    ExperimentRunRecord,
    LockReference,
    RuntimeBlock,
    TerminationStatus,
    observed,
)

RUN_FILENAME = "experiment.run.json"
BUNDLE_DIRNAME = "experiment-evidence"
STDOUT_FILENAME = "stdout.log"
STDERR_FILENAME = "stderr.log"

#: Bookkeeping paths the wrapper itself writes; never experiment artifacts.
EXCLUDED_NAMES = {LOCK_FILENAME, RUN_FILENAME, BUNDLE_DIRNAME, STDOUT_FILENAME, STDERR_FILENAME}
EXCLUDED_DIRNAMES = {"__pycache__", ".pytest_cache"}


@dataclass
class RunOutcome:
    record: ExperimentRunRecord
    run_path: Path
    evidence_dir: Path
    exit_code: int


def snapshot_tree(root: Path) -> dict[str, str]:
    """relpath -> sha256 for every file under ``root`` (wrapper bookkeeping excluded)."""
    files: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts[0] in EXCLUDED_NAMES or any(p in EXCLUDED_DIRNAMES for p in rel.parts):
            continue
        try:
            files[rel.as_posix()] = hash_file(path)
        except OSError:
            files[rel.as_posix()] = "sha256:unreadable"
    return files


def _field_diff(before: dict[str, str], after: dict[str, str], label: str) -> ProvenanceField[Any]:
    items = {
        name: digest for name, digest in sorted(after.items()) if _differs(name, before, after)
    }
    if not items:
        return ProvenanceField(
            value=None,
            status=ProvenanceStatus.UNKNOWN,
            confidence_note=f"artifacts.{label}: no {label.replace('_files', ' changes')} observed",
        )
    return observed(items, f"tree sha256 diff around execution: {label}")


def _differs(name: str, before: dict[str, str], after: dict[str, str]) -> bool:
    return name not in before or before[name] != after[name]


def _deleted_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(name for name in before if name not in after)


def load_and_verify_lock(lock_arg: str, root: Path) -> tuple[ExperimentLock | None, Path]:
    candidates = [Path(lock_arg)] if Path(lock_arg).is_absolute() else [root / lock_arg]
    if candidates[0].name != LOCK_FILENAME:
        candidates.append(root / LOCK_FILENAME)
    for candidate in candidates:
        if candidate.is_file():
            return _verify_lock_file(candidate), candidate
    return None, candidates[0]


def _verify_lock_file(path: Path) -> ExperimentLock | None:
    """Return the lock only if it parses *and* its stored hash covers its body."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stored = data.pop("lock_hash", None)
        body = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        recomputed = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
        if stored is None or stored != recomputed:
            return None
        return ExperimentLock.model_validate(data)
    except (OSError, ValueError, ValidationError):
        return None


def _wait_gracefully(proc: subprocess.Popen, timeout: float | None) -> tuple[int | None, str]:
    """Return (exit code or None, timeout note).  No inference on any path."""
    try:
        return proc.wait(timeout=timeout), ""
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            return proc.wait(
                timeout=30
            ), f"kill signal delivered; exited after timeout of {timeout}s"
        except subprocess.TimeoutExpired:
            return None, (
                f"timeout of {timeout}s elapsed and the kill did not take effect; "
                "the child may still be running"
            )
    except KeyboardInterrupt:
        try:
            return proc.wait(timeout=30), "local keyboard interrupt; child reaped after"
        except subprocess.TimeoutExpired:
            return None, "local keyboard interrupt; final exit status not observable"


def _status_for(
    returncode: int | None, timeout_note: str, spawn_failed: bool
) -> tuple[TerminationStatus, str]:
    if spawn_failed:
        return TerminationStatus.UNKNOWN, "process never spawned; no exit status was observed"
    if returncode is None:
        if timeout_note.startswith("timeout"):
            return TerminationStatus.TIMEOUT, timeout_note
        return TerminationStatus.UNKNOWN, timeout_note or "exit status not observable"
    if timeout_note.startswith("kill signal delivered"):
        # the wrapper delivered the kill; that observation outranks the raw status
        return TerminationStatus.TIMEOUT, timeout_note
    if timeout_note.startswith("local keyboard interrupt"):
        return TerminationStatus.INTERRUPTED, timeout_note
    if returncode < 0 or returncode == 130:
        return (
            TerminationStatus.INTERRUPTED,
            f"observed exit status {returncode} (signal/SIGINT convention)",
        )
    if returncode == 0:
        return TerminationStatus.SUCCESS, "process exited 0; no claim about training quality"
    return TerminationStatus.FAILED, f"process exited {returncode}"


def run_experiment(
    root: Path,
    command: list[str],
    lock_arg: str = LOCK_FILENAME,
    run_filename: str = RUN_FILENAME,
    timeout: float | None = None,
) -> RunOutcome:
    root = root.resolve()
    lock, lock_path = load_and_verify_lock(lock_arg, root)

    evidence_dir = root / BUNDLE_DIRNAME
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_log = root / STDOUT_FILENAME
    err_log = root / STDERR_FILENAME

    before = snapshot_tree(root)
    start_time = runtime.now_iso()

    spawn_error: str | None = None
    returncode: int | None = None
    timeout_note = ""
    pid_field: ProvenanceField[Any] = ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    if shutil.which(command[0]) is None:
        spawn_error = f"command not found on PATH: {command[0]}"
    else:
        with (
            out_log.open("wb") as out_handle,
            err_log.open("wb") as err_handle,
        ):
            try:
                proc = subprocess.Popen(command, cwd=root, stdout=out_handle, stderr=err_handle)
            except OSError as exc:
                spawn_error = f"process could not be spawned: {exc}"
            else:
                pid_field = observed(proc.pid, "wrapper-reported child pid")
                returncode, timeout_note = _wait_gracefully(proc, timeout)

    end_time = runtime.now_iso()
    after = snapshot_tree(root)

    if lock is None:
        lock_ref = LockReference(
            lock_hash=ProvenanceField(
                value=None,
                status=ProvenanceStatus.UNKNOWN,
                confidence_note=(
                    "stored lock hash does not cover its body (tampered or malformed); "
                    "no lock_hash is asserted"
                ),
            ),
            lock_path=observed(_rel(lock_path, root), "lock file found on disk at this path"),
        )
    else:
        lock_ref = LockReference(
            lock_hash=observed(lock.compute_hash(), "sha256 over the lock canonical body"),
            lock_path=observed(_rel(lock_path, root), "lock file found on disk at this path"),
        )

    status, status_note = _status_for(returncode, timeout_note, spawn_error is not None)

    execution = ExecutionBlock(
        command=observed(list(command), "argv passed to the wrapper after '--'"),
        cwd=runtime.working_directory(root),
        pid=pid_field,
        start_time=observed(start_time, "system clock (UTC) immediately before spawn"),
        end_time=observed(end_time, "system clock (UTC) immediately after the wait returned"),
        exit_code=(
            observed(returncode, "exit status returned by wait()")
            if returncode is not None
            else ProvenanceField(
                value=None,
                status=ProvenanceStatus.UNKNOWN,
                confidence_note=spawn_error or timeout_note or "exit status not observable",
            )
        ),
    )
    runtime_block = RuntimeBlock(
        stdout_path=observed(_rel(out_log, root), "file written by the wrapper during execution"),
        stderr_path=observed(_rel(err_log, root), "file written by the wrapper during execution"),
        timeout_status=(
            observed(timeout_note, "wrapper kill/wait outcome after the timeout")
            if timeout_note
            else _no_timeout_field(timeout, spawn_error)
        ),
        timeout_seconds=(
            observed(timeout, "--timeout option") if timeout is not None else _unknown_timeout()
        ),
    )
    deleted = _deleted_paths(before, after)
    artifacts = ArtifactsBlock(
        created_files=_field_diff(before, after, "created_files"),
        modified_files=_field_diff(before, after, "modified_files"),
        note=observed(
            "artifact membership from a full-tree sha256 diff; deletions are reported in "
            f"this note, not as fields: {deleted or 'none'}; wrapper bookkeeping excluded"
            + (f"; {timeout_note}" if timeout_note else ""),
            "before/after snapshot diff",
        ),
    )

    record = ExperimentRunRecord(
        lock_reference=lock_ref,
        execution=execution,
        runtime=runtime_block,
        artifacts=artifacts,
        environment=EnvironmentBlock(
            python_version=environment.python_version(),
            packages=environment.installed_packages(),
            platform=environment.platform_info(),
        ),
        termination_status=status,
    )
    if status_note:
        record.artifacts.note.value = f"{record.artifacts.note.value}; termination: {status_note}"

    run_path = root / run_filename
    sealed = record.seal()
    run_path.write_text(
        json.dumps(sealed.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _assemble_bundle(lock_path, run_path, out_log, err_log, evidence_dir)

    if spawn_error is not None:
        exit_code = 127  # shell convention for "command not found", not an inference
    elif returncode is None:
        exit_code = 1
    elif returncode < 0:
        exit_code = 1
    else:
        exit_code = returncode
    return RunOutcome(
        record=sealed, run_path=run_path, evidence_dir=evidence_dir, exit_code=exit_code
    )


def _no_timeout_field(timeout: float | None, spawn_error: str | None) -> ProvenanceField[str]:
    note = (
        "no timeout configured"
        if timeout is None
        else "timeout option given but the process never ran"
        if spawn_error
        else "process exited before any timeout"
    )
    return ProvenanceField(
        value=None,
        status=ProvenanceStatus.UNKNOWN,
        confidence_note=f"runtime.timeout_status: {note}",
    )


def _unknown_timeout() -> ProvenanceField[float]:
    return ProvenanceField(
        value=None,
        status=ProvenanceStatus.UNKNOWN,
        confidence_note="runtime.timeout_seconds: no --timeout given",
    )


def _rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _assemble_bundle(
    lock_path: Path, run_path: Path, out_log: Path, err_log: Path, evidence_dir: Path
) -> None:
    """Minimal evidence bundle: lock, run record, stdout, stderr.  No compression,
    no upload, no signing (Phase 2 boundary)."""
    for source in (lock_path, run_path, out_log, err_log):
        if source.is_file() and source.resolve() != (evidence_dir / source.name).resolve():
            shutil.copy2(source, evidence_dir / source.name)
