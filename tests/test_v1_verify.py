"""Phase 3 tests: deterministic verification of evidence bundles (V001-V006).

Tamper matrix T1-T7 from the task book plus the anti-inference firewall (no
stdout metric, exit-code-meaning or UNKNOWN field may ever produce a PASS or
FAIL verdict) and the write-boundary guarantees (verify only writes its own
two output files, byte-inside the bundle).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from experiment_doctor.cli import app
from experiment_doctor.v1.lock.writer import LOCK_FILENAME, DeclaredInputs, build_lock, write_lock
from experiment_doctor.v1.run.runner import BUNDLE_DIRNAME, RUN_FILENAME, run_experiment
from experiment_doctor.v1.verify.checks import verify_bundle
from experiment_doctor.v1.verify.schema import CheckStatus

FIXTURE = Path(__file__).parent / "fixtures" / "v1_verify_project"


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


def make_bundle(tmp_path: Path, *extra: str, with_git: bool = True) -> Path:
    """Produce a real Phase 1+2 bundle, then drop project-root bookkeeping
    so the bundle alone is what verify must judge (the shipped-evidence case)."""
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    if with_git:
        _git(root, "init", "-q")
        _git(root, "add", ".")
        _git(root, "commit", "-q", "-m", "init")
    write_lock(build_lock(DeclaredInputs(root=root, seed=3)), root / LOCK_FILENAME)
    run_experiment(root, [sys.executable, "train.py", *extra])
    for name in ("stdout.log", "stderr.log", LOCK_FILENAME, RUN_FILENAME):
        (root / name).unlink(missing_ok=True)
    (root / "experiment-evidence" / "verify.json").unlink(missing_ok=True)
    return root / BUNDLE_DIRNAME


def _statuses(bundle: Path) -> dict[str, str]:
    report, _ = verify_bundle(bundle)
    return {c.check_id: c.status.value for c in report.checks}


# ---- T1: clean bundle -----------------------------------------------------------


def test_T1_clean_bundle_all_pass(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    statuses = _statuses(bundle)
    assert statuses == {
        "V001": "PASS",
        "V002": "PASS",
        "V003": "PASS",
        "V004": "PASS",
        "V005": "PASS",
        "V006": "PASS",
    }


def test_report_is_deterministic(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    first, _ = verify_bundle(bundle)
    second, _ = verify_bundle(bundle)
    assert first.canonical_json() == second.canonical_json()
    assert first.digest() == second.digest()


def test_verify_writes_only_its_own_two_outputs(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    watched = ("experiment.lock.json", "experiment.run.json", "stdout.log", "stderr.log")
    before = {name: (bundle / name).read_bytes() for name in watched}
    runner = CliRunner()
    result = runner.invoke(app, ["verify", str(bundle)])
    assert result.exit_code == 0, result.output
    after = {name: (bundle / name).read_bytes() for name in watched}
    assert before == after  # lock/run/logs byte-identical: no repair, no rewrite
    assert sorted(p.name for p in bundle.iterdir()) == sorted(
        [*watched, "verify.json", "verify.md"]
    )  # exactly two new files, both ours
    assert (bundle.parent / "verify.json").exists() is False  # writes stay in the bundle


# ---- T2: lock content edited -----------------------------------------------------


def test_T2_lock_tamper_fails_V001_only(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    data = json.loads((bundle / LOCK_FILENAME).read_text(encoding="utf-8"))
    data["randomness"]["seed"]["value"] = 42  # stored lock_hash kept stale
    (bundle / LOCK_FILENAME).write_text(json.dumps(data), encoding="utf-8")
    statuses = _statuses(bundle)
    assert statuses["V001"] == "FAIL"
    # the lock body changed after the run was sealed, so the run's recorded
    # lock hash no longer matches what the bundle lock recomputes to: the
    # chain check catches the edit from the other side, honestly.
    assert statuses["V002"] == "FAIL"
    assert statuses["V003"] == "PASS"
    report, _ = verify_bundle(bundle)
    assert report.exit_code == 1


# ---- T3: run content edited ------------------------------------------------------


def test_T3_run_tamper_fails_V003(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    data = json.loads((bundle / RUN_FILENAME).read_text(encoding="utf-8"))
    # edit a claim without recomputing the seal: exactly what a forger who
    # never saw the canonicalization contract would do
    data["lock_reference"]["lock_hash"]["value"] = "sha256:" + "0" * 64
    (bundle / RUN_FILENAME).write_text(json.dumps(data), encoding="utf-8")
    report, _ = verify_bundle(bundle)
    statuses = {c.check_id: c.status.value for c in report.checks}
    assert statuses["V003"] == "FAIL"  # body no longer matches run_hash seal
    assert statuses["V001"] == "PASS"
    assert report.exit_code == 1


def test_T3b_forged_lock_reference_fails_V002(tmp_path: Path) -> None:
    # a reference edit that keeps the seal consistent is impossible (run_hash
    # covers it), so this case reuses an unsigned legacy record path: patch
    # run_hash too, exactly like an external forger would.
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    path = bundle / RUN_FILENAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data["lock_reference"]["lock_hash"]["value"] = "sha256:" + "f" * 64
    data["run_hash"] = None  # forger drops the seal rather than recomputing
    path.write_text(json.dumps(data), encoding="utf-8")
    statuses = _statuses(bundle)
    assert statuses["V003"] == "FAIL"  # no valid seal over the body
    assert statuses["V002"] == "FAIL"  # and the claim contradicts the bundle lock


# ---- T4: missing bundle member ----------------------------------------------------


def test_T4_missing_stdout_log_fails_V004(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    (bundle / "stdout.log").unlink()
    statuses = _statuses(bundle)
    assert statuses["V004"] == "FAIL"
    assert statuses["V001"] == "PASS"


# ---- T5: artifact not findable at verify time -------------------------------------


def test_T5_deleted_artifact_is_INCONCLUSIVE_not_deletion_verdict(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    (bundle.parent / "results" / "run1.csv").unlink()  # project copy gone, bundle has none
    report, _ = verify_bundle(bundle)
    v005 = next(c for c in report.checks if c.check_id == "V005")
    assert v005.status is CheckStatus.INCONCLUSIVE
    assert "NOT read as deletion" in v005.message
    assert report.exit_code == 0  # INCONCLUSIVE alone never exits 1


def test_T5b_artifact_content_swap_fails_V005(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    target = bundle.parent / "results" / "run1.csv"
    target.write_text("epoch,acc\n1,0.999\n", encoding="utf-8")  # keep name, swap bytes
    statuses = _statuses(bundle)
    assert statuses["V005"] == "FAIL"


# ---- T6: out-of-bundle path claim ---------------------------------------------------


def test_T6_absolute_path_escaping_bundle_fails_V006(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    path = bundle / RUN_FILENAME
    data = json.loads(path.read_text(encoding="utf-8"))
    outside = str(tmp_path.parent / "somewhere_else.log")
    data["runtime"]["stdout_path"]["value"] = outside  # unsigned edit also breaks V003
    path.write_text(json.dumps(data), encoding="utf-8")
    statuses = _statuses(bundle)
    assert statuses["V006"] == "FAIL"
    assert any(outside in message for message in _evidence(bundle))


def _evidence(bundle: Path) -> list[str]:
    report, _ = verify_bundle(bundle)
    return [item for check in report.checks for item in check.evidence]


def test_T6b_declared_output_dir_escape_fails_V006(tmp_path: Path) -> None:
    # a run record whose stdout/stderr claim lives outside the project
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    path = bundle / RUN_FILENAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data["runtime"]["stderr_path"]["value"] = str(Path("C:/Windows/stderr.log"))
    path.write_text(json.dumps(data), encoding="utf-8")
    statuses = _statuses(bundle)
    assert statuses["V006"] == "FAIL"


# ---- T7: legacy Phase 2 bundle stays verifiable -------------------------------------


def test_T7_phase2_bundle_still_verifies(tmp_path: Path) -> None:
    # A Phase 2 bundle IS a v1.0-phase2 artifact (schema_version 1.0).  Verify
    # it, then ship the bundle ALONE (project root deleted) and re-verify:
    # the hash/seal checks must not depend on the originating machine.
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    assert _statuses(bundle)["V005"] == "PASS"  # artifact still under the project
    shipped = tmp_path / "shipped-bundle"
    os.replace(bundle, shipped)  # same-volume atomic rename (Windows-safe)

    def _unreadonly(func: object, path: str, exc: object) -> None:  # git objects are read-only
        os.chmod(path, stat.S_IWRITE)
        assert callable(func)
        func(path)

    shutil.rmtree(tmp_path / "proj", onerror=_unreadonly)
    statuses = _statuses(tmp_path / "shipped-bundle")
    assert statuses["V001"] == "PASS"
    assert statuses["V002"] == "PASS"
    assert statuses["V003"] == "PASS"
    assert statuses["V004"] == "PASS"
    assert statuses["V006"] == "PASS"
    assert statuses["V005"] == "INCONCLUSIVE"  # honest: artifact not findable now


# ---- UNKNOWN / absence semantics -----------------------------------------------------


def test_unknown_lock_reference_is_INCONCLUSIVE_not_FAIL(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    bad_lock = root / LOCK_FILENAME
    write_lock(build_lock(DeclaredInputs(root=root)), bad_lock)
    data = json.loads(bad_lock.read_text(encoding="utf-8"))
    data["identity"]["created_at"]["value"] = "bogus"  # seal goes stale
    bad_lock.write_text(json.dumps(data), encoding="utf-8")
    run_experiment(root, [sys.executable, "train.py"])  # run refuses to trust the lock
    report, bundle = verify_bundle(root)
    statuses = {c.check_id: c.status.value for c in report.checks}
    assert statuses["V001"] == "FAIL"
    assert statuses["V002"] == "INCONCLUSIVE"  # UNKNOWN claim, not a mismatch
    assert statuses["V006"] == "PASS"


# ---- anti-inference firewall (Step 5) --------------------------------------------------


def test_firewall_stdout_metrics_change_nothing(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    (bundle / "stdout.log").write_text(
        "accuracy=99.9 f1=1.0 best_epoch=7 converged\n", encoding="utf-8"
    )
    assert all(value == "PASS" for value in _statuses(bundle).values())
    (bundle / "stdout.log").write_text("NaN loss, diverged, OOM\n", encoding="utf-8")
    assert all(value == "PASS" for value in _statuses(bundle).values())


def test_firewall_exit_code_zero_is_never_a_success_claim(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)  # exits 0, writes nothing
    report, _ = verify_bundle(bundle)
    statuses = {c.check_id: c.status.value for c in report.checks}
    assert statuses["V005"] == "NOT_APPLICABLE"  # no claims, no verdict
    assert report.exit_code == 0
    assert not any("train" in c.message.lower() for c in report.checks)


def test_firewall_no_scores_and_only_four_statuses(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    report, _ = verify_bundle(bundle)
    text = report.canonical_json().lower()
    # NB: ProvenanceField.confidence_note is the v0.1 evidence annotation, not a
    # score; the ban targets invented aggregate metrics as JSON keys.
    for banned in ("overall_score", "trust_score", '"score"', '"confidence"', '"verdict"'):
        assert banned not in text
    assert {c.status for c in report.checks} <= {
        CheckStatus.PASS,
        CheckStatus.FAIL,
        CheckStatus.INCONCLUSIVE,
        CheckStatus.NOT_APPLICABLE,
    }
    assert [c.check_id for c in report.checks] == ["V001", "V002", "V003", "V004", "V005", "V006"]


# ---- CLI ---------------------------------------------------------------------------


def test_cli_verify_exit_codes(tmp_path: Path) -> None:
    runner = CliRunner()
    good = make_bundle(tmp_path / "good", "--artifact", "run1.csv")
    assert runner.invoke(app, ["verify", str(good)]).exit_code == 0

    bad = make_bundle(tmp_path / "bad", "--artifact", "run1.csv")
    data = json.loads((bad / RUN_FILENAME).read_text(encoding="utf-8"))
    data["execution"]["exit_code"]["value"] = 12345  # sealed body edited, seal not recomputed
    (bad / RUN_FILENAME).write_text(json.dumps(data), encoding="utf-8")
    result = runner.invoke(app, ["verify", str(bad)])
    assert result.exit_code == 1  # FAIL -> 1

    only_inconclusive = make_bundle(tmp_path / "inconclusive", "--artifact", "run1.csv")
    shutil.rmtree(only_inconclusive.parent / "results")
    assert runner.invoke(app, ["verify", str(only_inconclusive)]).exit_code == 0

    empty_dir = tmp_path / "nothing"
    empty_dir.mkdir()
    assert runner.invoke(app, ["verify", str(empty_dir)]).exit_code != 0


def test_cli_project_dir_input_accepted(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path, "--artifact", "run1.csv")
    result = CliRunner().invoke(app, ["verify", str(bundle.parent)])
    assert result.exit_code == 0, result.output


def test_cli_all_commands_registered(tmp_path: Path) -> None:
    runner = CliRunner()
    for name in ("scan", "audit", "rules", "adapters", "init", "run", "verify"):
        assert runner.invoke(app, [name, "--help"]).exit_code == 0
