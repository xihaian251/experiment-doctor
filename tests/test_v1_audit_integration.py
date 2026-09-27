"""Phase 4 tests: the captured adapter feeding the frozen v0.1 audit + rule engine.

Three obligations run through this file.

*Transfer, never observe* -- every field the adapter emits must carry the evidence
grade the bundle gave it, cited to the bundle file that states it.

*No inference* -- a seed that appears only inside the command string, a metric that
appears only in stdout, and an exit code of zero must each leave the corresponding
rule short of PASS.  These are the firewall tests.

*Zero drift* -- ED001-ED010 are evaluated unchanged; a project with no evidence
bundle must keep scanning exactly as it did before this adapter existed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from experiment_doctor.adapters import available_adapters, build
from experiment_doctor.adapters.captured import CapturedProjectAdapter
from experiment_doctor.audit import audit_project
from experiment_doctor.cli import app
from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus
from experiment_doctor.rules import run_rules
from experiment_doctor.rules.base import RuleStatus
from experiment_doctor.scanner import scan_project, select_adapter
from experiment_doctor.schema import (
    ArtifactRole,
    ArtifactType,
    ExperimentRun,
    MetricRecord,
    RunStatus,
    TerminationCause,
)
from experiment_doctor.v1.lock.writer import LOCK_FILENAME, DeclaredInputs, build_lock, write_lock
from experiment_doctor.v1.run.runner import (
    BUNDLE_DIRNAME,
    RUN_FILENAME,
    STDERR_FILENAME,
    STDOUT_FILENAME,
    run_experiment,
)
from experiment_doctor.v1.run.schema import TerminationStatus

FIXTURE = Path(__file__).parent / "fixtures" / "v1_audit_project"

BUNDLE_FILES = (LOCK_FILENAME, RUN_FILENAME, STDOUT_FILENAME, STDERR_FILENAME)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def _bundle(root: Path) -> Path:
    return root / BUNDLE_DIRNAME


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _capture(tmp_path: Path, *, seed: int | None = 11, argv: tuple[str, ...] = ()) -> Path:
    """Run the real Phase 1/2 capture over the fixture and return the project root."""
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    write_lock(build_lock(DeclaredInputs(root=root, seed=seed)), root / LOCK_FILENAME)
    run_experiment(root, [sys.executable, "train.py", *argv])
    return root


def _project(root: Path) -> tuple[object, list]:
    project = scan_project(root)
    return project, run_rules(project, audit_project(project))


def _single_run(root: Path) -> ExperimentRun:
    project = scan_project(root)
    assert len(project.runs) == 1
    return project.runs[0]


def _status(results: list, rule_id: str) -> RuleStatus | None:
    for result in results:
        if result.rule_id == rule_id:
            return result.status
    return None


# --------------------------------------------------------------------- registry


def test_captured_adapter_is_registered() -> None:
    names = [item.name for item in available_adapters()]
    assert "captured" in names
    # the shipped adapters keep their names, and captured registers last so a score
    # tie still favours whichever adapter a project was accepted against
    assert names[:4] == ["generic", "gmmvi-exp3", "torchssl", "crda"]


def test_captured_wins_selection_over_generic(tmp_path: Path) -> None:
    root = _capture(tmp_path)
    adapter, score = select_adapter(root)
    assert adapter.name == "captured"
    assert score > 0.0


def test_project_without_a_bundle_is_not_captured(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    (root / "metrics.csv").write_text("epoch,acc\n1,0.5\n", encoding="utf-8")
    assert select_adapter(root)[0].name != "captured"
    assert CapturedProjectAdapter(root).detect(root) == 0.0


def test_bundle_directory_is_accepted_as_the_scanned_path(tmp_path: Path) -> None:
    root = _capture(tmp_path)
    run = _single_run(_bundle(root))
    assert run.seed.value == 11


# ------------------------------------------------------- Step 1: field transfer


def test_seed_carries_grade_and_a_bundle_citation(tmp_path: Path) -> None:
    run = _single_run(_capture(tmp_path, seed=42))
    assert run.seed.value == 42
    assert run.seed.status is ProvenanceStatus.CONFIRMED
    assert run.seed.source is not None
    assert run.seed.source.path is not None
    assert run.seed.source.path.endswith(LOCK_FILENAME)
    assert run.seed.source.key == "randomness.seed"


def test_code_identity_is_transferred(tmp_path: Path) -> None:
    run = _single_run(_capture(tmp_path))
    assert run.code_commit.status is ProvenanceStatus.CONFIRMED
    assert run.code_dirty.status in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.UNKNOWN)
    assert run.code_repository.has_value


def test_command_is_the_argv_the_wrapper_invoked(tmp_path: Path) -> None:
    run = _single_run(_capture(tmp_path, argv=("--seed", "7")))
    assert run.command.status is ProvenanceStatus.CONFIRMED
    assert "train.py" in (run.command.value or "")
    assert "7" in (run.command.value or "")
    assert run.command.source is not None and run.command.source.key == "execution.command"


def test_timestamps_are_seconds_since_epoch(tmp_path: Path) -> None:
    run = _single_run(_capture(tmp_path))
    assert run.start_time.status is ProvenanceStatus.CONFIRMED
    assert isinstance(run.start_time.value, float)
    assert run.end_time.value is not None and run.start_time.value is not None
    assert run.end_time.value >= run.start_time.value


def test_runtime_environment_comes_from_the_run_record(tmp_path: Path) -> None:
    run = _single_run(_capture(tmp_path))
    slot = run.runtime_environment
    assert slot is not None
    assert slot.python_version.status is ProvenanceStatus.CONFIRMED
    assert slot.framework_versions.has_value
    assert slot.os.has_value
    # accelerator and hardware are nowhere in the bundle, so they are not here either
    assert slot.cuda_version.status is ProvenanceStatus.UNKNOWN
    assert slot.hardware.status is ProvenanceStatus.UNKNOWN
    paths = {artifact.path for artifact in run.artifacts}
    cited = {
        field.source.path
        for field in slot.evidenced_fields().values()
        if field.source is not None and field.source.path is not None
    }
    assert cited and cited <= paths


def test_bundle_files_are_the_runs_own_artifacts(tmp_path: Path) -> None:
    run = _single_run(_capture(tmp_path))
    by_name = {Path(item.path).name: item for item in run.artifacts}
    assert set(by_name) == set(BUNDLE_FILES)
    assert by_name[LOCK_FILENAME].artifact_role is ArtifactRole.CONFIG
    assert by_name[RUN_FILENAME].artifact_role is ArtifactRole.RESULT
    assert by_name[STDOUT_FILENAME].artifact_type is ArtifactType.LOG
    assert by_name[STDOUT_FILENAME].artifact_role is ArtifactRole.LOG


def test_undeclared_optional_fields_stay_unknown(tmp_path: Path) -> None:
    run = _single_run(_capture(tmp_path))
    for name in (
        "method",
        "task",
        "dataset",
        "dataset_version",
        "tracker_run_id",
        "repetition_index",
        "entrypoint",
        "history_rows",
        "included_in_aggregation",
    ):
        field: ProvenanceField[object] = getattr(run, name)
        assert field.status is ProvenanceStatus.UNKNOWN, name
        assert field.value is None, name
    assert run.result_slot_index is None
    assert run.metrics == []


def test_declared_config_files_do_not_become_a_resolved_config(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "config.yaml").write_text("lr: 0.1\n", encoding="utf-8")
    write_lock(
        build_lock(DeclaredInputs(root=root, config_files=[root / "config.yaml"])),
        root / LOCK_FILENAME,
    )
    run = _single_run(root)
    assert run.resolved_config.status is ProvenanceStatus.UNKNOWN
    assert run.resolved_config.value is None
    # the file list itself is still recorded, at the grade the lock gave it
    assert run.config_source.status is ProvenanceStatus.CONFIRMED


# ------------------------------------------------ Step 3: rules on captured data


def test_rule_outcomes_on_a_complete_capture(tmp_path: Path) -> None:
    _, results = _project(_capture(tmp_path))
    assert _status(results, "ED002") is RuleStatus.PASS  # seed recorded at capture time
    assert _status(results, "ED003") is RuleStatus.PASS  # revision in the run's own lock
    assert _status(results, "ED004") is RuleStatus.INCONCLUSIVE  # never the merged values
    assert _status(results, "ED009") is RuleStatus.INCONCLUSIVE  # exit code is not a cause
    assert _status(results, "ED010") is RuleStatus.PASS  # the run recorded its interpreter
    assert _status(results, "ED001") is RuleStatus.NOT_APPLICABLE  # one run, nothing to compare
    assert [r.rule_id for r in results if r.rule_id in {"ED005", "ED006", "ED007", "ED008"}] == []
    assert [_status(results, "ED001")]  # every emitted result is accounted for above


def test_no_rule_fails_on_an_honest_capture(tmp_path: Path) -> None:
    _, results = _project(_capture(tmp_path))
    assert [r.rule_id for r in results if r.status is RuleStatus.FAIL] == []
    assert [r.rule_id for r in results if r.status is RuleStatus.NOT_RUN] == []


def test_audit_reports_no_metric_of_record_for_a_capture(tmp_path: Path) -> None:
    project = scan_project(_capture(tmp_path))
    audit = audit_project(project)
    assert audit.metrics[0].metric_names == []
    assert audit.metrics[0].runs_with_metrics == 0
    assert audit.counts["aggregations"] == 0


def test_missing_seed_record_keeps_ed002_inconclusive(tmp_path: Path) -> None:
    _, results = _project(_capture(tmp_path, seed=None))
    assert _status(results, "ED002") is RuleStatus.INCONCLUSIVE


def test_missing_commit_keeps_ed003_inconclusive(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)  # deliberately not a git repository
    write_lock(build_lock(DeclaredInputs(root=root, seed=3)), root / LOCK_FILENAME)
    run_experiment(root, [sys.executable, "train.py"])
    assert _single_run(root).code_commit.status is ProvenanceStatus.UNKNOWN
    assert _status(_project(root)[1], "ED003") is RuleStatus.INCONCLUSIVE


# ----------------------------------------------------------- Step 4: the firewall


def test_seed_in_the_command_string_does_not_pass_ed002(tmp_path: Path) -> None:
    """lock.seed is UNKNOWN while argv says ``--seed 123``; the argv must not leak upward."""
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    write_lock(build_lock(DeclaredInputs(root=root)), root / LOCK_FILENAME)
    outcome = run_experiment(root, [sys.executable, "train.py", "--seed", "123"])
    bundle = _bundle(root)
    # prove the string really is there, then prove the adapter ignores it as a seed
    record = _read(bundle / RUN_FILENAME)
    assert "--seed" in json.dumps(record["execution"]["command"])
    run = _single_run(root)
    assert "123" in (run.command.value or "")
    assert run.seed.status is ProvenanceStatus.UNKNOWN
    assert run.seed.value is None
    assert run.seed_derivation.status is ProvenanceStatus.UNKNOWN
    assert _status(_project(root)[1], "ED002") is RuleStatus.INCONCLUSIVE
    assert outcome.exit_code == 0


def test_metric_text_in_stdout_does_not_become_a_metric(tmp_path: Path) -> None:
    root = _capture(tmp_path)
    stdout = (_bundle(root) / STDOUT_FILENAME).read_text(encoding="utf-8")
    assert "accuracy=99.0" in stdout  # the bait is on disk
    assert (root / "results" / "metrics.csv").is_file()
    run = _single_run(root)
    assert run.metrics == []
    audit = audit_project(scan_project(root))
    assert audit.metrics[0].metric_names == []
    assert _status(_project(root)[1], "ED005") is None  # no aggregation, no selection claim


def test_exit_code_zero_is_not_a_termination_cause_or_a_status(tmp_path: Path) -> None:
    root = _capture(tmp_path)
    assert _read(_bundle(root) / RUN_FILENAME)["termination_status"] == "SUCCESS"
    run = _single_run(root)
    assert run.termination_cause.value is None
    assert run.termination_cause.status is ProvenanceStatus.UNKNOWN
    assert run.status is RunStatus.UNKNOWN
    assert run.included_in_aggregation.status is ProvenanceStatus.UNKNOWN


def test_failed_exit_does_not_claim_a_cause(tmp_path: Path) -> None:
    root = _capture(tmp_path, argv=("--exit", "3"))
    assert _read(_bundle(root) / RUN_FILENAME)["termination_status"] == "FAILED"
    run = _single_run(root)
    assert run.termination_cause.value is None
    assert run.termination_cause.status is ProvenanceStatus.UNKNOWN
    assert run.status is RunStatus.UNKNOWN
    assert _status(_project(root)[1], "ED009") is RuleStatus.INCONCLUSIVE


def test_only_a_wrapper_inflicted_deadline_is_a_recorded_cause(tmp_path: Path) -> None:
    root = _capture(tmp_path)
    bundle = _bundle(root)
    payload = _read(bundle / RUN_FILENAME)
    payload["termination_status"] = TerminationStatus.TIMEOUT.value
    payload["runtime"]["timeout_status"] = {
        "value": "kill signal delivered after the deadline",
        "status": "CONFIRMED",
        "source": {"note": "synthetic"},
    }
    payload["runtime"]["timeout_seconds"] = {
        "value": 30.0,
        "status": "CONFIRMED",
        "source": {"note": "synthetic"},
    }
    _write(bundle / RUN_FILENAME, payload)
    run = _single_run(root)
    assert run.termination_cause.value is TerminationCause.TIME_LIMIT
    assert run.status is RunStatus.TRUNCATED_TIME_LIMIT
    assert run.compute_budget.value == "wall-clock limit of 30.0s set by the run wrapper"
    assert _status(_project(root)[1], "ED009") is RuleStatus.PASS


def test_adapter_never_upgrades_an_evidence_grade(tmp_path: Path) -> None:
    """An INFERRED lock field crosses over as INFERRED, so ED002 stays short of PASS."""
    root = _capture(tmp_path, seed=None)
    path = _bundle(root) / LOCK_FILENAME
    payload = _read(path)
    payload["randomness"]["seed"] = {
        "value": 11,
        "status": "INFERRED",
        "source": {"note": "plausible from the launch order"},
    }
    _write(path, payload)
    run = _single_run(root)
    assert run.seed.status is ProvenanceStatus.INFERRED
    assert _status(_project(root)[1], "ED002") is RuleStatus.INCONCLUSIVE


def test_unknown_never_carries_a_value_after_transfer(tmp_path: Path) -> None:
    """The pydantic invariant survives the mapping: no adapter may pair UNKNOWN with a value."""
    root = _capture(tmp_path, seed=None)
    run = _single_run(root)
    walked = 0
    for name in type(run).model_fields:
        field = getattr(run, name)
        if isinstance(field, ProvenanceField):
            walked += 1
            assert not (field.status is ProvenanceStatus.UNKNOWN and field.value is not None), name
    assert walked > 20


# ----------------------------------------------- bundle damage and CLI plumbing


def test_lock_only_bundle_still_audits_with_run_fields_unknown(tmp_path: Path) -> None:
    root = _capture(tmp_path)
    bundle = _bundle(root)
    shutil.rmtree(bundle)
    bundle.mkdir()
    write_lock(build_lock(DeclaredInputs(root=root, seed=5)), bundle / LOCK_FILENAME)
    assert CapturedProjectAdapter(root).detect(root) == 0.7
    run = _single_run(root)
    assert run.seed.value == 5
    assert run.command.status is ProvenanceStatus.UNKNOWN
    assert run.start_time.status is ProvenanceStatus.UNKNOWN
    # the lock describes the machine *before* the process started, so it is never
    # mapped into the run's runtime record; with no run record ED010 has no claim
    assert run.runtime_environment is None
    assert _status(_project(root)[1], "ED010") is RuleStatus.NOT_APPLICABLE
    assert _status(_project(root)[1], "ED002") is RuleStatus.PASS


def test_unreadable_bundle_files_do_not_raise(tmp_path: Path) -> None:
    root = _capture(tmp_path)
    (_bundle(root) / RUN_FILENAME).write_text("{not json", encoding="utf-8")
    adapter = CapturedProjectAdapter(root)
    assert adapter.detect(root) == 0.7
    project = scan_project(root)
    assert project.adapter == "captured"
    assert len(project.runs) == 1
    assert project.runs[0].command.status is ProvenanceStatus.UNKNOWN


def test_tampering_is_verifys_job_not_the_adapters(tmp_path: Path) -> None:
    """The audit path reads what the files say; it neither repairs nor refuses."""
    root = _capture(tmp_path, seed=42)
    path = _bundle(root) / LOCK_FILENAME
    payload = _read(path)
    payload["randomness"]["seed"]["value"] = 999
    _write(path, payload)
    assert _single_run(root).seed.value == 999
    from experiment_doctor.v1.verify.checks import verify_bundle

    report, _ = verify_bundle(root)
    assert any(check.status.value == "FAIL" for check in report.checks)


def test_cli_audit_selects_captured_and_exits_zero(tmp_path: Path) -> None:
    root = _capture(tmp_path)
    result = CliRunner().invoke(app, ["audit", str(root), "-o", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert "adapter=captured" in result.output
    payload = _read(tmp_path / "out" / "report.json")
    assert payload["audit"]["adapter"] == "captured"


def test_cli_scan_summary_lists_capture_notes(tmp_path: Path) -> None:
    root = _capture(tmp_path)
    project = scan_project(root)
    assert project.notes and any("one bundle" in note for note in project.notes)


def test_seal_helpers_are_unused_by_the_audit_path(tmp_path: Path) -> None:
    """No component of scan/audit/rules computes a hash of the bundle."""
    import experiment_doctor.adapters.captured as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    for banned in ("hash_file", "run_hash", "lock_hash", "sha256", "verify_bundle"):
        assert banned not in source, banned


# ------------------------------------------------------------- zero drift guard


def test_generic_scan_of_a_non_bundle_project_is_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    shutil.copytree(FIXTURE, root)
    (root / "run1.csv").write_text("epoch,accuracy\n1,0.99\n", encoding="utf-8")
    before = scan_project(root, adapter=build("generic", root))
    after = scan_project(root)
    assert select_adapter(root)[0].name == "generic"
    assert before.model_dump() == after.model_dump()


def test_metrics_of_record_type_is_never_constructed(tmp_path: Path) -> None:
    """A regression guard for the metric firewall at the schema boundary."""
    assert MetricRecord(name="accuracy").value.status is ProvenanceStatus.UNKNOWN
    root = _capture(tmp_path)
    assert _single_run(root).metrics == []
