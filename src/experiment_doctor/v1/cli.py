"""``experiment-doctor init``: capture a lock for the current project state.

Additive v1.0 command; the four v0.1 subcommands are untouched.  init writes
``experiment.lock.json`` and nothing else -- it never edits training code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from experiment_doctor.v1.lock.writer import LOCK_FILENAME, DeclaredInputs, build_lock, write_lock
from experiment_doctor.v1.run.runner import RUN_FILENAME, load_and_verify_lock, run_experiment
from experiment_doctor.v1.verify.checks import verify_bundle, write_verify_outputs


def init(
    path: Path = typer.Argument(Path("."), exists=True, help="Project directory to capture."),
    command: Optional[str] = typer.Option(
        None, "--command", help="The experiment command this lock is for (declared, not inferred)."
    ),
    seed: Optional[int] = typer.Option(
        None, "--seed", help="Seed declared for the run; left UNKNOWN when not given."
    ),
    config: Optional[list[Path]] = typer.Option(
        None, "--config", help="Config file(s) to fingerprint (repeatable)."
    ),
    dataset: Optional[list[Path]] = typer.Option(
        None, "--dataset", help="Dataset file/directory to fingerprint (repeatable)."
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Directory where the run will write artifacts."
    ),
    out: Path = typer.Option(
        Path(LOCK_FILENAME), "-o", help="Lock file to write, relative to the project directory."
    ),
) -> None:
    """Capture code/environment/declared facts into experiment.lock.json."""
    lock = build_lock(
        DeclaredInputs(
            root=path,
            command=command,
            seed=seed,
            config_files=list(config or []),
            dataset_paths=list(dataset or []),
            output_directory=output_dir,
        )
    )
    target = out if out.is_absolute() else path / out
    written = write_lock(lock, target)
    grades = ", ".join(f"{name}={field.status.value}" for name, field in sorted(lock.fields()))
    typer.echo(f"lock written: {written}")
    typer.echo(f"lock_hash: {lock.compute_hash()}")
    typer.echo(grades)


def run(
    args: list[str] = typer.Argument(
        default_factory=list,
        help="Experiment command after '--', e.g. `run -- python train.py`.",
    ),
    path: str = typer.Option(".", "--path", help="Project directory holding experiment.lock.json."),
    lock: str = typer.Option(LOCK_FILENAME, "--lock", help="Lock file name, relative to --path."),
    run_out: str = typer.Option(RUN_FILENAME, "--run-out", help="Run record file name."),
    timeout: Optional[float] = typer.Option(
        None, "--timeout", help="Kill the experiment after this many seconds."
    ),
) -> None:
    """Run an experiment command and capture the evidence chain around it."""
    command = list(args)
    if command and command[0] == "--":  # standalone click keeps the separator
        command = command[1:]
    if not command:
        raise typer.BadParameter("usage: experiment-doctor run -- COMMAND [ARGS...]")
    root = Path(path)
    if not root.is_dir():
        raise typer.BadParameter(f"--path is not a directory: {root}")
    _, lock_path = load_and_verify_lock(lock, root)
    if not lock_path.is_file():
        raise typer.BadParameter(f"no {LOCK_FILENAME} found under {root}; run `init` first")
    outcome = run_experiment(root, command, lock_arg=lock, run_filename=run_out, timeout=timeout)
    record = outcome.record
    typer.echo(f"run record written: {outcome.run_path}")
    typer.echo(f"evidence bundle: {outcome.evidence_dir}")
    typer.echo(f"run_hash: {record.run_hash}")
    lock_hash = record.lock_reference.lock_hash.value
    typer.echo(f"lock_reference: {lock_hash if lock_hash else 'UNVERIFIED'}")
    typer.echo(f"termination: {record.termination_status.value}")
    grades = ", ".join(f"{name}={field.status.value}" for name, field in sorted(record.fields()))
    typer.echo(grades)
    raise typer.Exit(code=outcome.exit_code)


def verify(
    path: Path = typer.Argument(
        ".", exists=True, help="Evidence bundle dir, or the project that contains one."
    ),
) -> None:
    """Verify an evidence bundle deterministically (V001-V006); writes verify.json/md."""
    try:
        report, bundle = verify_bundle(path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    json_path, md_path = write_verify_outputs(report, bundle)
    for check in report.checks:
        typer.echo(f"{check.check_id}  {check.status.value}  {check.message}")
    typer.echo(f"verify outputs written: {json_path} , {md_path}")
    raise typer.Exit(code=report.exit_code)
