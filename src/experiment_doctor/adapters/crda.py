"""CRDA (mhmohebbi/CRDA tabular-regression augmentation) semantic adapter.

Understands only the main-experiment artifact layout::

    experiments/<dataset>/<baseline>_<YYYYmmdd-HHMMSS>/
        config.json                     resolved runtime config (written at init)
        interim_results/<tag>_interim_results.csv   one row per (subset, seed)
        results.csv                     per-subset x per-metric mean/std aggregate
        params/<tag>_params_seed_<s>.json           per-seed tuned parameters

A timestamped directory is a family container, not a run: each seed row of an
interim file is one ``ExperimentRun``; each (subset, metric) of ``results.csv``
is one ``AggregationRecord``.  All numbers are parsed from the artifacts.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from experiment_doctor.adapters.aggregation_claims import find_line, read_lines
from experiment_doctor.provenance import (
    ProvenanceField,
    ProvenanceStatus,
    SourceRef,
)
from experiment_doctor.scanner import (
    AdapterSpec,
    ExperimentAdapter,
    make_artifact_ref,
    register,
    relative,
)
from experiment_doctor.schema import (
    AggregationRecord,
    ArtifactRef,
    ArtifactRole,
    ExperimentFamily,
    ExperimentRun,
    FamilyKind,
    MetricDirection,
    MetricRecord,
    SelectionPolicy,
    SpreadBasis,
    SpreadSemantics,
)

RUN_DIR_RE = re.compile(r"^(?P<baseline>mlp|xgboost)_(?P<stamp>\d{8}-\d{6})$")
INTERIM_SUFFIX = "_interim_results.csv"
#: quantities the project publishes as model performance, aggregated in results.csv
PERFORMANCE_METRICS = ("mse", "aug_mse", "delta_mse")
#: statistical gate columns: parsed as run metrics, never modelled as aggregations
DIAGNOSTIC_METRICS = ("p_wilcoxon",)

SRC_EXPERIMENT = "src/experiment.py"
SRC_COLLECTOR = "scripts/collect_main_experiment_results.py"

#: text needles; the adapter cites lines, it never cites numbers
NEEDLE_STD_ERR = "np.nanstd(values, ddof=1) / np.sqrt(len(values))"
NEEDLE_MEMBERSHIP = "values = [r[metric] for r in seed_results]"
NEEDLE_SEEDS = "np.random.randint(0, 1000000"
NEEDLE_MSE_EVAL = "mse = baseline.evaluate(X_test, y_test"
NEEDLE_AUG_ENSEMBLE = "ensemble_pred = preds.mean(axis=1)"
NEEDLE_DELTA = "delta_mse = 100.0 * (aug_mse - mse) / mse"
NEEDLE_MINIMISE = "# Optuna minimises"
NEEDLE_LOWER_BETTER = "lower is better"
NEEDLE_RAW_STD_HISTORY = "raw std in early runs"
NEEDLE_SEM_PROSE = "standard error"


def _row_line(tag_seen: int) -> int:
    """Physical line of the n-th data row under a one-line CSV header."""
    return tag_seen + 2


class _SeedRow:
    __slots__ = ("seed", "values", "line", "should_proceed")

    def __init__(self, seed: int, values: dict[str, float], line: int, proceeded: bool) -> None:
        self.seed = seed
        self.values = values
        self.line = line
        self.should_proceed = proceeded


class _Subset:
    """One (dataset tag, baseline) cell of the experiment: 1 family, N seed runs."""

    def __init__(self, tag: str, rows: list[_SeedRow], reported: dict[str, tuple[float, float]]):
        self.tag = tag
        self.rows = rows
        self.reported = reported


class _RunDirectory:
    def __init__(
        self,
        path: Path,
        baseline: str,
        config: dict[str, Any],
        subsets: list[_Subset],
    ) -> None:
        self.path = path
        self.baseline = baseline
        self.config = config
        self.subsets = subsets


class CRDAAdapter(ExperimentAdapter):
    """Semantic adapter for CRDA main MLP/XGBoost experiment artifacts."""

    name = "crda"

    def __init__(self, root: Path | str) -> None:
        super().__init__(Path(root))
        self._parsed: list[_RunDirectory] | None = None
        self._notes: list[str] = []

    def describe(self) -> str:
        return (
            "CRDA: reads experiments/<dataset>/<baseline>_<timestamp>/ interim_results CSVs as "
            "seed-level runs, config.json as the resolved runtime config, and results.csv as "
            "per-subset mean+/-spread aggregates"
        )

    # ------------------------------------------------------------------ detect
    def detect(self, root: Path) -> float:
        dirs = self._parse(root)
        if not dirs:
            return 0.0
        score = 0.55
        # header check reads the small interim files from disk
        headers_ok = False
        for directory in dirs:
            for csv_path in sorted((directory.path / "interim_results").glob(f"*{INTERIM_SUFFIX}")):
                with csv_path.open(encoding="utf-8") as fh:
                    header = next(csv.reader(fh), [])
                if {"seed", "delta_mse", "p_wilcoxon", "should_proceed"} <= set(header):
                    headers_ok = True
                    break
            if headers_ok:
                break
        if headers_ok:
            score += 0.15
        if any(
            {"num_seeds", "sample_sizes", "ignore_filter"} <= set(directory.config)
            for directory in dirs
        ):
            score += 0.15
        return score

    # ------------------------------------------------------------------ parse
    def _experiments_root(self, root: Path) -> Path:
        candidate = root / "experiments"
        return candidate if candidate.is_dir() else root

    def _parse(self, root: Path) -> list[_RunDirectory]:
        if self._parsed is not None:
            return self._parsed
        directories: list[_RunDirectory] = []
        exp_root = self._experiments_root(Path(root))
        if not exp_root.is_dir():
            self._parsed = []
            return self._parsed
        for dataset_dir in sorted(exp_root.iterdir()):
            if not dataset_dir.is_dir():
                continue
            for run_dir in sorted(dataset_dir.iterdir()):
                match = RUN_DIR_RE.match(run_dir.name)
                if not (run_dir.is_dir() and match):
                    continue
                parsed = self._parse_run_dir(run_dir, match.group("baseline"))
                if parsed is not None:
                    directories.append(parsed)
        self._parsed = directories
        return directories

    def _parse_run_dir(self, run_dir: Path, baseline: str) -> _RunDirectory | None:
        config_path = run_dir / "config.json"
        interim_dir = run_dir / "interim_results"
        if not config_path.is_file() or not interim_dir.is_dir():
            return None
        config = json.loads(config_path.read_text(encoding="utf-8"))
        reported = self._parse_reported(run_dir / "results.csv")
        subsets: list[_Subset] = []
        for csv_path in sorted(interim_dir.glob(f"*{INTERIM_SUFFIX}")):
            tag = csv_path.name[: -len(INTERIM_SUFFIX)]
            rows = self._parse_interim(csv_path)
            if not rows:
                continue
            subsets.append(_Subset(tag, rows, reported.get(tag, {})))
        if not subsets:
            return None
        return _RunDirectory(run_dir, baseline, config, subsets)

    @staticmethod
    def _parse_interim(csv_path: Path) -> list[_SeedRow]:
        rows: list[_SeedRow] = []
        with csv_path.open(newline="", encoding="utf-8") as fh:
            for index, row in enumerate(csv.DictReader(fh)):
                try:
                    seed = int(row["seed"])
                except (KeyError, ValueError):
                    continue
                values: dict[str, float] = {}
                for metric in (*PERFORMANCE_METRICS, *DIAGNOSTIC_METRICS):
                    raw = row.get(metric)
                    if raw not in (None, ""):
                        try:
                            values[metric] = float(raw)
                        except ValueError:
                            continue
                rows.append(
                    _SeedRow(
                        seed,
                        values,
                        _row_line(index),
                        str(row.get("should_proceed", "")).strip().lower() == "true",
                    )
                )
        return rows

    @staticmethod
    def _parse_reported(path: Path) -> dict[str, dict[str, tuple[float, float]]]:
        out: dict[str, dict[str, tuple[float, float]]] = {}
        if not path.is_file():
            return out
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    out.setdefault(str(row["dataset"]), {})[str(row["metric"])] = (
                        float(row["mean"]),
                        float(row["std"]),
                    )
                except (KeyError, ValueError):
                    continue
        return out

    # ----------------------------------------------------------------- sources
    def _line_of(self, rel: str, needle: str) -> tuple[int | None, str | None]:
        hit = find_line(read_lines(self.root / rel), needle)
        return hit if hit is not None else (None, None)

    def _src(
        self, rel: str, line: int | None = None, key: str | None = None, note: str | None = None
    ) -> SourceRef:
        return SourceRef(path=rel, line=line, key=key, note=note)

    def _note(self, text: str) -> None:
        if text not in self._notes:
            self._notes.append(text)

    # --------------------------------------------------------------- families
    def discover_families(self, root: Path) -> list[ExperimentFamily]:
        return self._families_and_runs(root)[0]

    def discover_runs(self, root: Path) -> list[ExperimentRun]:
        return self._families_and_runs(root)[1]

    def _families_and_runs(self, root: Path) -> tuple[list[ExperimentFamily], list[ExperimentRun]]:
        families: list[ExperimentFamily] = []
        runs: list[ExperimentRun] = []
        membership_claim = self._membership_rule()
        for directory in self._parse(root):
            for subset in directory.subsets:
                family_id = f"{subset.tag}/{directory.baseline}"
                run_ids = [f"{family_id}/seed-{row.seed}" for row in subset.rows]
                families.append(
                    ExperimentFamily(
                        family_id=family_id,
                        name=family_id,
                        kind=FamilyKind.EVALUATION,
                        result_dir=relative(self.root, directory.path),
                        method=ProvenanceField.of(
                            directory.baseline,
                            ProvenanceStatus.CONFIRMED,
                            self._src(
                                relative(self.root, directory.path / "config.json"),
                                key="baseline",
                            ),
                        ),
                        task=ProvenanceField.unknown(
                            note="the artifacts name a dataset and a subset size, not a task label"
                        ),
                        run_ids=run_ids,
                        declared_repetitions=self._declared_repetitions(directory),
                        membership_rule=membership_claim,
                        primary_metric="aug_mse",
                        secondary_metrics=["mse", "delta_mse"],
                    )
                )
                for row in subset.rows:
                    runs.append(self._build_run(directory, subset, row, family_id))
        return families, runs

    def _declared_repetitions(self, directory: _RunDirectory) -> ProvenanceField[int]:
        value = directory.config.get("num_seeds")
        if not isinstance(value, int):
            return ProvenanceField.unknown(note="config.json records no num_seeds")
        return ProvenanceField.of(
            value,
            ProvenanceStatus.SUPPORTED,
            self._src(relative(self.root, directory.path / "config.json"), key="num_seeds"),
            note=(
                "a declaration inside the run's own resolved config; distinct from "
                "observed seed rows, which this tool counts separately"
            ),
        )

    def _membership_rule(self) -> ProvenanceField[str]:
        line, text = self._line_of(SRC_EXPERIMENT, NEEDLE_MEMBERSHIP)
        return ProvenanceField.of(
            (
                "all seed rows written to interim_results for the subset are aggregated; "
                "with ignore_filter=true the Wilcoxon gate only records should_proceed=false, "
                "it never removes a seed from the aggregate"
            ),
            ProvenanceStatus.CONFIRMED,
            self._src(SRC_EXPERIMENT, line=line, key=text),
        )

    # ------------------------------------------------------------------- runs
    def _build_run(
        self,
        directory: _RunDirectory,
        subset: _Subset,
        row: _SeedRow,
        family_id: str,
    ) -> ExperimentRun:
        rel_dir = relative(self.root, directory.path)
        interim_rel = f"{rel_dir}/interim_results/{subset.tag}{INTERIM_SUFFIX}"
        config_rel = f"{rel_dir}/config.json"
        row_key = f"row seed={row.seed}"
        config = dict(directory.config)
        return ExperimentRun(
            run_id=f"{family_id}/seed-{row.seed}",
            family_id=family_id,
            seed=ProvenanceField.of(
                row.seed,
                ProvenanceStatus.CONFIRMED,
                self._src(interim_rel, line=row.line, key=f"{row_key} column=seed"),
                note="recorded per seed by the harness; params/<tag>_params_seed_<seed>.json "
                "filename identities agree",
            ),
            seed_derivation=self._seed_derivation(directory),
            method=ProvenanceField.of(
                directory.baseline,
                ProvenanceStatus.CONFIRMED,
                self._src(config_rel, key="baseline"),
            ),
            dataset=ProvenanceField.of(
                subset.tag,
                ProvenanceStatus.CONFIRMED,
                self._src(interim_rel, line=1, key="column=dataset"),
                note="dataset name plus the subset size this row belongs to",
            ),
            resolved_config=ProvenanceField.of(
                config,
                ProvenanceStatus.CONFIRMED,
                self._src(config_rel),
                note="written from the live Config instance at Experiment init "
                f"({SRC_EXPERIMENT}); per-seed tuned parameters live in the separate "
                "params/ file and are deliberately not merged into it",
            ),
            config_source=ProvenanceField.of(
                config_rel, ProvenanceStatus.CONFIRMED, self._src(config_rel)
            ),
            metrics=self._metrics(row, interim_rel),
            artifacts=self._artifacts(directory, subset, row, rel_dir),
            included_in_aggregation=ProvenanceField.of(
                True,
                ProvenanceStatus.CONFIRMED,
                self._src(
                    interim_rel,
                    line=row.line,
                    key=row_key,
                    note="the results.csv aggregate consumes exactly the rows of this file",
                ),
            ),
        )

    def _seed_derivation(self, directory: _RunDirectory) -> ProvenanceField[str]:
        line, text = self._line_of(SRC_EXPERIMENT, NEEDLE_SEEDS)
        if line is None:
            return ProvenanceField.unknown()
        return ProvenanceField.of(
            f"np.random.randint(0, 1000000, num_seeds) after seeding(random_seed); {text}",
            ProvenanceStatus.SUPPORTED,
            self._src(SRC_EXPERIMENT, line=line, key=text),
            note="the generator seed is recorded in config.json; the drawn trial seeds are "
            "the values actually read from the interim rows",
        )

    def _metrics(self, row: _SeedRow, interim_rel: str) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        for metric in (*PERFORMANCE_METRICS, *DIAGNOSTIC_METRICS):
            if metric not in row.values:
                continue
            records.append(
                MetricRecord(
                    name=metric,
                    value=ProvenanceField.of(
                        row.values[metric],
                        ProvenanceStatus.CONFIRMED,
                        self._src(interim_rel, line=row.line, key=f"column={metric}"),
                    ),
                    direction=self._direction(metric),
                    status=ProvenanceStatus.CONFIRMED,
                    source=self._src(interim_rel, line=row.line, key=f"column={metric}"),
                )
            )
        return records

    def _direction(self, metric: str) -> ProvenanceField[MetricDirection]:
        if metric == "delta_mse":
            line, text = self._line_of("README.md", NEEDLE_LOWER_BETTER)
            return ProvenanceField.of(
                MetricDirection.MINIMIZE,
                ProvenanceStatus.CONFIRMED,
                self._src("README.md", line=line, key=text),
                note="percent change of MSE; the project states 'lower is better' and "
                "'negative = improvement'",
            )
        if metric in ("mse", "aug_mse"):
            line, text = self._line_of(SRC_EXPERIMENT, NEEDLE_MINIMISE)
            return ProvenanceField.of(
                MetricDirection.MINIMIZE,
                ProvenanceStatus.CONFIRMED,
                self._src(SRC_EXPERIMENT, line=line, key=text),
                note="the project's own tuning loop treats validation MSE as the quantity to "
                "minimise",
            )
        return ProvenanceField.unknown(
            note="p_wilcoxon is a statistical gate diagnostic, not a performance metric; "
            "no direction is claimed"
        )

    def _artifacts(
        self,
        directory: _RunDirectory,
        subset: _Subset,
        row: _SeedRow,
        rel_dir: str,
    ) -> list[ArtifactRef]:
        paths = [
            (directory.path / "config.json", ArtifactRole.CONFIG),
            (
                directory.path / "interim_results" / f"{subset.tag}{INTERIM_SUFFIX}",
                ArtifactRole.RESULT,
            ),
            (directory.path / "params" / f"{subset.tag}_params_seed_{row.seed}.json", None),
            (directory.path / "results.csv", None),
        ]
        refs = []
        for path, role in paths:
            if not path.is_file():
                continue
            ref = make_artifact_ref(self.root, path)
            if role is not None:
                ref.artifact_role = role
            refs.append(ref)
        return refs

    # ---------------------------------------------------------- aggregations
    def discover_aggregations(self, root: Path) -> list[AggregationRecord]:
        records: list[AggregationRecord] = []
        for directory in self._parse(root):
            for subset in directory.subsets:
                family_id = f"{subset.tag}/{directory.baseline}"
                member_ids = [f"{family_id}/seed-{row.seed}" for row in subset.rows]
                for metric in PERFORMANCE_METRICS:
                    cell = subset.reported.get(metric)
                    records.append(
                        self._aggregation(directory, subset, family_id, metric, member_ids, cell)
                    )
        return records

    def _aggregation(
        self,
        directory: _RunDirectory,
        subset: _Subset,
        family_id: str,
        metric: str,
        member_ids: list[str],
        cell: tuple[float, float] | None,
    ) -> AggregationRecord:
        rel_dir = relative(self.root, directory.path)
        results_rel = f"{rel_dir}/results.csv"
        record = AggregationRecord(
            aggregation_id=f"{family_id}/{metric}@included",
            family_id=family_id,
            metric_name=metric,
            statistic="mean",
            transform="identity",
            member_run_ids=member_ids,
            excluded_run_ids=[],
            membership_rule=self._membership_rule(),
            # The std column of these artifacts is declared as read off the artifact
            # itself (population standard deviation, ddof=0); see _spread_notes().
            std_ddof=0,
            spread_basis=SpreadBasis.STANDARD_DEVIATION,
            display_multiplier=1.0,
        )
        if cell is not None:
            record.reported_value = cell[0]
            record.reported_spread = cell[1]
            record.reported_source = self._src(
                results_rel, key=f"dataset={subset.tag},metric={metric}"
            )
        record.documented_spread = self._documented_spread()
        record.implemented_spread = self._implemented_spread()
        record.implemented_selection = self._implemented_selection(metric)
        record.documented_selection = ProvenanceField.unknown(
            note="no sentence of README.md says which observation of a run a published "
            "cell stands for"
        )
        self._spread_notes()
        return record

    def _documented_spread(self) -> ProvenanceField[SpreadSemantics]:
        line, text = self._line_of("README.md", NEEDLE_SEM_PROSE)
        if line is None:
            return ProvenanceField.unknown(note="README.md never names the statistic")
        return ProvenanceField.of(
            SpreadSemantics.STANDARD_ERROR,
            ProvenanceStatus.CONFIRMED,
            self._src("README.md", line=line, key=text),
            note="quoted from the project's own documentation",
        )

    def _implemented_spread(self) -> ProvenanceField[SpreadSemantics]:
        """The artifacts and the shipped code give mutually incompatible accounts.

        ``src/experiment.py`` computes ``nanstd(ddof=1)/sqrt(n)`` (a sample standard
        error), while the project's own collector script states that the committed
        ``results.csv`` ``std`` columns are version-dependent ("raw std in early
        runs, SEM in later runs") - and these artifacts' values read as raw
        standard deviations.  Neither account is assertable alone, so the honest
        grade is CONFLICTING rather than either reading.
        """
        se_line, se_text = self._line_of(SRC_EXPERIMENT, NEEDLE_STD_ERR)
        hist_line, hist_text = self._line_of(SRC_COLLECTOR, NEEDLE_RAW_STD_HISTORY)
        sources = [
            self._src(SRC_EXPERIMENT, line=se_line, key=se_text),
            self._src(SRC_COLLECTOR, line=hist_line, key=hist_text),
        ]
        return ProvenanceField.conflicting(
            [s for s in sources if s.line is not None] or sources,
            note=(
                "the shipped aggregation code computes sample std / sqrt(n) while the "
                "committed results.csv cells are (per the project's own collector note) "
                "raw standard deviations from an earlier code version; the producing "
                "code version is not recorded by any run artifact (ED003)"
            ),
        )

    def _implemented_selection(self, metric: str) -> ProvenanceField[SelectionPolicy]:
        if metric == "mse":
            line, text = self._line_of(SRC_EXPERIMENT, NEEDLE_MSE_EVAL)
            return ProvenanceField.of(
                SelectionPolicy.LAST,
                ProvenanceStatus.CONFIRMED,
                self._src(SRC_EXPERIMENT, line=line, key=text),
                note="the test-set evaluation of the fitted baseline, taken once at the end "
                "of the pipeline; the run tracks no per-epoch series to select a best from",
            )
        needle = NEEDLE_AUG_ENSEMBLE if metric == "aug_mse" else NEEDLE_DELTA
        line, text = self._line_of(SRC_EXPERIMENT, needle)
        note = (
            "mean prediction of the 10 cross-validated augmented models on the test set"
            if metric == "aug_mse"
            else "percent change derived from mse and aug_mse of the same seed row"
        )
        return ProvenanceField.of(
            SelectionPolicy.OTHER,
            ProvenanceStatus.CONFIRMED,
            self._src(SRC_EXPERIMENT, line=line, key=text),
            note=note,
        )

    def _spread_notes(self) -> None:
        self._note(
            "results.csv 'std' columns are modelled with spread_basis=standard_deviation, "
            "std_ddof=0 because that is what the committed cell values are numerically equal "
            "to; src/experiment.py at HEAD computes a sample standard error instead, and the "
            "project's collector docstring states the column's meaning changed across "
            "versions, so implemented_spread is CONFLICTING rather than either single reading"
        )
        self._note(
            "p_wilcoxon and should_proceed are statistical gate diagnostics recorded per "
            "seed; their results.csv rows are not modelled as performance aggregations"
        )

    # ---------------------------------------------------------- project level
    def code_repository(self) -> ArtifactRef | None:
        path = self.root / SRC_EXPERIMENT
        if not path.is_file():
            return None
        ref = make_artifact_ref(self.root, path)
        ref.artifact_role = ArtifactRole.SOURCE_CODE
        return ref

    @property
    def notes(self) -> list[str]:
        self._note(
            "no run artifact records the git commit, package versions or hardware the "
            "experiments ran with; the clone HEAD is never substituted for them"
        )
        return sorted(set(self._notes))


def spec() -> AdapterSpec:
    return AdapterSpec(
        name="crda",
        description=(
            "CRDA main-experiment layout: timestamped directory per (dataset, baseline), "
            "one seed-level run per interim_results row, results.csv aggregates per subset"
        ),
        factory=CRDAAdapter,
    )


def install() -> None:
    register(spec())
