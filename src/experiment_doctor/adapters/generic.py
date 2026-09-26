"""Generic fallback adapter.

Understands directory structure and file kinds, nothing else.  It deliberately
produces no metric semantics: an unlabelled CSV column is not a metric of record.
Its job is to still yield an artifact inventory plus explicit provenance gaps.
"""

from __future__ import annotations

from pathlib import Path

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.scanner import (
    MAX_ARTIFACTS,
    AdapterSpec,
    ExperimentAdapter,
    classify,
    iter_files,
    make_artifact_ref,
    register,
    register_generic,
    relative,
)
from experiment_doctor.schema import (
    ArtifactType,
    ExperimentFamily,
    ExperimentRun,
    FamilyKind,
    RunStatus,
)


def _config_candidates(files: list[Path]) -> list[Path]:
    return [p for p in files if classify(p) is ArtifactType.CONFIG]


def _metric_files(files: list[Path]) -> list[Path]:
    return [p for p in files if classify(p) is ArtifactType.METRIC]


def _strip_run_suffix(stem: str) -> str:
    for token in ("_config", ".config", "_metrics", "_results", "_history", "_log"):
        if stem.endswith(token):
            return stem[: -len(token)]
    return stem


class GenericProjectAdapter(ExperimentAdapter):
    """Structure-level adapter used when no project-specific adapter applies."""

    name = "generic"

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._files: list[Path] | None = None

    def describe(self) -> str:
        return (
            "generic: directory walk + artifact inventory; emits run candidates from "
            "metric-shaped files and explicit provenance gaps, no metric semantics"
        )

    @property
    def files(self) -> list[Path]:
        if self._files is None:
            self._files = [
                p for p in iter_files(self.root, limit=min(MAX_ARTIFACTS, 50_000)) if p.is_file()
            ]
        return self._files

    def _by_dir(self) -> dict[Path, list[Path]]:
        grouped: dict[Path, list[Path]] = {}
        for path in self.files:
            grouped.setdefault(path.parent, []).append(path)
        return grouped

    def discover_families(self, root: Path) -> list[ExperimentFamily]:
        families: list[ExperimentFamily] = []
        for directory, files in sorted(
            self._by_dir().items(), key=lambda kv: relative(self.root, kv[0])
        ):
            metrics = _metric_files(files)
            if not metrics:
                continue
            family_id = relative(self.root, directory)
            families.append(
                ExperimentFamily(
                    family_id=family_id,
                    name=Path(directory).name,
                    kind=FamilyKind.UNKNOWN,
                    result_dir=family_id,
                    declared_repetitions=ProvenanceField.unknown(
                        note="no repetition count is declared in any artifact"
                    ),
                    membership_rule=ProvenanceField.unknown(
                        note="generic scanner cannot know which runs were aggregated"
                    ),
                    run_ids=[self._run_id(family_id, path) for path in sorted(metrics)],
                )
            )
        return families

    def _run_id(self, family_id: str, path: Path) -> str:
        return f"{family_id}#{path.stem}"

    def discover_runs(self, root: Path) -> list[ExperimentRun]:
        runs: list[ExperimentRun] = []
        for directory, files in sorted(
            self._by_dir().items(), key=lambda kv: relative(self.root, kv[0])
        ):
            metrics = _metric_files(files)
            if not metrics:
                continue
            family_id = relative(self.root, directory)
            configs = _config_candidates(files)
            for path in sorted(metrics):
                co_located = [
                    cfg
                    for cfg in configs
                    if _strip_run_suffix(cfg.stem) == _strip_run_suffix(path.stem)
                ]
                run = ExperimentRun(
                    run_id=self._run_id(family_id, path),
                    family_id=family_id,
                    result_slot_index=None,
                    status=RunStatus.UNKNOWN,
                    artifacts=[make_artifact_ref(self.root, path)],
                )
                if co_located:
                    run.config_source = ProvenanceField.of(
                        relative(self.root, co_located[0]),
                        ProvenanceStatus.INFERRED,
                        SourceRef(path=relative(self.root, path), note="co-located file stem"),
                        note="matched by file stem only; nothing in the artifacts proves the binding",
                    )
                runs.append(run)
        return runs

    def code_repository(self) -> None:
        return None


def spec() -> AdapterSpec:
    return AdapterSpec(
        name="generic",
        description=GenericProjectAdapter(Path(".")).describe(),
        factory=GenericProjectAdapter,
    )


def install() -> None:
    """Register the generic adapter as the always-available fallback."""
    register_generic(spec())


__all__ = [
    "GenericProjectAdapter",
    "install",
    "register",
    "relative",
    "spec",
]
