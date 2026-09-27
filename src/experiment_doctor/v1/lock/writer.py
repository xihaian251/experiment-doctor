"""Lock construction and writing.

``build_lock`` composes capture results (git, environment, invocation) with the
user's explicit declarations.  A value enters the lock through exactly one of
two doors -- direct observation or explicit declaration -- never through
inference (the GMMVI seed case: a plausible derivation is still not evidence).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.v1.capture import environment, git, runtime
from experiment_doctor.v1.lock.schema import (
    ArtifactsBlock,
    CodeBlock,
    ConfigurationBlock,
    DatasetBlock,
    EnvironmentBlock,
    ExecutionBlock,
    ExperimentLock,
    IdentityBlock,
    RandomnessBlock,
)

LOCK_FILENAME = "experiment.lock.json"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def hash_tree(root: Path) -> str:
    """Order-independent fingerprint of a directory: sha256 over sorted
    (relative path, file hash) pairs."""
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            entries.append(f"{path.relative_to(root).as_posix()} {hash_file(path)}")
    digest = hashlib.sha256("\n".join(entries).encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def _rel_key(path: Path, base: Path, suffix: str = "") -> str:
    try:
        return path.relative_to(base).as_posix() + suffix
    except ValueError:  # declared outside the project root: keep the raw path
        return path.as_posix() + suffix


def _fingerprint_paths(
    paths: list[Path], base: Path, label: str
) -> ProvenanceField[dict[str, str]]:
    fingerprints: dict[str, str] = {}
    missing: list[str] = []
    for raw in paths:
        path = base / raw if not raw.is_absolute() else raw
        if path.is_file():
            fingerprints[_rel_key(path, base)] = hash_file(path)
        elif path.is_dir():
            fingerprints[_rel_key(path, base, "/")] = hash_tree(path)
        else:
            missing.append(str(raw))
    if not fingerprints:
        note = "declared paths unreadable" if missing else "no paths declared"
        return ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN, confidence_note=note)
    source = SourceRef(note=f"sha256 of declared {label} at capture time")
    field: ProvenanceField[dict[str, str]] = ProvenanceField.of(
        dict(sorted(fingerprints.items())), ProvenanceStatus.CONFIRMED, source
    )
    if missing:
        field.confidence_note = "declared but not found at capture time: " + ", ".join(missing)
    return field


class DeclaredInputs(BaseModel):
    """What the user declared on the command line; None means not declared."""

    root: Path
    command: str | None = None
    seed: int | None = None
    config_files: list[Path] = Field(default_factory=list)
    dataset_paths: list[Path] = Field(default_factory=list)
    output_directory: Path | None = None


def build_lock(declared: DeclaredInputs) -> ExperimentLock:
    root = declared.root.resolve()

    root_field = git.repository_root(root)
    if root_field.value is not None:
        repo_root = Path(str(root_field.value))
        code = CodeBlock(
            repository=git.repository_url(repo_root),
            commit=git.current_commit(repo_root),
            dirty=git.is_dirty(repo_root),
            diff_hash=git.diff_hash(repo_root),
        )
    else:
        code = CodeBlock()  # every field UNKNOWN with an explanatory note

    if declared.dataset_paths:
        dataset = DatasetBlock(
            paths=ProvenanceField.of(
                sorted(p.as_posix() for p in declared.dataset_paths),
                ProvenanceStatus.CONFIRMED,
                SourceRef(note="declared via --dataset"),
            ),
            fingerprints=_fingerprint_paths(declared.dataset_paths, root, "dataset paths"),
        )
    else:
        dataset = DatasetBlock()

    if declared.config_files:
        configuration = ConfigurationBlock(
            config_files=ProvenanceField.of(
                sorted(p.as_posix() for p in declared.config_files),
                ProvenanceStatus.CONFIRMED,
                SourceRef(note="declared via --config"),
            ),
            config_hash=_fingerprint_paths(declared.config_files, root, "config files"),
        )
    else:
        configuration = ConfigurationBlock()

    if declared.seed is not None:
        randomness = RandomnessBlock(
            seed=ProvenanceField.of(
                declared.seed, ProvenanceStatus.CONFIRMED, SourceRef(note="declared via --seed")
            ),
            seed_source=ProvenanceField.of(
                "cli --seed", ProvenanceStatus.CONFIRMED, SourceRef(note="declaration channel")
            ),
        )
    else:
        randomness = RandomnessBlock()

    if declared.output_directory is not None:
        artifacts = ArtifactsBlock(
            output_directory=ProvenanceField.of(
                str(declared.output_directory),
                ProvenanceStatus.CONFIRMED,
                SourceRef(note="declared via --output-dir"),
            )
        )
    else:
        artifacts = ArtifactsBlock()

    return ExperimentLock(
        identity=IdentityBlock(created_at=runtime.timestamp_field()),
        code=code,
        dataset=dataset,
        configuration=configuration,
        randomness=randomness,
        environment=EnvironmentBlock(
            python_version=environment.python_version(),
            packages=environment.installed_packages(),
            platform=environment.platform_info(),
        ),
        execution=ExecutionBlock(
            command=runtime.declared_command(declared.command),
            cwd=runtime.working_directory(root),
            # start_time stays UNKNOWN until Phase 2's run wrapper observes it
        ),
        artifacts=artifacts,
    )


def write_lock(lock: ExperimentLock, path: Path) -> Path:
    sealed = lock.seal()
    assert sealed.lock_hash == sealed.compute_hash()
    payload = json.dumps(sealed.model_dump(mode="json"), indent=2, ensure_ascii=False)
    path.write_text(payload + "\n", encoding="utf-8")
    return path
