"""Generic scanner plus the adapter protocol.

Layering (v0.1): the generic scanner knows how to walk a directory, classify
artifacts and count run candidates.  An adapter knows what a *specific* project
means.  Project-specific semantics never live in the schema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus
from experiment_doctor.schema import (
    AggregationRecord,
    ArtifactRef,
    ArtifactType,
    ExperimentFamily,
    ExperimentProject,
    ExperimentRun,
)

NOISE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    ".idea",
    ".vscode",
}

#: Cap so that scanning a large directory tree cannot run away.
MAX_ARTIFACTS = 200_000

ENVIRONMENT_NAMES = {
    "requirements.txt",
    "requirements.lock",
    "environment.yml",
    "environment.yaml",
    "poetry.lock",
    "uv.lock",
    "pipfile",
    "pipfile.lock",
    "dockerfile",
    "spack.yaml",
}
SCRIPT_SUFFIXES = {".py", ".sh", ".bash", ".zsh", ".r", ".jl", ".m"}
METRIC_SUFFIXES = {".csv", ".tsv", ".jsonl", ".ndjson", ".arrow", ".parquet"}
CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".conf", ".env"}
CHECKPOINT_SUFFIXES = {
    ".pt",
    ".pth",
    ".ckpt",
    ".safetensors",
    ".bin",
    ".pkl",
    ".pickle",
    ".npz",
    ".npy",
    ".h5",
    ".hdf5",
    ".onnx",
    ".joblib",
}
LOG_SUFFIXES = {".log", ".out", ".err", ".txt", ".stderr", ".stdout"}
TABLE_SUFFIXES = {".tex", ".tab", ".md", ".html", ".rst"}


def classify(path: Path) -> ArtifactType:
    """Best-effort artifact type from name only.  Never claims more than a name gives."""
    name = path.name.lower()
    if name in ENVIRONMENT_NAMES or name.endswith((".sbatch", ".slurm")) or "slurm" in name:
        return ArtifactType.ENVIRONMENT
    if path.suffix.lower() in CHECKPOINT_SUFFIXES:
        return ArtifactType.CHECKPOINT
    if name.endswith((".csv.bad", ".csv.failed", ".csv.excluded")):
        return ArtifactType.METRIC
    if path.suffix.lower() in METRIC_SUFFIXES:
        return ArtifactType.METRIC
    if path.suffix.lower() in SCRIPT_SUFFIXES:
        return ArtifactType.SCRIPT
    if path.suffix.lower() in LOG_SUFFIXES:
        return ArtifactType.LOG
    if path.suffix.lower() in CONFIG_SUFFIXES:
        return ArtifactType.CONFIG
    if path.suffix.lower() in TABLE_SUFFIXES:
        return ArtifactType.TABLE
    return ArtifactType.UNKNOWN


def relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def make_artifact_ref(root: Path, path: Path, hash_small_files: bool = False) -> ArtifactRef:
    """Metadata only.  Hashing is opt-in and capped: big artifacts must not be read."""
    stat = path.stat()
    digest: str | None = None
    if hash_small_files and stat.st_size <= 65_536 and classify(path) is ArtifactType.CONFIG:
        import hashlib

        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return ArtifactRef(
        path=relative(root, path),
        artifact_type=classify(path),
        size=stat.st_size,
        mtime=round(stat.st_mtime, 3),
        sha256=digest,
    )


def iter_files(root: Path, limit: int = MAX_ARTIFACTS) -> Iterable[Path]:
    """Walk ``root`` skipping VCS/build noise, in deterministic order, capped at ``limit``."""
    remaining = limit
    stack = [root]
    while stack and remaining > 0:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except (OSError, PermissionError):
            continue
        dirs: list[Path] = []
        for entry in entries:
            if entry.is_dir():
                if entry.name not in NOISE_DIRS:
                    dirs.append(entry)
                continue
            if not entry.is_file():
                continue
            remaining -= 1
            yield entry
        stack.extend(reversed(dirs))


class ExperimentAdapter(ABC):
    """Minimal adapter protocol: detect, then discover the three object levels."""

    name: str = "abstract"

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def describe(self) -> str:
        return self.name

    def detect(self, root: Path) -> float:
        """Return 0..1.  Higher wins; 0 means this adapter does not apply."""
        return 0.0

    @abstractmethod
    def discover_families(self, root: Path) -> list[ExperimentFamily]: ...

    @abstractmethod
    def discover_runs(self, root: Path) -> list[ExperimentRun]: ...

    def discover_aggregations(self, root: Path) -> list[AggregationRecord]:
        return []

    def project_id(self, root: Path) -> str:
        return Path(root).resolve().name

    def code_repository(self) -> ArtifactRef | None:
        return None


@dataclass
class AdapterSpec:
    """Registry entry: how to build an adapter for a root, plus what it does."""

    name: str
    description: str
    factory: Callable[[Path], ExperimentAdapter]
    options: tuple[str, ...] = field(default_factory=tuple)


_REGISTRY: list[AdapterSpec] = []


def register(spec: AdapterSpec) -> None:
    _REGISTRY.append(spec)


def registry() -> list[AdapterSpec]:
    return list(_REGISTRY)


def select_adapter(root: Path, *, prefer: str | None = None) -> tuple[ExperimentAdapter, float]:
    """Pick the highest-scoring registered adapter, falling back to the generic one."""
    _ensure_adapters_installed()
    candidates: list[tuple[float, AdapterSpec]] = []
    for spec in _REGISTRY:
        adapter = spec.factory(root)
        score = adapter.detect(root)
        if prefer is not None:
            if adapter.name == prefer and score > 0:
                return adapter, score
            continue
        if score > 0:
            candidates.append((score, spec))
    if candidates and prefer is None:
        candidates.sort(key=lambda item: item[0], reverse=True)
        score, spec = candidates[0]
        return spec.factory(root), score
    if prefer is not None:
        raise SystemExit(f"adapter '{prefer}' does not apply to {root}")
    generic = _GENERIC_SPEC
    if generic is None:
        raise RuntimeError("no adapters registered")
    return generic.factory(root), 0.0


_GENERIC_SPEC: AdapterSpec | None = None


def _ensure_adapters_installed() -> None:
    """Lazily import the adapter package so the registry is never empty.

    Imported here rather than at module scope because ``experiment_doctor.adapters``
    depends on this module.
    """
    if _GENERIC_SPEC is not None and _REGISTRY:
        return
    from experiment_doctor.adapters import install_adapters

    install_adapters()


def register_generic(spec: AdapterSpec) -> None:
    """The generic fallback is not scored; it is always available."""
    global _GENERIC_SPEC
    _GENERIC_SPEC = spec
    register(spec)


#: Higher is weaker.  Used to keep a project-level claim from outranking its own evidence.
_GRADE_RANK = {
    ProvenanceStatus.CONFIRMED: 0,
    ProvenanceStatus.SUPPORTED: 1,
    ProvenanceStatus.INFERRED: 2,
    ProvenanceStatus.UNKNOWN: 3,
    ProvenanceStatus.CONFLICTING: 4,
}


def _project_repository(runs: Sequence[ExperimentRun]) -> ProvenanceField[str]:
    """Project-level repository claim: never stronger than the weakest run that names one."""
    evidenced = [run.code_repository for run in runs if run.code_repository.has_value]
    if not evidenced:
        return ProvenanceField.unknown(note="no run artifact names a code repository")
    values = {claim.value for claim in evidenced if claim.value is not None}
    if len(values) > 1:
        return ProvenanceField.conflicting(
            [claim.source for claim in evidenced if claim.source is not None],
            note=f"runs name {len(values)} different repositories",
        )
    weakest = max(evidenced, key=lambda claim: _GRADE_RANK[claim.status])
    return ProvenanceField.of(
        next(iter(values)),
        weakest.status,
        weakest.source,
        note=f"named by {len(evidenced)} of {len(runs)} runs",
    )


def scan_project(
    root: Path | str,
    *,
    adapter: ExperimentAdapter | None = None,
    prefer: str | None = None,
    include_inventory: bool = True,
) -> ExperimentProject:
    """Run discovery for one project directory.  Read-only."""
    root = Path(root)
    if not root.exists():
        raise SystemExit(f"path does not exist: {root}")
    if adapter is None:
        adapter, _score = select_adapter(root, prefer=prefer)

    families = adapter.discover_families(root)
    runs = adapter.discover_runs(root)
    aggregations = adapter.discover_aggregations(root)
    inventory: Sequence[ArtifactRef] = ()
    if include_inventory:
        inventory = [make_artifact_ref(root, path) for path in iter_files(root) if path.is_file()]

    project = ExperimentProject(
        root=str(root.resolve()),
        project_id=adapter.project_id(root),
        adapter=adapter.name,
        code_repository=_project_repository(runs),
        families=families,
        runs=runs,
        aggregations=aggregations,
        artifacts=list(inventory),
        notes=list(getattr(adapter, "notes", []) or []),
    )
    repo = adapter.code_repository()
    if repo is not None:
        project.artifacts.append(repo)
    return project


def provenance_coverage_summary(runs: list[ExperimentRun]) -> dict[str, int]:
    """Cheap counts used by ``scan``; the audit produces the full field-level coverage."""
    return {
        "runs": len(runs),
        "runs_with_metrics": sum(1 for run in runs if run.metrics),
        "runs_with_config": sum(1 for run in runs if run.resolved_config.has_value),
        "runs_with_seed_value": sum(1 for run in runs if run.seed.has_value),
        "runs_included_in_aggregation": sum(
            1 for run in runs if run.included_in_aggregation.value is True
        ),
        "runs_excluded_from_aggregation": sum(
            1 for run in runs if run.included_in_aggregation.value is False
        ),
    }
