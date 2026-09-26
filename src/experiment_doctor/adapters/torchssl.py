"""TorchSSL adapter (TorchSSL/TorchSSL, the official FlexMatch/FreeMatch/SoftMatch toolbox).

Everything asserted here comes from the project's own artifacts:

* ``<logs_root>/<alg>_<dataset>_<num_labels>_<seed>/log.txt`` -- one text log per run,
  written by ``get_logger()``'s ``FileHandler`` (``utils.py:84-99``) and containing the
  effective configuration dump (``fixmatch.py:179``) plus one line per evaluation;
* ``scripts/average_log.py`` -- the only place the aggregation semantics are written down
  (group key = directory name minus its last underscore token, ``np.mean``/``np.std`` with
  ``np.std``'s default ``ddof=0``, printed to 2 decimals as ``mean±std``);
* ``scripts/config_generator.py`` -- how a config file, a ``save_name`` and a rendezvous
  port are allocated per (alg, dataset, label budget, seed);
* ``environment.yml`` -- the *declared* conda environment, never the recorded one.

Run identity: the project has no experiment tracker.  Its natural key is the run directory
name, which is also ``save_name``.  ``run_id`` keeps that name; ``seed`` is read from the
log, never derived from the name, and the two are cross-checked.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
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
    ArtifactType,
    ExclusionCategory,
    ExperimentFamily,
    ExperimentRun,
    FamilyKind,
    MetricDirection,
    MetricRecord,
    RunStatus,
    SpreadBasis,
    TerminationCause,
)

#: The project's own aggregation script: family key, statistic and spread live there.
AVERAGE_LOG = Path("scripts") / "average_log.py"
ENVIRONMENT_FILE = Path("environment.yml")
#: One config file per run, named by scripts/config_generator.py.
CONFIG_DIR = Path("config")

DATASETS = ("cifar10", "cifar100", "svhn", "stl10", "imagenet")
RUN_DIR_RE = re.compile(
    r"^(?P<alg>[a-z][a-z0-9_]*?)_"
    r"(?P<dataset>" + "|".join(DATASETS) + r")_"
    r"(?P<labels>\d+)_(?P<seed>\d+)$"
)
ARGUMENTS_RE = re.compile(r"Arguments: Namespace\((.*)\)\s*$")
TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \w+\]")
EVAL_LINE_RE = re.compile(
    r"^(?:\[[^\]]+\] )?(?P<it>\d+) iteration, USE_EMA: \w+, (?P<dict>.*?),\s*"
    r"BEST_EVAL_ACC: (?P<best>[0-9.]+), at (?P<best_it>\d+) iters$"
)
TOP1_RE = re.compile(r"'eval/top-1-acc': ([0-9.eE+-]+)")

#: The metric of record, named on the project's reported (percent) basis.  ``@best`` and
#: ``@last`` are this adapter's convention for the *selection policy* behind a value:
#: v0.1's MetricRecord has no policy field, and a name suffix plus ``primary_metric`` keeps
#: the two policies addressable without inventing one.
METRIC_BEST = "eval/top-1-acc@best"
METRIC_LAST = "eval/top-1-acc@last"

#: Keys the log records but which are run bookkeeping rather than experiment identity.
#: Each is stored on its own field (``seed``, ``run_id``, ``config_source``) or is a
#: launcher allocation (``dist_url``, handed out sequentially by config_generator.py).
LAUNCHER_KEYS = frozenset({"seed", "save_name", "c", "dist_url"})

#: Log lines are small; hashing them lets an acceptance run prove download integrity.
MAX_HASH_BYTES = 4_000_000


def _coerce(raw: str) -> Any:
    text = raw.strip()
    if text in ("True", "False"):
        return text == "True"
    if len(text) >= 2 and text[0] in "'\"" and text[-1] == text[0]:
        return text[1:-1]
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_namespace(text: str) -> dict[str, Any]:
    """``Namespace(a=1, b='x, y', c=True)`` -> dict, splitting on top-level commas only.

    Quoted values and bracketed collections may contain commas; a backslash escapes the
    next character.  A value that fails to parse this way would silently drop a config key
    from the run-identity comparison, so the splitter stays deliberately conservative.
    """
    args: dict[str, Any] = {}
    depth = 0
    quote: str | None = None
    start = 0
    index = 0

    def emit(chunk: str) -> None:
        if "=" not in chunk:
            return
        key, _, raw = chunk.partition("=")
        if re.fullmatch(r"\w+", key.strip()):
            args[key.strip()] = _coerce(raw)

    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            emit(text[start:index])
            start = index + 1
        index += 1
    emit(text[start:])
    return args


@dataclass
class RunLog:
    """What one ``log.txt`` says about its run."""

    directory: Path
    rel_path: str
    absolute_path: Path
    size: int
    mtime: float
    sha256: str | None
    args: dict[str, Any]
    evaluations: list[tuple[int, float]] = field(default_factory=list)
    logged_best: float | None = None
    logged_best_iteration: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    arguments_line: int | None = None

    @property
    def num_train_iter(self) -> int | None:
        value = self.args.get("num_train_iter")
        return int(value) if isinstance(value, int) else None

    @property
    def final_iteration(self) -> int | None:
        return self.evaluations[-1][0] if self.evaluations else None

    @property
    def final_eval_interval(self) -> int | None:
        """Spacing of the last two logged evaluations."""
        if len(self.evaluations) < 2:
            return None
        return self.evaluations[-1][0] - self.evaluations[-2][0]

    def policy_best(self) -> tuple[float, int] | None:
        """The running maximum under the project's own strict ``>`` rule."""
        best, at = 0.0, 0
        for iteration, value in self.evaluations:
            if value > best:
                best, at = value, iteration
        return (best, at) if self.evaluations else None


class TorchSSLAdapter(ExperimentAdapter):
    """Semantic adapter for TorchSSL shared run logs."""

    name = "torchssl"

    def __init__(
        self,
        root: Path | str,
        *,
        repo_root: Path | str | None = None,
        logs_root: Path | str | None = None,
        reported_table: Path | str | None = None,
    ) -> None:
        super().__init__(Path(root))
        self._repo_root = Path(repo_root).resolve() if repo_root else None
        self._logs_root = Path(logs_root).resolve() if logs_root else None
        self.reported_table = Path(reported_table) if reported_table else None
        self._layout_resolved = False
        self._logs_cache: dict[str, RunLog | None] = {}
        self._line_cache: dict[str, dict[str, int | None]] = {}
        self._runs_cache: list[ExperimentRun] | None = None
        self._notes: list[str] = []

    # ------------------------------------------------------------------ layout
    def describe(self) -> str:
        return (
            "TorchSSL: reads <alg>_<dataset>_<labels>_<seed>/log.txt run logs, their Arguments "
            "Namespace dump and per-evaluation lines, plus scripts/average_log.py aggregation rules"
        )

    def detect(self, root: Path) -> float:
        self._resolve_layout()
        run_dirs = self._run_dirs()
        if not run_dirs:
            return 0.0
        score = 0.6
        if self._average_log_path() is not None:
            score += 0.2
        groups = {self._family_id_of(path.name) for path in run_dirs}
        if any(len([p for p in run_dirs if self._family_id_of(p.name) == g]) > 1 for g in groups):
            score += 0.2
        return score

    def _resolve_layout(self) -> None:
        if self._layout_resolved:
            return
        self._layout_resolved = True
        root = self.root
        if self._logs_root is None:
            for candidate in (root, root / "logs", root / "downloads" / "logs"):
                if candidate.is_dir() and self._matching_dirs(candidate):
                    self._logs_root = candidate.resolve()
                    break
        if self._repo_root is None:
            for candidate in (root, root / "repo", root.parent / "repo"):
                if (candidate / AVERAGE_LOG).is_file():
                    self._repo_root = candidate.resolve()
                    break

    @property
    def logs_root(self) -> Path | None:
        self._resolve_layout()
        return self._logs_root

    @property
    def repo_root(self) -> Path | None:
        self._resolve_layout()
        return self._repo_root

    def _run_dirs(self) -> list[Path]:
        root = self.logs_root
        if root is None:
            return []
        return self._matching_dirs(root)

    @staticmethod
    def _matching_dirs(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        return sorted(
            (child for child in root.iterdir() if child.is_dir() and RUN_DIR_RE.match(child.name)),
            key=lambda path: path.name,
        )

    def _average_log_path(self) -> Path | None:
        repo = self.repo_root
        if repo is None:
            return None
        path = repo / AVERAGE_LOG
        return path if path.is_file() else None

    def _model_src(self, alg: str, needle: str, key: str) -> SourceRef | None:
        """Cite the line in ``models/<alg>/<alg>.py`` that states a rule, or None."""
        repo = self.repo_root
        if repo is None:
            return None
        path = repo / "models" / alg / f"{alg}.py"
        if not path.is_file():
            return None
        cache: dict[str, int | None] = self._line_cache.setdefault(str(path), {})
        if needle not in cache:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            cache[needle] = next(
                (number for number, text in enumerate(lines, start=1) if needle in text), None
            )
        line = cache[needle]
        if line is None:
            return None
        return self._src(relative(self.root, path), key=key, line=line)

    def _src(
        self, path: str, key: str | None = None, line: int | None = None, note: str | None = None
    ) -> SourceRef:
        return SourceRef(path=path, key=key, line=line, note=note)

    def _note(self, text: str) -> None:
        if text not in self._notes:
            self._notes.append(text)

    @staticmethod
    def _family_id_of(directory_name: str) -> str:
        match = RUN_DIR_RE.match(directory_name)
        if match is None:  # pragma: no cover - callers filter on the pattern
            return directory_name
        return f"{match.group('alg')}/{match.group('dataset')}_{match.group('labels')}"

    # --------------------------------------------------------------- log reading
    def _read_log(self, directory: Path) -> RunLog | None:
        key = str(directory)
        if key in self._logs_cache:
            return self._logs_cache[key]
        log_path = directory / "log.txt"
        if not log_path.is_file():
            self._logs_cache[key] = None
            return None
        stat = log_path.stat()
        digest = (
            hashlib.sha256(log_path.read_bytes()).hexdigest()
            if stat.st_size <= MAX_HASH_BYTES
            else None
        )
        log = RunLog(
            directory=directory,
            rel_path=relative(self.root, log_path),
            absolute_path=log_path,
            size=stat.st_size,
            mtime=round(stat.st_mtime, 3),
            sha256=digest,
            args={},
        )
        stamps: list[float] = []
        for number, line in enumerate(
            log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        ):
            if log.arguments_line is None:
                match = ARGUMENTS_RE.search(line)
                if match:
                    log.args = parse_namespace(match.group(1))
                    log.arguments_line = number + 1
            stamp = TIMESTAMP_RE.match(line)
            if stamp:
                stamps.append(_epoch(stamp.group(1)))
            evaluation = EVAL_LINE_RE.match(line)
            if evaluation:
                top1 = TOP1_RE.search(evaluation.group("dict"))
                if top1 is None:
                    continue
                log.evaluations.append((int(evaluation.group("it")), float(top1.group(1))))
                log.logged_best = float(evaluation.group("best"))
                log.logged_best_iteration = int(evaluation.group("best_it"))
        if stamps:
            log.start_time = stamps[0]
            log.end_time = stamps[-1]
        self._logs_cache[key] = log
        return log

    # ----------------------------------------------------------------- families
    def discover_families(self, root: Path) -> list[ExperimentFamily]:
        del root
        runs = self.discover_runs(self.root)
        rule_source = self._rule_source()
        families: list[ExperimentFamily] = []
        by_family: dict[str, list[ExperimentRun]] = {}
        for run in runs:
            by_family.setdefault(run.family_id, []).append(run)
        for family_id in sorted(by_family):
            members = by_family[family_id]
            match = RUN_DIR_RE.match(members[0].run_id)
            assert match is not None  # run ids are built from this pattern
            log = self._read_log(self.logs_root / members[0].run_id) if self.logs_root else None
            args = log.args if log else {}
            families.append(
                ExperimentFamily(
                    family_id=family_id,
                    name=f"{match.group('alg')}_{match.group('dataset')}_{match.group('labels')}",
                    kind=FamilyKind.EVALUATION,
                    result_dir=members[0].run_id,
                    method=members[0].method,
                    task=members[0].task,
                    run_ids=[run.run_id for run in members],
                    declared_repetitions=ProvenanceField.unknown(
                        note="README.md:58 claims seeds 0,1,2 while the shipped "
                        "scripts/config_generator.py:192 generates seeds=[0]; the artifacts disagree, "
                        "so no repetition count is asserted"
                    ),
                    membership_rule=ProvenanceField.of(
                        "every run directory whose log reaches the terminal evaluation enters the group "
                        "mean; the group key is the directory name minus its last underscore token",
                        ProvenanceStatus.SUPPORTED,
                        rule_source,
                        note="the aggregation loop has one skip branch only, the completeness gate at "
                        "average_log.py:82-84, whose condition is the hardcoded string '1048000 "
                        "iteration' at :23 -- a finished run of a different budget would be dropped "
                        "for that string alone",
                    ),
                    primary_metric=METRIC_BEST,
                )
            )
            self._record_family_notes(args, family_id, len(members))
        return families

    def _record_family_notes(self, args: dict[str, Any], family_id: str, n_runs: int) -> None:
        if not args:
            return
        self._note(
            f"{family_id}: {n_runs} runs share one identity key; each evaluation line records 14 metric "
            "keys (7 train/lr, 7 eval) but scripts/average_log.py consumes only eval/top-1-acc and "
            "eval/top-5-acc, and no direction is recorded for any of them"
        )

    def _rule_source(self) -> SourceRef | None:
        path = self._average_log_path()
        if path is None:
            return None
        return self._src(relative(self.root, path), key="group + np.mean/np.std", line=81)

    # --------------------------------------------------------------------- runs
    def discover_runs(self, root: Path) -> list[ExperimentRun]:
        if self._runs_cache is not None:
            return self._runs_cache
        del root
        runs: list[ExperimentRun] = []
        for directory in self._run_dirs():
            log = self._read_log(directory)
            if log is None:
                continue
            runs.append(self._build_run(log))
        self._runs_cache = runs
        return runs

    def _build_run(self, log: RunLog) -> ExperimentRun:
        match = RUN_DIR_RE.match(log.directory.name)
        assert match is not None
        alg, dataset, labels, dir_seed = (
            match.group("alg"),
            match.group("dataset"),
            int(match.group("labels")),
            int(match.group("seed")),
        )
        family_id = f"{alg}/{dataset}_{labels}"
        run = ExperimentRun(
            run_id=log.directory.name,
            family_id=family_id,
            status=RunStatus.COMPLETED_INCLUDED,
            artifacts=self._artifacts(log, alg, dataset, labels, dir_seed),
        )
        log_src = self._src(log.rel_path, line=log.arguments_line, key="Arguments")

        run.method = ProvenanceField.of(
            alg, ProvenanceStatus.CONFIRMED, self._src(log.rel_path, key="Arguments.alg")
        )
        run.task = ProvenanceField.of(
            f"semi-supervised image classification with {labels} labels on {dataset}",
            ProvenanceStatus.SUPPORTED,
            self._repo_src("README.md", 13, key="toolbox description"),
            note="the task phrase is the project's own prose; dataset and label budget are recorded "
            "in the run log",
        )
        run.dataset = ProvenanceField.of(
            dataset, ProvenanceStatus.CONFIRMED, self._src(log.rel_path, key="Arguments.dataset")
        )
        run.dataset_version = ProvenanceField.unknown(
            note="datasets/ssl_dataset.py fetches the archive by name into data_dir; "
            "no hash, release or version is recorded anywhere"
        )
        run.seed = self._seed_field(log, dir_seed)
        run.seed_derivation = ProvenanceField.of(
            "one config file per seed, named <alg>_<dataset>_<labels>_<seed>; the seed is a literal "
            "config value, not derived from a start_seed or from the run slot",
            ProvenanceStatus.SUPPORTED,
            self._repo_src("scripts/config_generator.py", 12, key="save_name template"),
        )
        run.tracker_run_id = ProvenanceField.unknown(
            note="no experiment tracker in this project; results are one text log per run directory"
        )
        run.parent_run_id = ProvenanceField.unknown(
            note="nothing links a run to a search or a parent"
        )
        run.repetition_index = ProvenanceField.unknown(
            note="the project records a seed value, never an ordinal; run count is not treated as one"
        )
        run.result_slot_index = None

        run.code_repository = ProvenanceField.of(
            "TorchSSL/TorchSSL",
            ProvenanceStatus.SUPPORTED,
            self._repo_src("README.md", 5, key="github asset url"),
            note="named by the repository's own README; no run artifact names a repository",
        )
        run.code_commit = ProvenanceField.unknown(
            note="no artifact records a commit, and the clone HEAD cannot stand in: the logged "
            "Namespace carries use_azure=False, an argument that exists nowhere at HEAD, so the "
            "script that ran is not the script that was cloned"
        )
        run.code_dirty = ProvenanceField.unknown(
            note="nothing records the working-tree state of the training machine"
        )

        run.config_source = ProvenanceField.of(
            str(log.args.get("c", "")),
            ProvenanceStatus.CONFIRMED,
            self._src(log.rel_path, key="Arguments.c"),
            note="the path the run was launched with; only seed-0 configs ship at HEAD and at least "
            "that one is not identical to what ran (its dist_url differs from the logged value)",
        )
        run.resolved_config = self._resolved_config(log, log_src)
        run.unrecorded_effective_parameters = [
            "cudnn.deterministic=True and cudnn.benchmark=True (assigned in code, not Namespace keys)",
            "the weak/strong augmentation transforms selected inside datasets/ssl_dataset.py per dataset",
            f"evaluation runs on the EMA shadow model (models/{alg}/{alg}.py apply_shadow), "
            "which no argument states",
        ]

        run.entrypoint = ProvenanceField.of(
            f"{alg}.py",
            ProvenanceStatus.INFERRED,
            self._repo_src("README.md", 121, key="usage"),
            note="the README documents 'python %s.py --c config/...'; the invocation itself is not "
            "logged, so the entrypoint stays a name-based inference" % alg,
        )
        run.command = ProvenanceField.unknown(
            note="the command line is not recorded; only the config path inside it is"
        )
        run.start_time = self._time_field(log, "start_time", log_src)
        run.end_time = self._time_field(log, "end_time", log_src)
        run.runtime_seconds = self._runtime_field(log)
        run.environment = self._environment_field()
        run.compute_budget = self._budget_field(log)
        run.history_rows = ProvenanceField.of(
            len(log.evaluations),
            ProvenanceStatus.CONFIRMED,
            self._src(log.rel_path, key="evaluation lines"),
            note="one row per evaluation, every num_eval_iter iterations",
        )
        run.termination_cause = self._termination_field(log)
        run.metrics = self._metrics(log, alg)
        run.included_in_aggregation = ProvenanceField.of(
            True,
            ProvenanceStatus.SUPPORTED,
            self._repo_src(
                str(AVERAGE_LOG), 82, key="Finish gate: only unfinished logs are skipped"
            ),
            note="membership is read from the aggregation script's behaviour, not from a per-run "
            "record; this log carries the '1048000 iteration' line the gate at :23 tests for, so the "
            "gate keeps it",
        )
        run.exclusion_category = ProvenanceField.of(
            ExclusionCategory.NONE,
            ProvenanceStatus.SUPPORTED,
            self._repo_src(str(AVERAGE_LOG), 84, key="the only continue in the aggregation loop"),
            note="this project has no exclusion mechanism beyond that completeness gate",
        )
        run.exclusion_reason = ProvenanceField.unknown(
            note="nothing was excluded, so there is no reason to record"
        )
        run.exclusion_evidence = ProvenanceField.unknown(
            note="no marker, comment or prose lists an excluded run"
        )
        return run

    def _seed_field(self, log: RunLog, dir_seed: int) -> ProvenanceField[int]:
        logged = log.args.get("seed")
        if not isinstance(logged, int):
            return ProvenanceField.unknown(
                note="the Arguments dump in this log carries no seed value"
            )
        if logged != dir_seed:
            return ProvenanceField.conflicting(
                [
                    self._src(log.rel_path, key="Arguments.seed"),
                    self._src(relative(self.root, log.directory), key="directory name"),
                ],
                note="the logged seed and the directory seed token disagree",
            )
        return ProvenanceField.of(
            logged,
            ProvenanceStatus.CONFIRMED,
            self._src(log.rel_path, line=log.arguments_line, key="Arguments.seed"),
            note="recorded by the run itself; the directory and config names agree with it and were "
            "used only as a cross-check, never as the source",
        )

    def _resolved_config(
        self, log: RunLog, log_src: SourceRef
    ) -> ProvenanceField[dict[str, object]]:
        if not log.args:
            return ProvenanceField.unknown(note="this log carries no Arguments dump")
        identity = {
            key: value for key, value in sorted(log.args.items()) if key not in LAUNCHER_KEYS
        }
        withheld = sorted(key for key in LAUNCHER_KEYS if key in log.args)
        return ProvenanceField.of(
            dict(identity),
            ProvenanceStatus.CONFIRMED,
            log_src,
            note="the effective Namespace as logged after over_write_args_from_file() and the in-code "
            "mutations; %s are withheld because they vary per run and live on their own fields "
            "(seed, run_id, config_source) or are launcher port allocations "
            "(scripts/config_generator.py:194)" % ", ".join(withheld),
        )

    def _time_field(self, log: RunLog, which: str, log_src: SourceRef) -> ProvenanceField[float]:
        value = getattr(log, which)
        if value is None:
            return ProvenanceField.unknown(note="this log has no timestamped line")
        return ProvenanceField.of(
            value,
            ProvenanceStatus.CONFIRMED,
            self._src(log.rel_path, key=which, note=str(log_src.path)),
            note="the logger's asctime; naive local wall clock, no timezone is recorded",
        )

    def _runtime_field(self, log: RunLog) -> ProvenanceField[float]:
        if log.start_time is None or log.end_time is None:
            return ProvenanceField.unknown(note="both ends of the log must carry a timestamp")
        return ProvenanceField.of(
            round(log.end_time - log.start_time, 3),
            ProvenanceStatus.SUPPORTED,
            self._src(log.rel_path, key="first and last timestamped line"),
            note="difference of the two logged stamps; the last line is a checkpoint save after the "
            "final evaluation, not process exit",
        )

    def _environment_field(self) -> ProvenanceField[str]:
        repo = self.repo_root
        path = repo / ENVIRONMENT_FILE if repo is not None else None
        if path is None or not path.is_file():
            return ProvenanceField.unknown(
                note="no environment declaration reachable from this root"
            )
        declared = _declared_environment(path)
        return ProvenanceField.of(
            declared,
            ProvenanceStatus.SUPPORTED,
            self._src(relative(self.root, path), key="conda env pins"),
            note="the declared environment of the repository.  No log line records a Python, PyTorch, "
            "CUDA or GPU-model version, so this can never be CONFIRMED for a historical run",
        )

    def _budget_field(self, log: RunLog) -> ProvenanceField[str]:
        gpu = log.args.get("gpu")
        return ProvenanceField.of(
            f"logged device index gpu={gpu}; the project claims a single P100 for CIFAR-10 in prose",
            ProvenanceStatus.SUPPORTED,
            self._repo_src("README.md", 26, key="hardware per dataset"),
            note="a statement about the campaign, attached to every run of that dataset; the log "
            "evidences the device index only",
        )

    def _termination_field(self, log: RunLog) -> ProvenanceField[TerminationCause]:
        budget, final = log.num_train_iter, log.final_iteration
        if budget is None or final is None:
            return ProvenanceField.unknown(
                note="neither the budget nor the last iteration is logged"
            )
        alg = str(log.args.get("alg", ""))
        if final >= budget:
            return ProvenanceField.of(
                TerminationCause.ITERATION_CAP,
                ProvenanceStatus.CONFIRMED,
                self._src(log.rel_path, key="final evaluation iteration"),
            )
        break_src = self._model_src(alg, "if self.it > args.num_train_iter", "iteration-cap break")
        interval = log.final_eval_interval
        declared_step = log.args.get("num_eval_iter")
        if interval is None or not log.evaluations:
            return ProvenanceField.unknown(note="a single evaluation line cannot show the cadence")
        if final != (budget // interval) * interval:
            return ProvenanceField.of(
                TerminationCause.UNKNOWN,
                ProvenanceStatus.INFERRED,
                self._src(log.rel_path, key="final evaluation iteration"),
                note="the log stops at %d, which is not the last evaluation the %d-iteration grid "
                "would produce before the declared budget of %d" % (final, interval, budget),
            )
        cap_src = self._model_src(alg, "self.num_eval_iter = 1000", "eval interval overwritten")
        if declared_step == interval:
            reason = "the declared num_eval_iter=%s" % declared_step
        else:
            self._note(
                "num_eval_iter is mutated inside the training loop, so the config value is not the "
                "effective evaluation cadence: logs switch to one evaluation every 1000 iterations "
                "past 0.8 * num_train_iter"
            )
            reason = "the eval interval the code assigns past 0.8 * num_train_iter%s" % (
                " (models/%s/%s.py:%s sets it to 1000)" % (alg, alg, cap_src.line)
                if cap_src
                else ", which the last log lines show as %d" % interval
            )
        return ProvenanceField.of(
            TerminationCause.ITERATION_CAP,
            ProvenanceStatus.CONFIRMED,
            self._src(log.rel_path, key="final evaluation iteration"),
            note="the loop breaks once it > num_train_iter=%d%s; the last logged evaluation is %d, "
            "the largest multiple of %s at or below the budget under %s"
            % (
                budget,
                " (" + str(break_src.path) + ":" + str(break_src.line) + ")" if break_src else "",
                final,
                interval,
                reason,
            ),
        )

    def _metrics(self, log: RunLog, alg: str) -> list[MetricRecord]:
        records: list[MetricRecord] = []
        policy = log.policy_best()
        if policy is None:
            return records
        best, best_iteration = policy
        logged = log.logged_best
        rule_src = self._model_src(
            alg, "tb_dict['eval/top-1-acc'] > best_eval_acc", "strict > on eval/top-1-acc"
        )
        direction = ProvenanceField.of(
            MetricDirection.MAXIMIZE,
            ProvenanceStatus.CONFIRMED if rule_src is not None else ProvenanceStatus.INFERRED,
            rule_src or self._src(log.rel_path, key="BEST_EVAL_ACC"),
            note="the project's own best-tracking comparison is a strict > on eval/top-1-acc, and the "
            "running maximum it logs matches a recomputed strict-> scan over all %d evaluations"
            % len(log.evaluations)
            + ("" if rule_src else "; the method file was not readable, so the rule is inferred"),
        )
        if logged is not None and abs(logged - best) > 1e-12:
            records.append(
                MetricRecord(
                    name=METRIC_BEST,
                    value=ProvenanceField.conflicting(
                        [
                            self._src(log.rel_path, key="BEST_EVAL_ACC"),
                            self._src(log.rel_path, key="recomputed running maximum"),
                        ],
                        note="the logged best and the recomputed best disagree",
                    ),
                    direction=direction,
                    status=ProvenanceStatus.CONFLICTING,
                )
            )
        else:
            records.append(
                MetricRecord(
                    name=METRIC_BEST,
                    value=ProvenanceField.of(
                        best * 100.0,
                        ProvenanceStatus.CONFIRMED,
                        self._src(log.rel_path, key="BEST_EVAL_ACC"),
                        note="the log prints the fraction (%s); scripts/average_log.py:92 multiplies by "
                        "100 before aggregating, so the value is stored on the reported percent basis"
                        % _fmt(best),
                    ),
                    step=ProvenanceField.of(
                        best_iteration,
                        ProvenanceStatus.CONFIRMED,
                        self._src(log.rel_path, key="at <it> iters"),
                        note="the iteration the project itself reports for this best value",
                    ),
                    direction=direction,
                    source=self._src(log.rel_path, key="evaluation lines"),
                    status=ProvenanceStatus.CONFIRMED,
                )
            )
        last_iteration, last_value = log.evaluations[-1]
        records.append(
            MetricRecord(
                name=METRIC_LAST,
                value=ProvenanceField.of(
                    last_value * 100.0,
                    ProvenanceStatus.CONFIRMED,
                    self._src(log.rel_path, key="final evaluation line"),
                    note="the accuracy at the iteration cap; this project never publishes it, it is "
                    "recorded so the selection policy can be measured",
                ),
                step=ProvenanceField.of(
                    last_iteration,
                    ProvenanceStatus.CONFIRMED,
                    self._src(log.rel_path, key="final evaluation line"),
                ),
                direction=direction,
                source=self._src(log.rel_path, key="evaluation lines"),
                status=ProvenanceStatus.CONFIRMED,
            )
        )
        return records

    def _artifacts(
        self, log: RunLog, alg: str, dataset: str, labels: int, seed: int
    ) -> list[ArtifactRef]:
        artifacts = [
            ArtifactRef(
                path=log.rel_path,
                artifact_type=ArtifactType.LOG,
                size=log.size,
                mtime=log.mtime,
                sha256=log.sha256,
            )
        ]
        repo = self.repo_root
        if repo is not None:
            config = repo / CONFIG_DIR / alg / f"{alg}_{dataset}_{labels}_{seed}.yaml"
            # Only seed-0 configs ship at HEAD; naming an absent file as an artifact would
            # invent evidence.  Its absence is recorded on config_source instead.
            if config.is_file():
                artifacts.append(make_artifact_ref(self.root, config, hash_small_files=True))
        return artifacts

    # ------------------------------------------------------------- aggregations
    def discover_aggregations(self, root: Path) -> list[AggregationRecord]:
        reported = self._reported_cells()
        self._note(
            "the published cell is round(np.mean(v), 2) + '\\u00b1' + round(np.std(v), 2) "
            "(scripts/average_log.py:132): each component rounds independently, np.std's default "
            "ddof=0 makes the spread a population standard deviation over the seed group, and no "
            "division by sqrt(N) happens anywhere in the script"
        )
        runs_by_family: dict[str, list[ExperimentRun]] = {}
        for run in self.discover_runs(root):
            runs_by_family.setdefault(run.family_id, []).append(run)
        records: list[AggregationRecord] = []
        for family in self.discover_families(root):
            runs = runs_by_family.get(family.family_id, [])
            included = [run for run in runs if run.included_in_aggregation.value is True]
            records.append(
                self._aggregation(
                    family, METRIC_BEST, included, "included", family.membership_rule, reported
                )
            )
            records.append(
                self._aggregation(
                    family,
                    METRIC_LAST,
                    included,
                    "included",
                    ProvenanceField.of(
                        "counterfactual: the same run set reduced from the accuracy at the iteration "
                        "cap instead of the logged best",
                        ProvenanceStatus.INFERRED,
                        family.membership_rule.source,
                        note="this project never published a last-epoch table; recorded to measure how "
                        "far the selection policy moves the number",
                    ),
                    reported,
                )
            )
        return records

    def _aggregation(
        self,
        family: ExperimentFamily,
        metric_name: str,
        members: Iterable[ExperimentRun],
        variant: str,
        membership: ProvenanceField[str],
        reported: dict[tuple[str, str, str], dict[str, Any]],
    ) -> AggregationRecord:
        member_ids = [run.run_id for run in members]
        record = AggregationRecord(
            aggregation_id=f"{family.family_id}/{metric_name}@{variant}",
            family_id=family.family_id,
            metric_name=metric_name,
            statistic="mean",
            transform="identity",
            member_run_ids=member_ids,
            excluded_run_ids=[],
            n=len(member_ids),
            std_ddof=0,
            spread_basis=SpreadBasis.STANDARD_DEVIATION,
            display_multiplier=1.0,
            membership_rule=membership,
        )
        cell = reported.get((family.family_id, metric_name, variant))
        if cell is not None:
            self._attach_reported(record, cell)
        return record

    def _reported_cells(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        path = self.reported_table
        if path is None or not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        out: dict[tuple[str, str, str], dict[str, Any]] = {}
        for cell in data.get("cells", []):
            variant = str(cell.get("variant", "included"))
            out[(str(cell["family"]), str(cell["metric"]), variant)] = cell
        return out

    def _attach_reported(self, record: AggregationRecord, cell: dict[str, Any]) -> None:
        decimals = cell.get("decimals")
        tolerance = cell.get("value_tolerance")
        if tolerance is None and isinstance(decimals, int):
            # Rounding half-width of the printed digits, plus boundary slack.
            tolerance = 0.5 * 10.0**-decimals * (1.0 + 1e-9)
        record.reported_value = float(cell["value"]) if cell.get("value") is not None else None
        record.reported_spread = float(cell["spread"]) if cell.get("spread") is not None else None
        if tolerance is not None:
            record.tolerance = float(tolerance)
        record.spread_tolerance = (
            float(cell["spread_tolerance"])
            if cell.get("spread_tolerance") is not None
            else record.tolerance
        )
        record.reported_source = SourceRef(
            path=str(self.reported_table),
            key=f"{record.family_id}/{record.metric_name}@{record.variant}",
            note=str(cell.get("source", "")),
        )

    # -------------------------------------------------------------- project level
    def code_repository(self) -> ArtifactRef | None:
        path = self._average_log_path()
        if path is None:
            return None
        return make_artifact_ref(self.root, path)

    def _repo_src(self, rel: str, line: int | None = None, key: str | None = None) -> SourceRef:
        repo = self.repo_root
        path = relative(self.root, repo / rel) if repo is not None else rel
        return self._src(path, key=key, line=line)

    @property
    def notes(self) -> list[str]:
        notes = list(self._notes)
        notes.append(
            "the run log's Arguments dump is the effective config (post YAML overwrite, post in-code "
            "mutation), so HEAD's shipped YAMLs were not merged into it; at least one shipped seed-0 "
            "YAML disagrees with the log it names (dist_url), which is why config_source is a path and "
            "not a contents claim"
        )
        notes.append(
            "no log records a Python/PyTorch/CUDA/GPU version, so environment stays SUPPORTED from "
            "environment.yml and is never CONFIRMED"
        )
        return sorted(set(notes))


def _epoch(stamp: str) -> float:
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S,%f").timestamp()


def _fmt(value: float) -> str:
    return f"{value:.4f}"


#: Packages whose pins matter for reproducing a run, whether declared with conda
#: (``pkg=version=build``) or under the pip section (``pkg==version``).
ENVIRONMENT_PINS = (
    "python",
    "pytorch",
    "torchvision",
    "torchaudio",
    "cudatoolkit",
    "numpy",
    "pyyaml",
)


def _declared_environment(path: Path) -> str:
    """Name and key pins of the declared conda environment, read from the file itself."""
    found: dict[str, str] = {}
    name = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        # conda writes list items as '  - pkg=version=build' and pip items as '  - pkg==version'.
        text = line.strip().lstrip("-").strip()
        if text.startswith("name:"):
            name = text.split(":", 1)[1].strip()
            continue
        for package in ENVIRONMENT_PINS:
            if text.startswith(f"{package}=") or text.startswith(f"{package}=="):
                # conda writes 'pkg=version=build_hash', pip writes 'pkg==version'.
                parts = text.split("=")
                version = next((part for part in parts[1:] if part and part != parts[0]), "")
                if version:
                    found.setdefault(package, version)
    body = ", ".join(f"{package}=={version}" for package, version in sorted(found.items()))
    if not body:
        return f"conda env '{name}' declared, no key pins matched"
    return f"conda env '{name or path.name}' declared: {body}"


def install() -> None:
    register(
        AdapterSpec(
            name="torchssl",
            description=(
                "reads TorchSSL shared run logs (<alg>_<dataset>_<labels>_<seed>/log.txt): seed and "
                "effective config from the Arguments dump, best/last accuracy from the evaluation "
                "lines, family key and mean±std from scripts/average_log.py"
            ),
            factory=TorchSSLAdapter,
            options=("repo_root", "logs_root", "reported_table"),
        )
    )


__all__ = ["TorchSSLAdapter", "install", "parse_namespace"]
