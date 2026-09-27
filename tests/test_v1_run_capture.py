"""Phase 2 tests: run capture + evidence bundle + provenance chain.

Covers the task-book matrix T1-T7 (exit 0, exit 1, stderr, artifacts, lock-hash
mismatch, spaced args, env isolation) plus the security requirements (no
credential reads/writes, no git history mutation, all writes stay inside the
project) and the capture-only discipline (spawn failure and unclear kills stay
UNKNOWN, timeouts are never inferred).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from experiment_doctor.cli import app
from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus
from experiment_doctor.v1.lock.schema import ExperimentLock
from experiment_doctor.v1.lock.writer import LOCK_FILENAME, DeclaredInputs, build_lock, write_lock
from experiment_doctor.v1.run.runner import BUNDLE_DIRNAME, RUN_FILENAME, RunOutcome, run_experiment
from experiment_doctor.v1.run.schema import TerminationStatus

FIXTURE = Path(__file__).parent / "fixtures" / "v1_run_project"

RUN_KEYS = ("password", "passwd", "secret", "token", "credential", "api_key")


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return proc.stdout.strip()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    write_lock(build_lock(DeclaredInputs(root=root, seed=11)), root / LOCK_FILENAME)
    return root


def _run(project: Path, *extra: str) -> RunOutcome:
    return run_experiment(project, [sys.executable, "train.py", *extra])


# ---- T1: normal exit 0 --------------------------------------------------------


def test_T1_exit0_record_and_chain(project: Path) -> None:
    outcome = _run(project).record
    assert outcome.termination_status is TerminationStatus.SUCCESS
    assert outcome.execution.exit_code.value == 0
    assert outcome.execution.exit_code.status is ProvenanceStatus.CONFIRMED
    assert str(outcome.execution.start_time.value) <= str(outcome.execution.end_time.value)
    # SUCCESS is a statement about the process, never about the training
    note = str(outcome.artifacts.note.value)
    assert "no claim about training quality" in note
    # provenance chain: the run references the lock's canonical hash
    lock_data = json.loads((project / LOCK_FILENAME).read_text(encoding="utf-8"))
    lock = ExperimentLock.model_validate(lock_data)
    assert outcome.lock_reference.lock_hash.value == lock.compute_hash()
    assert outcome.lock_reference.lock_hash.status is ProvenanceStatus.CONFIRMED
    assert outcome.run_hash == outcome.compute_hash()


def test_T1_command_is_observed_not_inferred_from_lock(project: Path) -> None:
    # the lock was init'ed without --command: it stays UNKNOWN there,
    # while the run record captures the argv actually executed.
    outcome = _run(project)
    lock = ExperimentLock.model_validate_json((project / LOCK_FILENAME).read_text("utf-8"))
    assert lock.execution.command.status is ProvenanceStatus.UNKNOWN
    assert outcome.record.execution.command.value[1:] == ["train.py"]  # type: ignore[index]


# ---- T2: exit 1 ----------------------------------------------------------------


def test_T2_exit1_recorded_as_FAILED_not_inferred(project: Path) -> None:
    outcome = _run(project, "--exit", "1")
    assert outcome.record.execution.exit_code.value == 1
    assert outcome.record.termination_status is TerminationStatus.FAILED
    assert outcome.exit_code == 1  # parent mirrors the experiment exit code


# ---- T3: stderr ----------------------------------------------------------------


def test_T3_stderr_captured_to_file(project: Path) -> None:
    outcome = _run(project, "--noise")
    stderr_path = project / outcome.record.runtime.stderr_path.value  # type: ignore[operator]
    assert "synthetic stderr line" in stderr_path.read_text(encoding="utf-8")
    assert outcome.record.runtime.stderr_path.status is ProvenanceStatus.CONFIRMED


# ---- T4: artifacts --------------------------------------------------------------


def test_T4_created_artifact_diff_hashed(project: Path) -> None:
    outcome = _run(project, "--artifact", "run1.csv")
    created = outcome.record.artifacts.created_files
    assert created.status is ProvenanceStatus.CONFIRMED
    assert set(created.value or {}) == {"results/run1.csv"}
    assert str((created.value or {})["results/run1.csv"]).startswith("sha256:")


def test_T4_modified_artifact_detected(project: Path) -> None:
    _run(project, "--artifact", "run1.csv")
    outcome = _run(project, "--artifact", "run1.csv", "--exit", "0")
    modified = outcome.record.artifacts.modified_files
    assert modified.status is ProvenanceStatus.CONFIRMED
    assert set(modified.value or {}) == {"results/run1.csv"}


def test_T4_no_writes_means_nothing_to_report(project: Path) -> None:
    outcome = _run(project)
    assert outcome.record.artifacts.created_files.status is ProvenanceStatus.UNKNOWN
    assert outcome.record.artifacts.modified_files.status is ProvenanceStatus.UNKNOWN


# ---- T5: lock hash mismatch ------------------------------------------------------


def test_T5_tampered_lock_gives_UNKNOWN_reference(project: Path) -> None:
    lock_path = project / LOCK_FILENAME
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    data["randomness"]["seed"]["value"] = 77  # body edit; stored lock_hash kept stale
    lock_path.write_text(json.dumps(data), encoding="utf-8")
    outcome = _run(project)
    ref = outcome.record.lock_reference
    assert ref.lock_hash.value is None
    assert ref.lock_hash.status is ProvenanceStatus.UNKNOWN
    assert "tampered" in str(ref.lock_hash.confidence_note)
    assert ref.lock_path.status is ProvenanceStatus.CONFIRMED


# ---- T6: spaced arguments ---------------------------------------------------------


def test_T6_argument_with_space_survives_argv(project: Path) -> None:
    os.environ["ED SPACE MARKER"] = "isolated-value"
    try:
        outcome = _run(project, "--echo-env", "ED SPACE MARKER")
    finally:
        del os.environ["ED SPACE MARKER"]
    record = outcome.record
    assert record.execution.command.value[-1] == "ED SPACE MARKER"  # type: ignore[index]
    stderr_text = (project / str(record.runtime.stderr_path.value)).read_text(encoding="utf-8")
    assert "ED SPACE MARKER=isolated-value" in stderr_text


def test_T6_command_not_found_is_UNKNOWN_not_FAILED(project: Path) -> None:
    outcome = run_experiment(project, ["definitely-not-a-command-xyz", "train.py"])
    assert outcome.record.execution.exit_code.value is None
    assert outcome.record.execution.exit_code.status is ProvenanceStatus.UNKNOWN
    assert outcome.record.termination_status is TerminationStatus.UNKNOWN
    assert outcome.exit_code == 127


# ---- T7: environment isolation -----------------------------------------------------


def test_T7_child_inherits_and_parent_env_untouched(project: Path) -> None:
    os.environ["ED_RUN_TEST_MARKER"] = "1"
    try:
        outcome = _run(project, "--echo-env", "ED_RUN_TEST_MARKER")
    finally:
        del os.environ["ED_RUN_TEST_MARKER"]
    stderr_text = (project / str(outcome.record.runtime.stderr_path.value)).read_text("utf-8")
    assert "ED_RUN_TEST_MARKER=1" in stderr_text
    assert "ED_RUN_TEST_MARKER" not in os.environ
    assert outcome.record.environment.python_version.status is ProvenanceStatus.CONFIRMED


# ---- timeout (never inferred) ---------------------------------------------------------


def test_timeout_kills_and_is_recorded(project: Path) -> None:
    outcome = run_experiment(
        project, [sys.executable, "-c", "import time; time.sleep(30)"], timeout=2
    )
    assert outcome.record.termination_status is TerminationStatus.TIMEOUT
    assert outcome.record.runtime.timeout_status.status is ProvenanceStatus.CONFIRMED
    assert outcome.record.runtime.timeout_seconds.value == 2
    assert outcome.exit_code == 1


# ---- evidence bundle ------------------------------------------------------------------


def test_bundle_has_exactly_the_four_files(project: Path) -> None:
    _run(project, "--artifact", "run1.csv")
    bundle = project / BUNDLE_DIRNAME
    assert sorted(p.name for p in bundle.iterdir()) == sorted(
        [LOCK_FILENAME, RUN_FILENAME, "stdout.log", "stderr.log"]
    )
    locked_copy = json.loads((bundle / LOCK_FILENAME).read_text(encoding="utf-8"))
    assert ExperimentLock.model_validate(locked_copy).lock_hash is not None


def test_run_record_serialization_keeps_unknown_empty(project: Path) -> None:
    outcome = _run(project)
    body = json.loads(outcome.record.canonical_json())
    for block in body.values():
        if isinstance(block, dict):
            for field in block.values():
                if isinstance(field, dict) and field.get("status") == "UNKNOWN":
                    assert field.get("value") is None


def test_run_hash_detects_record_tampering(project: Path) -> None:
    outcome = _run(project)
    record = outcome.record
    mutated = record.model_copy(
        update={
            "execution": record.execution.model_copy(
                update={
                    "exit_code": ProvenanceField.of(
                        999, ProvenanceStatus.CONFIRMED, record.execution.exit_code.source
                    )
                }
            )
        }
    )
    assert mutated.compute_hash() != record.run_hash


# ---- security (Step 5) -------------------------------------------------------------------


def test_security_no_writes_outside_project(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "i")
    from experiment_doctor.v1.lock.writer import DeclaredInputs, build_lock, write_lock

    write_lock(build_lock(DeclaredInputs(root=root)), root / LOCK_FILENAME)

    def listing(folder: Path) -> set[str]:
        return {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()}

    outside_before = {p for p in tmp_path.rglob("*") if p.is_file() and root not in p.parents}
    run_experiment(root, [sys.executable, "train.py", "--artifact", "a.csv"])
    outside_after = {p for p in tmp_path.rglob("*") if p.is_file() and root not in p.parents}
    assert outside_before == outside_after
    assert listing(root)  # sanity: the run did write inside


def test_security_no_git_history_mutation(project: Path) -> None:
    head_before = _git(project, "rev-parse", "HEAD")
    log_before = (project / ".git" / "logs" / "HEAD").read_bytes()
    run_experiment(project, [sys.executable, "train.py", "--artifact", "a.csv"])
    assert _git(project, "rev-parse", "HEAD") == head_before  # no new commit
    assert (project / ".git" / "logs" / "HEAD").read_bytes() == log_before  # no ref moves


def test_security_never_reads_credentials(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert RUN_KEYS  # credential-name list also used by the source scan below
    monkeypatch.setenv("ED_CANARY_PASSWORD", "CANARY-VALUE")
    _run(project, "--noise")
    evidence_text = "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in (project / BUNDLE_DIRNAME).iterdir()
        if p.is_file()
    )
    assert "CANARY-VALUE" not in evidence_text  # env canary never echoed into evidence


def test_security_new_sources_contain_no_credential_logic() -> None:
    root = Path(__file__).parent.parent / "src" / "experiment_doctor" / "v1"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        if any(key in text for key in RUN_KEYS):
            offenders.append(path.name)
    assert offenders == []


# ---- CLI -------------------------------------------------------------------------------


def test_cli_run_success_and_mirrored_exit(project: Path) -> None:
    runner = CliRunner()
    ok = runner.invoke(app, ["run", "--path", str(project), "--", sys.executable, "train.py"])
    assert ok.exit_code == 0, ok.output
    assert "termination: SUCCESS" in ok.output
    bad = runner.invoke(
        app, ["run", "--path", str(project), "--", sys.executable, "train.py", "--exit", "2"]
    )
    assert bad.exit_code == 2  # parent CLI exit code mirrors the experiment
    data = json.loads((project / RUN_FILENAME).read_text(encoding="utf-8"))
    assert data["execution"]["exit_code"]["value"] == 2
    assert data["schema_version"] == "1.0"


def test_cli_run_requires_lock(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--path", str(tmp_path), "--", sys.executable, "-V"])
    assert result.exit_code != 0


def test_cli_all_commands_registered(project: Path) -> None:
    runner = CliRunner()
    for name in ("scan", "audit", "rules", "adapters", "init", "run"):
        assert runner.invoke(app, [name, "--help"]).exit_code == 0
