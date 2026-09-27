"""Phase 1 tests: lock schema + capture layer + ``init``.

Covers the task-book matrix T1-T5 (commit recoverable, dirty detection, python
version, command capture, unknown-stays-unknown) plus the UNKNOWN serialization
invariant and the canonical-hash contract that Phase 4's verify will build on.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from experiment_doctor.cli import app
from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.v1.lock.schema import ExperimentLock
from experiment_doctor.v1.lock.writer import LOCK_FILENAME, DeclaredInputs, build_lock, write_lock

FIXTURE = Path(__file__).parent / "fixtures" / "v1_basic_project"


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
    return root


def _declared(root: Path, **kw: object) -> DeclaredInputs:
    return DeclaredInputs(root=root, **kw)  # type: ignore[arg-type]


# ---- T1: git commit is captured ----------------------------------------------


def test_T1_commit_captured(project: Path) -> None:
    lock = build_lock(_declared(project))
    assert lock.code.commit.status is ProvenanceStatus.CONFIRMED
    assert lock.code.commit.value == _git(project, "rev-parse", "HEAD")
    assert lock.code.repository.value is not None


# ---- T2: dirty state and diff hash -------------------------------------------


def test_T2_dirty_detected_with_diff_hash(project: Path) -> None:
    (project / "train.py").write_text("# edited\n", encoding="utf-8")
    lock = build_lock(_declared(project))
    assert lock.code.dirty.value is True
    assert lock.code.dirty.status is ProvenanceStatus.CONFIRMED
    assert str(lock.code.diff_hash.value).startswith("sha256:")


def test_T2_clean_tree_has_no_diff_hash(project: Path) -> None:
    lock = build_lock(_declared(project))
    assert lock.code.dirty.value is False
    assert lock.code.dirty.status is ProvenanceStatus.CONFIRMED
    assert lock.code.diff_hash.value is None
    assert lock.code.diff_hash.status is ProvenanceStatus.UNKNOWN


def test_T2_diff_hash_tracks_untracked_content(project: Path) -> None:
    (project / "extra.py").write_text("x = 1\n", encoding="utf-8")
    first = build_lock(_declared(project)).code.diff_hash.value
    (project / "extra.py").write_text("x = 2\n", encoding="utf-8")
    second = build_lock(_declared(project)).code.diff_hash.value
    assert first != second and first is not None


# ---- T3: environment capture ---------------------------------------------------


def test_T3_python_version_captured(project: Path) -> None:
    import sys

    lock = build_lock(_declared(project))
    assert lock.environment.python_version.value == sys.version.split()[0]
    assert lock.environment.python_version.status is ProvenanceStatus.CONFIRMED


def test_environment_packages_and_platform(project: Path) -> None:
    lock = build_lock(_declared(project))
    packages = lock.environment.packages.value
    assert isinstance(packages, dict) and packages.get("pydantic")
    assert lock.environment.platform.status is ProvenanceStatus.CONFIRMED


# ---- T4: command capture is declaration, not inference -------------------------


def test_T4_declared_command_captured(project: Path) -> None:
    lock = build_lock(_declared(project, command="python train.py --config config.yaml"))
    assert lock.execution.command.value == "python train.py --config config.yaml"
    assert lock.execution.command.status is ProvenanceStatus.CONFIRMED


def test_T4_start_time_stays_unknown_in_phase1(project: Path) -> None:
    lock = build_lock(_declared(project))
    assert lock.execution.start_time.status is ProvenanceStatus.UNKNOWN
    assert lock.execution.cwd.value == str(project.resolve())


# ---- T5: unknown stays unknown --------------------------------------------------


def test_T5_command_not_inferred_when_undeclared(project: Path) -> None:
    lock = build_lock(_declared(project))
    assert lock.execution.command.value is None
    assert lock.execution.command.status is ProvenanceStatus.UNKNOWN


def test_T5_seed_is_not_read_out_of_config(project: Path) -> None:
    # config.yaml literally contains "seed: 3"; capture must not pick it up.
    lock = build_lock(_declared(project))
    assert lock.randomness.seed.value is None
    assert lock.randomness.seed.status is ProvenanceStatus.UNKNOWN
    assert lock.randomness.seed_source.status is ProvenanceStatus.UNKNOWN


def test_declared_seed_is_confirmed(project: Path) -> None:
    lock = build_lock(_declared(project, seed=3))
    assert lock.randomness.seed.value == 3
    assert lock.randomness.seed.status is ProvenanceStatus.CONFIRMED


def test_T5_non_git_directory_keeps_code_unknown(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    shutil.copytree(FIXTURE, root)
    lock = build_lock(_declared(root))
    for field in (lock.code.repository, lock.code.commit, lock.code.dirty, lock.code.diff_hash):
        assert field.value is None
        assert field.status is ProvenanceStatus.UNKNOWN


def test_T5_undeclared_dataset_stays_unknown(project: Path) -> None:
    lock = build_lock(_declared(project))
    assert lock.dataset.paths.status is ProvenanceStatus.UNKNOWN
    assert lock.dataset.fingerprints.status is ProvenanceStatus.UNKNOWN


# ---- fingerprints ----------------------------------------------------------------


def test_dataset_and_config_fingerprints(project: Path) -> None:
    lock = build_lock(
        _declared(project, dataset_paths=[Path("dataset")], config_files=[Path("config.yaml")])
    )
    fps = lock.dataset.fingerprints
    assert fps.status is ProvenanceStatus.CONFIRMED
    assert set(fps.value or {}) == {"dataset/"}
    assert str((fps.value or {})["dataset/"]).startswith("sha256:")
    assert set(lock.configuration.config_hash.value or {}) == {"config.yaml"}


def test_missing_declared_path_is_noted_not_fabricated(project: Path) -> None:
    lock = build_lock(_declared(project, dataset_paths=[Path("nope.csv")]))
    assert lock.dataset.fingerprints.value is None
    assert lock.dataset.fingerprints.status is ProvenanceStatus.UNKNOWN
    assert lock.dataset.paths.status is ProvenanceStatus.CONFIRMED  # declared list is a fact


# ---- canonical serialization / hash -----------------------------------------------


def test_canonical_json_is_repeatable_and_order_independent(project: Path) -> None:
    lock = build_lock(_declared(project, seed=1))
    body = json.loads(lock.canonical_json())
    assert lock.canonical_json() == json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert lock.canonical_json() == lock.canonical_json()
    assert lock.seal().lock_hash == lock.compute_hash()


def test_lock_hash_detects_tampering(project: Path) -> None:
    from experiment_doctor.provenance import ProvenanceField

    sealed = build_lock(_declared(project, seed=1)).seal()
    tampered = sealed.model_copy(
        update={
            "randomness": sealed.randomness.model_copy(
                update={
                    "seed": ProvenanceField.of(
                        999, ProvenanceStatus.CONFIRMED, sealed.randomness.seed.source
                    )
                }
            )
        }
    )
    assert tampered.compute_hash() != sealed.lock_hash


def test_unknown_fields_serialize_without_value(project: Path) -> None:
    lock = build_lock(_declared(project))
    body = json.loads(lock.canonical_json())
    for block in body.values():
        if not isinstance(block, dict):
            continue
        for field in block.values():
            if isinstance(field, dict) and field.get("status") == "UNKNOWN":
                assert field.get("value") is None


# ---- CLI -------------------------------------------------------------------------


def test_cli_init_writes_valid_lock(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "init",
            str(project),
            "--command",
            "python train.py",
            "--seed",
            "3",
            "--config",
            "config.yaml",
            "--dataset",
            "dataset",
        ],
    )
    assert result.exit_code == 0, result.output
    lock_path = project / LOCK_FILENAME
    assert lock_path.is_file()
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["code"]["commit"]["status"] == "CONFIRMED"
    assert data["randomness"]["seed"]["value"] == 3
    assert data["execution"]["start_time"]["status"] == "UNKNOWN"
    recomputed = ExperimentLock.model_validate(data)
    assert recomputed.lock_hash == recomputed.compute_hash()


def test_cli_legacy_commands_still_registered(project: Path) -> None:
    runner = CliRunner()
    for name in ("scan", "audit", "rules", "adapters"):
        assert runner.invoke(app, [name, "--help"]).exit_code == 0
    assert runner.invoke(app, ["init", "--help"]).exit_code == 0


def test_write_lock_roundtrip(project: Path, tmp_path: Path) -> None:
    lock = build_lock(_declared(project, seed=7)).seal()
    target = write_lock(lock, tmp_path / "out.json")
    restored = ExperimentLock.model_validate(json.loads(target.read_text(encoding="utf-8")))
    assert restored.canonical_json() == lock.canonical_json()
    assert restored.lock_hash == lock.lock_hash
