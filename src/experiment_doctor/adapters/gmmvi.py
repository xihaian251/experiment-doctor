"""GMMVI Experiment 3 adapter (OlegArenz/gmmvi_reproducibility, TMLR 2023).

Everything recovered here comes from the project's own artifacts:

* ``results/<DIR>/<group>/run_{i}.csv`` / ``.csv.bad`` / ``run_{i}_config.yml``
  written by ``evaluations/fetch_exp3.py``;
* ``evaluations/fetch_exp3.py`` itself -- the only place where the aggregation
  semantics are written down (final-row metric, ``np.std`` default ddof=0,
  ``3/sqrt(N)`` spread, the ``elbo_fb:`` negation, the per-run secondary
  ``np.sum``) together with the ``bad_run_ids`` exclusion lists;
* ``configs/exp3 (eval)/*.yml`` multi-document clusterwork2 configs, which declare
  the ``wandb.group`` -> method/environment mapping and ``repetitions``;
* ``README.rst``, the only prose stating *why* runs were dropped.

``run_{i}`` is a fetch slot: not an identity, not a seed, not a repetition index
(Phase 0 constraint A).  Seeds are never derived from it.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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
)

#: Tracking metadata columns, not experiment metrics.
INFRA_COLUMNS = {"", "_step", "num_samples", "_runtime", "_timestamp", "_id", "_name", "index"}
PRIMARY_CANDIDATES = {"-elbo", "elbo_fb:"}
#: Metrics the project's own fetch code negates before aggregating (fetch_exp3.py).
NEGATED_METRICS = {"elbo_fb:"}
EVAL_DIR_SUFFIX = "_EVAL"
SKIP_RESULT_DIRS = ("exp1_",)
FETCH_SCRIPT = Path("evaluations") / "fetch_exp3.py"
CONFIG_FOLDERS = ("exp3 (eval)", "exp3 (hyperopt)")
CLUSTERWORK_SCRIPT = Path("evaluations") / "clusterwork.py"
SWEEP_WORKER = Path("hyperopt") / "wandb_sweep.py"

#: Why the seed stays UNKNOWN, per launcher.  The rule is in the code; its operand is not.
_SEED_DERIVATION_NOTE = {
    True: (
        f"{CLUSTERWORK_SCRIPT.as_posix()} declares seed = start_seed + rep, but start_seed is a "
        "library default and no archived artifact records its value"
    ),
    False: (
        f"{SWEEP_WORKER.as_posix()} fixes seed = 1 for every sweep worker, so a search "
        "repetition is a hyperparameter draw rather than a new seed"
    ),
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _to_int(text: str) -> int | None:
    lowered = text.strip().lower()
    if lowered.isdigit():
        return int(lowered)
    return NUMBER_WORDS.get(lowered)


def _is_float(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, start=1):
        current = [index]
        for column, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[len(right)]


@dataclass
class FetchCall:
    """One ``fetch_exp3_eval``/``fetch_exp3_hyperopt`` declaration in fetch_exp3.py."""

    kind: str
    project: str
    folder: str
    groups: list[str]
    metric: str
    secondary_metrics: list[str]
    bad_run_ids: list[str]
    bad_id_comments: dict[str, str]
    line: int
    source_path: str
    active: bool


@dataclass
class GroupDecl:
    """One environment document of a cw2 config file, plus its DEFAULT values."""

    group: str
    method_alias: str
    algorithm_id: str | None
    doc_name: str
    experiment_id: str | None
    repetitions: int | None
    iterations: int | None
    config_path: str
    absolute_path: Path
    folder: str


@dataclass
class ExclusionClaim:
    """One README statement of how many seeds were dropped for one experiment."""

    raw_method: str
    raw_env: str
    count: int | None
    reason: str
    category: ExclusionCategory
    line: int
    source_path: str


@dataclass
class HistoryData:
    """Final logged values of one run history CSV."""

    columns: list[str]
    rows: int
    finals: dict[str, float]
    last_step: int | None
    last_runtime: float | None
    rel_path: str
    absolute_path: Path


class GMMVIAdapter(ExperimentAdapter):
    """Semantic adapter for gmmvi Experiment 3 artifacts."""

    name = "gmmvi-exp3"

    def __init__(
        self,
        root: Path | str,
        *,
        repo_root: Path | str | None = None,
        results_root: Path | str | None = None,
        reported_table: Path | str | None = None,
    ) -> None:
        super().__init__(Path(root))
        self._repo_root = Path(repo_root).resolve() if repo_root else None
        self._results_root = Path(results_root).resolve() if results_root else None
        self.reported_table = Path(reported_table) if reported_table else None
        self._layout_resolved = False
        self._fetch_calls: list[FetchCall] | None = None
        self._groups: dict[str, GroupDecl] | None = None
        self._directions: dict[str, tuple[MetricDirection, SourceRef]] | None = None
        self._readme_claims: list[ExclusionClaim] | None = None
        self._history_cache: dict[tuple[str, str], dict[int, HistoryData | None]] = {}
        self._families_cache: list[ExperimentFamily] | None = None
        self._runs_cache: list[ExperimentRun] | None = None
        self._notes: list[str] = []

    # ------------------------------------------------------------------ layout
    def describe(self) -> str:
        return (
            "gmmvi Experiment 3: reads fetch_exp3.py aggregation semantics, run_{i}.csv[.bad] "
            "histories, cw2 multi-doc configs and README.rst exclusion prose"
        )

    def detect(self, root: Path) -> float:
        self._resolve_layout()
        if self._results_root is None:
            return 0.0
        if not self._fetch_declarations():
            return 0.0
        score = 0.5
        if self._config_declarations():
            score += 0.3
        if self._project_readme_claims():
            score += 0.2
        return score

    def _resolve_layout(self) -> None:
        if self._layout_resolved:
            return
        self._layout_resolved = True
        root = self.root
        if self._repo_root is None:
            for candidate in (
                root,
                root / "repo",
                root / "gmmvi_reproducibility",
                root.parent / "repo",
            ):
                if (candidate / FETCH_SCRIPT).is_file():
                    self._repo_root = candidate.resolve()
                    break
        if self._results_root is None:
            candidates = [
                root / "extracted" / "evaluations" / "results",
                root / "evaluations" / "results",
                root / "results",
                root,
            ]
            for candidate in candidates:
                if candidate.is_dir() and any(
                    child.is_dir() and child.name.endswith(EVAL_DIR_SUFFIX)
                    for child in candidate.iterdir()
                ):
                    self._results_root = candidate.resolve()
                    break

    @property
    def repo_root(self) -> Path:
        self._resolve_layout()
        if self._repo_root is None:
            raise RuntimeError(
                f"no gmmvi repo root containing {FETCH_SCRIPT} found under {self.root}"
            )
        return self._repo_root

    @property
    def results_root(self) -> Path | None:
        self._resolve_layout()
        return self._results_root

    def _src(self, path: str, key: str | None = None, line: int | None = None) -> SourceRef:
        return SourceRef(path=path, key=key, line=line)

    def _fetch_path(self) -> Path:
        return self.repo_root / FETCH_SCRIPT

    # ------------------------------------------------- fetch_exp3.py semantics
    def _fetch_declarations(self) -> list[FetchCall]:
        if self._fetch_calls is not None:
            return self._fetch_calls
        path = self._fetch_path()
        if not path.is_file():
            self._fetch_calls = []
            return self._fetch_calls
        rel = relative(self.root, path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        calls: list[FetchCall] = []
        index = 0
        while index < len(lines):
            match = re.search(r"fetch_exp3_(eval|hyperopt)\(", lines[index])
            if not match:
                index += 1
                continue
            active = not lines[index].lstrip().startswith("#")
            start_line = index + 1
            chunk = lines[index][match.start() :]
            depth = chunk.count("(") - chunk.count(")")
            index += 1
            while depth > 0 and index < len(lines):
                chunk += "\n" + lines[index]
                depth += lines[index].count("(") - lines[index].count(")")
                index += 1
            call = self._parse_fetch_call(chunk, match.group(1), start_line, rel, active)
            if call is not None:
                calls.append(call)
        self._fetch_calls = calls
        self._extract_direction_rules(calls)
        self._note_folder_collisions(calls)
        return calls

    @staticmethod
    def _strip_comments(text: str) -> str:
        """Remove trailing ``#`` comments that are not inside a string literal."""
        out: list[str] = []
        quote: str | None = None
        for char in text:
            if quote:
                out.append(char)
                if char == quote:
                    quote = None
                continue
            if char in "\"'":
                quote = char
                out.append(char)
                continue
            if char == "#":
                break
            out.append(char)
        return "".join(out)

    def _parse_fetch_call(
        self, chunk: str, kind: str, line: int, rel: str, active: bool
    ) -> FetchCall | None:
        open_paren = chunk.index("(")
        body = chunk[open_paren + 1 :]
        clean = self._strip_comments(body)
        literals = re.findall(r'"([^"]*)"', clean)
        if len(literals) < 2:
            return None
        project, folder = literals[0], literals[1]
        groups: list[str] = []
        group_block = re.search(r"\[([^\]]*)\]", clean)
        if group_block:
            groups = re.findall(r'"([^"]*)"', group_block.group(1))
        metric_match = re.search(r'metric\s*=\s*"([^"]+)"', clean)
        secondary_match = re.search(r"secondary_metrics\s*=\s*\[([^\]]*)\]", clean)
        bad_match = re.search(r"bad_run_ids\s*=\s*\[(.*?)\]", body, re.S)
        bad_ids: list[str] = []
        bad_comments: dict[str, str] = {}
        if bad_match:
            pending: list[str] = []
            for token in re.finditer(
                r'"([a-z0-9]{6,12})"(\s*,)?\s*(?:#\s*(\w+))?', bad_match.group(1)
            ):
                bad_ids.append(token.group(1))
                pending.append(token.group(1))
                if token.group(3):
                    # a trailing comment labels every id on its line, not just the last one
                    for pending_id in pending:
                        bad_comments[pending_id] = token.group(3).lower()
                    pending = []
        secondary = re.findall(r'"([^"]+)"', secondary_match.group(1)) if secondary_match else []
        return FetchCall(
            kind=kind,
            project=project,
            folder=folder,
            groups=groups,
            metric=metric_match.group(1) if metric_match else "-elbo",
            secondary_metrics=secondary,
            bad_run_ids=bad_ids,
            bad_id_comments=bad_comments,
            line=line,
            source_path=rel,
            active=active,
        )

    def _extract_direction_rules(self, calls: list[FetchCall]) -> None:
        """Metric direction must be evidenced by the project's code, never by its name."""
        if self._directions is not None:
            return
        path = self._fetch_path()
        self._directions = {}
        if not path.is_file():
            return
        rel = relative(self.root, path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        default_flag_line: int | None = None
        default_direction = MetricDirection.MINIMIZE
        pending: tuple[str, int] | None = None
        for number, text in enumerate(lines, start=1):
            declared = re.search(r"secondary_metrics\[0\]\s*==\s*[\"']([^\"']+)[\"']", text)
            if declared:
                # A declaration the code never re-flags keeps the value set before the chain.
                if pending:
                    self._directions[pending[0]] = (
                        default_direction,
                        self._src(
                            rel, key="secondary default of the branch chain", line=pending[1]
                        ),
                    )
                pending = (declared.group(1), number)
                continue
            assignment = re.match(r"\s*larger_is_better\s*=\s*(True|False)\s*$", text)
            if assignment and pending is None and default_flag_line is None:
                default_flag_line = number
                default_direction = (
                    MetricDirection.MAXIMIZE
                    if assignment.group(1) == "True"
                    else MetricDirection.MINIMIZE
                )
                continue
            flag = re.search(r"larger_is_better\s*=\s*(True|False)", text)
            if flag and pending:
                name, start = pending
                direction = (
                    MetricDirection.MAXIMIZE
                    if flag.group(1) == "True"
                    else MetricDirection.MINIMIZE
                )
                self._directions[name] = (
                    direction,
                    self._src(rel, key=f"'{name}' branch", line=start),
                )
                pending = None
        if pending:
            self._directions[pending[0]] = (
                default_direction,
                self._src(rel, key="secondary default of the branch chain", line=pending[1]),
            )
        for number, text in enumerate(lines, start=1):
            if re.search(r"def latex_format\(.*larger_is_better=False", text):
                self._directions["__primary__"] = (
                    MetricDirection.MINIMIZE,
                    self._src(rel, key="latex_format default larger_is_better=False", line=number),
                )

    def _note_folder_collisions(self, calls: list[FetchCall]) -> None:
        seen: dict[str, list[FetchCall]] = {}
        for call in calls:
            if call.kind == "eval":
                seen.setdefault(call.folder, []).append(call)
        for folder, group in sorted(seen.items()):
            if len({call.project for call in group}) > 1:
                projects = ", ".join(sorted({call.project for call in group}))
                self._notes.append(
                    f"results/{folder}/ is written by {len(group)} fetch declarations from different "
                    f"tracking projects ({projects}); the surviving CSV columns identify which fetch "
                    "produced the archived files, the folder name alone does not"
                )

    # ------------------------------------------------------ cw2 config semantics
    def _config_declarations(self) -> dict[str, GroupDecl]:
        if self._groups is not None:
            return self._groups
        groups: dict[str, GroupDecl] = {}
        self._groups = groups
        base = self.repo_root / "evaluations" / "configs"
        for folder in CONFIG_FOLDERS:
            directory = base / folder
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.yml")):
                self._ingest_cw2_file(path, folder, groups)
        return groups

    def _ingest_cw2_file(self, path: Path, folder: str, groups: dict[str, GroupDecl]) -> None:
        rel = relative(self.root, path)
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8", errors="replace")))
        except (OSError, yaml.YAMLError) as exc:
            self._notes.append(f"{rel}: unreadable multi-document YAML ({type(exc).__name__})")
            return
        default: dict[str, Any] | None = None
        for document in documents:
            if isinstance(document, dict) and document.get("name") == "DEFAULT":
                default = document
        if default is None:
            return
        for document in documents:
            if not isinstance(document, dict):
                continue
            wandb_block = document.get("wandb")
            group = wandb_block.get("group") if isinstance(wandb_block, dict) else None
            if not group:
                continue
            decl = GroupDecl(
                group=str(group),
                method_alias=path.stem,
                algorithm_id=default.get("algorithm_id")
                if isinstance(default.get("algorithm_id"), str)
                else None,
                doc_name=str(document.get("name")),
                experiment_id=document.get("experiment_id"),
                repetitions=document.get("repetitions")
                if document.get("name") == "DEFAULT"
                else default.get("repetitions"),
                iterations=document.get("iterations")
                if document.get("name") == "DEFAULT"
                else default.get("iterations"),
                config_path=rel,
                absolute_path=path,
                folder=folder,
            )
            kind = "eval" if folder == "exp3 (eval)" else "hyperopt"
            groups.setdefault(f"{kind}:{decl.group.lower()}", decl)

    @staticmethod
    def _unwrap_config(node: Any) -> Any:
        """The tracking service stored config leaves as ``{desc, value}`` wrappers."""
        if isinstance(node, dict):
            if "value" in node and set(node) <= {"desc", "value"}:
                return GMMVIAdapter._unwrap_config(node["value"])
            return {str(key): GMMVIAdapter._unwrap_config(value) for key, value in node.items()}
        if isinstance(node, list):
            return [GMMVIAdapter._unwrap_config(item) for item in node]
        return node

    @staticmethod
    def _flatten(node: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for key, value in node.items():
            full = f"{prefix}{key}"
            if isinstance(value, dict):
                flat.update(GMMVIAdapter._flatten(value, f"{full}."))
            else:
                flat[full] = value
        return flat

    # ------------------------------------------------------------ README prose
    def _project_readme_claims(self) -> list[ExclusionClaim]:
        if self._readme_claims is not None:
            return self._readme_claims
        self._readme_claims = []
        path = self.repo_root / "README.rst"
        if not path.is_file():
            return self._readme_claims
        rel = relative(self.root, path)
        pattern = re.compile(
            r"^\s*[-*]+\s+(?P<m>[A-Za-z]{5,})\s+on\s+(?P<env>[A-Za-z0-9 ]+?):\s*(?P<n>\d+)\s+bad seeds"
        )
        for number, text in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            match = pattern.match(text)
            if match:
                self._readme_claims.append(
                    ExclusionClaim(
                        raw_method=match.group("m"),
                        raw_env=match.group("env").strip(),
                        count=int(match.group("n")),
                        reason=text.strip(),
                        category=ExclusionCategory.COMPLETED_OUTLIER,
                        line=number,
                        source_path=rel,
                    )
                )
                continue
            oom = re.search(
                r"ignored\s+(?P<n>\d+|[a-z]{3,5})\s+seeds.*?for\s+(?P<m>[A-Z]{5,})\s+on\s+(?P<env>[A-Za-z0-9]+)",
                text,
            )
            if oom:
                self._readme_claims.append(
                    ExclusionClaim(
                        raw_method=oom.group("m"),
                        raw_env=oom.group("env"),
                        count=_to_int(oom.group("n")),
                        reason="terminated early due to OOM",
                        category=ExclusionCategory.OOM,
                        line=number,
                        source_path=rel,
                    )
                )
        return self._readme_claims

    def _decl_for(self, group_name: str, is_eval: bool) -> GroupDecl | None:
        """Look the group up inside the folder it was launched from.

        The eval and hyperopt configs declare the same ``wandb.group`` names with
        different protocols (``repetitions: 10`` vs ``repetitions: 1``,
        ``iterations: 1000000`` vs ``100000``), so a shared lookup would mis-cite
        the search families with the evaluation protocol.
        """
        kind = "eval" if is_eval else "hyperopt"
        declarations = self._config_declarations()
        decl = declarations.get(f"{kind}:{group_name.lower()}")
        if decl is not None:
            return decl
        # BCMB evaluation groups are named *_bcmb2 while the grid uses *_bcmb
        if group_name.endswith("2"):
            return declarations.get(f"{kind}:{group_name[:-1].lower()}")
        return None

    def _claim_for(
        self, decl: GroupDecl | None, n_excluded: int | None = None
    ) -> ExclusionClaim | None:
        """Bind a README exclusion bullet to a family, grading the binding honestly."""
        if decl is None:
            return None
        target_method = _normalize(decl.method_alias)
        target_env = _normalize(decl.experiment_id or "")
        aliases = sorted(
            {_normalize(item.method_alias) for item in self._config_declarations().values()}
        )
        best: tuple[int, ExclusionClaim] | None = None
        for claim in self._project_readme_claims():
            method = _normalize(claim.raw_method)
            distance = _levenshtein(method, target_method)
            if method != target_method:
                if distance > 2 or method in aliases:
                    # distance 0 on some other alias means the bullet names a method
                    # that really exists; it is not a misspelling of this family's
                    continue
                near = [alias for alias in aliases if _levenshtein(method, alias) <= 2]
                closest = [alias for alias in near if _levenshtein(method, alias) == distance]
                if closest != [target_method]:
                    # The bullet either names another method that really exists, or it is
                    # equally close to two of them.  A seed count that matches this family's
                    # own excluded slots is the only remaining way to bind it, and it is weak.
                    if len(closest) < 2 or target_method not in closest:
                        continue
                    if n_excluded is None or claim.count != n_excluded:
                        continue
            env = _normalize(claim.raw_env)
            if not env or not (
                env == target_env or target_env.startswith(env) or env in target_env
            ):
                continue
            if best is None or distance < best[0]:
                best = (distance, claim)
        return best[1] if best else None

    # ----------------------------------------------------------- run histories
    def _result_dirs(self) -> list[Path]:
        root = self.results_root
        if root is None:
            return []
        return sorted(
            directory
            for directory in root.iterdir()
            if directory.is_dir()
            and not directory.name.startswith(SKIP_RESULT_DIRS)
            and any(child.is_dir() for child in directory.iterdir())
        )

    def _group_dirs(self) -> list[tuple[Path, str, str, bool]]:
        found: list[tuple[Path, str, str, bool]] = []
        for directory in self._result_dirs():
            is_eval = directory.name.endswith(EVAL_DIR_SUFFIX)
            for group in sorted(child for child in directory.iterdir() if child.is_dir()):
                found.append((group, directory.name, group.name, is_eval))
        return found

    def _slots(self, group: Path) -> Iterator[tuple[int, Path | None, Path | None, Path | None]]:
        """Enumerate fetch slots.  A slot exists if any of its three artifacts exists."""
        index = 0
        while True:
            plain = group / f"run_{index}.csv"
            bad = group / f"run_{index}.csv.bad"
            config = group / f"run_{index}_config.yml"
            if not plain.exists() and not bad.exists() and not config.exists():
                return
            yield (
                index,
                (plain if plain.exists() else None),
                (bad if bad.exists() else None),
                (config if config.exists() else None),
            )
            index += 1

    def _read_history(self, path: Path) -> HistoryData | None:
        try:
            with path.open(newline="", encoding="utf-8", errors="replace") as handle:
                rows = list(csv.reader(handle))
        except (OSError, csv.Error, UnicodeDecodeError):
            return None
        if len(rows) < 2:
            return None
        header = [name.strip() for name in rows[0]]
        body = [row for row in rows[1:] if any(cell.strip() for cell in row)]
        if not body:
            return None
        finals: dict[str, float] = {}
        last_step: int | None = None
        last_runtime: float | None = None
        for position, name in enumerate(header):
            values = [
                row[position] for row in body if len(row) > position and _is_float(row[position])
            ]
            if not values:
                continue
            if name == "_step":
                last_step = int(float(values[-1]))
            elif name == "_runtime":
                last_runtime = float(values[-1])
            elif name not in INFRA_COLUMNS:
                finals[name] = float(values[-1])
        return HistoryData(
            columns=header,
            rows=len(body),
            finals=finals,
            last_step=last_step,
            last_runtime=last_runtime,
            rel_path=relative(self.root, path),
            absolute_path=path,
        )

    def _histories(
        self, group: Path, dir_name: str, group_name: str
    ) -> dict[int, HistoryData | None]:
        key = (dir_name, group_name)
        cached = self._history_cache.get(key)
        if cached is not None:
            return cached
        data: dict[int, HistoryData | None] = {}
        for index, plain, bad, _config in self._slots(group):
            history = bad or plain
            data[index] = self._read_history(history) if history else None
        self._history_cache[key] = data
        return data

    # ------------------------------------------------------------- declarations
    def _call_for(self, dir_name: str, group_name: str, is_eval: bool) -> FetchCall | None:
        kind = "eval" if is_eval else "hyperopt"
        matches = [
            call
            for call in self._fetch_declarations()
            if call.folder == dir_name and call.kind == kind
        ]
        if not matches:
            return None
        with_group = [call for call in matches if group_name in call.groups]
        return (with_group or matches)[-1]

    @staticmethod
    def _observed_metric_columns(histories: dict[int, HistoryData | None]) -> list[str]:
        names: list[str] = []
        for data in histories.values():
            if not data:
                continue
            for name in data.columns:
                if name in INFRA_COLUMNS:
                    continue
                if name not in names:
                    names.append(name)
        return names

    def _primary_metric_name(
        self, call: FetchCall | None, histories: dict[int, HistoryData | None]
    ) -> str | None:
        observed = self._observed_metric_columns(histories)
        if call and call.metric in observed:
            return call.metric
        for name in observed:
            if name in PRIMARY_CANDIDATES:
                return name
        return observed[0] if observed else None

    # --------------------------------------------------------------- discovery
    def discover_families(self, root: Path) -> list[ExperimentFamily]:
        if self._families_cache is not None:
            return self._families_cache
        families: list[ExperimentFamily] = []
        for group_dir, dir_name, group_name, is_eval in self._group_dirs():
            family_id = f"{dir_name}/{group_name}"
            decl = self._decl_for(group_name, is_eval)
            call = self._call_for(dir_name, group_name, is_eval)
            histories = self._histories(group_dir, dir_name, group_name)
            primary = self._primary_metric_name(call, histories)
            observed = self._observed_metric_columns(histories)
            families.append(
                ExperimentFamily(
                    family_id=family_id,
                    name=group_name,
                    kind=FamilyKind.EVALUATION if is_eval else FamilyKind.HYPERPARAMETER_SEARCH,
                    result_dir=dir_name,
                    method=self._method_field(decl),
                    task=self._task_field(decl),
                    run_ids=[f"{family_id}#slot_{index}" for index in sorted(histories)],
                    declared_repetitions=self._declared_repetitions(decl),
                    membership_rule=self._membership_rule(call, is_eval),
                    primary_metric=primary,
                    secondary_metrics=[name for name in observed if name != primary],
                )
            )
        self._families_cache = families
        return families

    def discover_runs(self, root: Path) -> list[ExperimentRun]:
        if self._runs_cache is not None:
            return self._runs_cache
        runs: list[ExperimentRun] = []
        for group_dir, dir_name, group_name, is_eval in self._group_dirs():
            family_id = f"{dir_name}/{group_name}"
            decl = self._decl_for(group_name, is_eval)
            call = self._call_for(dir_name, group_name, is_eval)
            histories = self._histories(group_dir, dir_name, group_name)
            primary = self._primary_metric_name(call, histories)
            slots = list(self._slots(group_dir))
            claim = self._claim_for(decl, sum(1 for _, _, bad, _ in slots if bad is not None))
            for index, plain, bad, config in slots:
                runs.append(
                    self._build_run(
                        family_id=family_id,
                        index=index,
                        history_path=bad or plain,
                        is_bad=bad is not None,
                        config_path=config,
                        data=histories.get(index),
                        primary=primary,
                        decl=decl,
                        call=call,
                        claim=claim,
                        is_eval=is_eval,
                    )
                )
        self._runs_cache = runs
        return runs

    def _build_run(
        self,
        *,
        family_id: str,
        index: int,
        history_path: Path | None,
        is_bad: bool,
        config_path: Path | None,
        data: HistoryData | None,
        primary: str | None,
        decl: GroupDecl | None,
        call: FetchCall | None,
        claim: ExclusionClaim | None,
        is_eval: bool,
    ) -> ExperimentRun:
        history_rel = data.rel_path if data else None
        artifacts = [make_artifact_ref(self.root, history_path)] if history_path else []
        if config_path is not None:
            artifacts.append(make_artifact_ref(self.root, config_path))

        run = ExperimentRun(
            run_id=f"{family_id}#slot_{index}",
            family_id=family_id,
            result_slot_index=index,
            method=self._method_field(decl),
            task=self._task_field(decl),
            environment=self._task_field(decl),
            dataset=self._dataset_field(decl),
            dataset_version=ProvenanceField.unknown(
                note="no dataset version or checksum appears in any archived artifact"
            ),
            code_repository=ProvenanceField.of(
                "OlegArenz/gmmvi_reproducibility",
                ProvenanceStatus.SUPPORTED,
                self._src(
                    relative(self.root, self.repo_root / "README.rst"), key="repository reference"
                ),
                note="the repository that ships the artifacts; not proven to be the code that ran",
            ),
            code_commit=ProvenanceField.unknown(
                note="no commit sha of the code that produced these runs appears in any artifact"
            ),
            code_dirty=ProvenanceField.unknown(note="no dirty-state record exists"),
            tracker_run_id=ProvenanceField.unknown(
                note="run_{i} is the fetch slot, not the tracking id; no artifact records the id of this slot"
            ),
            repetition_index=ProvenanceField.unknown(
                note="the runner computes rep -> seed in memory and never persists the repetition index"
            ),
            parent_run_id=ProvenanceField.unknown(
                note="nothing in the artifacts links a rerun to the run it replaced"
            ),
            seed=self._seed_field(config_path),
            seed_derivation=ProvenanceField.unknown(note=_SEED_DERIVATION_NOTE[is_eval]),
            entrypoint=ProvenanceField.unknown(
                note="launch scripts are archived (run_exp3_*_eval*.sh) but none records which script ran this slot"
            ),
            command=ProvenanceField.unknown(note="no command line was archived"),
            start_time=ProvenanceField.unknown(
                note="only a per-row _runtime offset was logged, no wall-clock start"
            ),
            end_time=ProvenanceField.unknown(note="no wall-clock end was archived"),
            compute_budget=ProvenanceField.unknown(
                note="wall-clock limit and core count were injected by the launcher scripts and never logged per run"
            ),
            history_rows=self._rows_field(data, history_rel),
            runtime_seconds=self._runtime_field(data, history_rel),
            artifacts=artifacts,
        )

        if config_path is not None:
            self._attach_config(run, config_path)

        if data is None:
            run.status = RunStatus.ABSENT_NO_ARTIFACT
            run.included_in_aggregation = ProvenanceField.unknown(
                note="config-only slot: without a history file it cannot have been aggregated"
            )
            return run

        self._attach_metrics(run, data, primary)

        run.included_in_aggregation = ProvenanceField.of(
            not is_bad,
            ProvenanceStatus.CONFIRMED,
            self._src(
                history_rel or "",
                key="filename suffix .csv vs .csv.bad",
                line=call.line if call else None,
            ),
            note="machine-readable membership marker written by the fetch script",
        )
        primary_final = data.finals.get(primary) if primary else None
        if is_bad:
            run.status = (
                RunStatus.COMPLETED_EXCLUDED if primary_final is not None else RunStatus.UNKNOWN
            )
            run.exclusion_category = self._exclusion_category(claim)
            run.exclusion_reason = self._exclusion_reason(claim, history_rel)
            run.exclusion_evidence = self._exclusion_evidence(call, decl, claim, history_rel)
        else:
            run.status = (
                RunStatus.COMPLETED_INCLUDED if primary_final is not None else RunStatus.UNKNOWN
            )
            run.exclusion_category = ProvenanceField.of(
                ExclusionCategory.NONE,
                ProvenanceStatus.CONFIRMED,
                self._src(history_rel or "", key="no .csv.bad suffix"),
            )
        if not is_eval:
            run.included_in_aggregation = ProvenanceField.unknown(
                note="hyperparameter search runs are not aggregated into a published table"
            )
        return run

    def _rows_field(self, data: HistoryData | None, rel: str | None) -> ProvenanceField[int]:
        if data is None or rel is None:
            return ProvenanceField.unknown(note="no readable history file for this slot")
        return ProvenanceField.of(
            data.rows,
            ProvenanceStatus.CONFIRMED,
            self._src(rel, key="data rows"),
            note="rows of the archived history CSV",
        )

    def _runtime_field(self, data: HistoryData | None, rel: str | None) -> ProvenanceField[float]:
        if data is None or rel is None:
            return ProvenanceField.unknown(note="no readable history file for this slot")
        if data.last_runtime is None:
            return ProvenanceField.unknown(note="history CSV has no numeric _runtime column")
        return ProvenanceField.of(
            data.last_runtime,
            ProvenanceStatus.CONFIRMED,
            self._src(rel, key="_runtime"),
            note="last logged _runtime",
        )

    def _attach_metrics(self, run: ExperimentRun, data: HistoryData, primary: str | None) -> None:
        for name, value in data.finals.items():
            is_primary = name == primary
            direction, status, source, note = self._direction_for(name, is_primary)
            direction_field: ProvenanceField[MetricDirection]
            if status is ProvenanceStatus.UNKNOWN or direction is MetricDirection.UNKNOWN:
                direction_field = ProvenanceField.unknown(note=note)
            else:
                direction_field = ProvenanceField.of(direction, status, source, note)
            run.metrics.append(
                MetricRecord(
                    name=name,
                    value=ProvenanceField.of(
                        value,
                        ProvenanceStatus.CONFIRMED,
                        self._src(data.rel_path, key=f"last row of '{name}'"),
                        note="last logged value, which is the quantity the project aggregates",
                    ),
                    step=(
                        ProvenanceField.of(
                            data.last_step,
                            ProvenanceStatus.CONFIRMED,
                            self._src(data.rel_path, key="_step"),
                        )
                        if data.last_step is not None
                        else ProvenanceField.unknown(note="history CSV has no _step column")
                    ),
                    epoch=ProvenanceField.unknown(note="no epoch column is logged"),
                    direction=direction_field,
                    source=self._src(data.rel_path, key=name),
                    status=ProvenanceStatus.CONFIRMED,
                )
            )

    def _direction_for(
        self, name: str, is_primary: bool
    ) -> tuple[MetricDirection, ProvenanceStatus, SourceRef | None, str | None]:
        directions = self._directions or {}
        if name in directions:
            direction, source = directions[name]
            return direction, ProvenanceStatus.CONFIRMED, source, None
        if is_primary and "__primary__" in directions:
            direction, source = directions["__primary__"]
            return (
                direction,
                ProvenanceStatus.CONFIRMED,
                source,
                "primary metric uses latex_format's default larger_is_better=False",
            )
        return (
            MetricDirection.UNKNOWN,
            ProvenanceStatus.UNKNOWN,
            None,
            "no direction declaration covers this column",
        )

    def _method_field(self, decl: GroupDecl | None) -> ProvenanceField[str]:
        if decl is None:
            return ProvenanceField.unknown(note="group name matches no cw2 config document")
        return ProvenanceField.of(
            decl.algorithm_id or decl.method_alias,
            ProvenanceStatus.CONFIRMED,
            self._src(decl.config_path, key="DEFAULT.algorithm_id"),
            note=f"declared by config doc '{decl.doc_name}' (wandb.group={decl.group})",
        )

    def _task_field(self, decl: GroupDecl | None) -> ProvenanceField[str]:
        if decl is None or not decl.experiment_id:
            return ProvenanceField.unknown(note="no environment document matches this group")
        return ProvenanceField.of(
            str(decl.experiment_id),
            ProvenanceStatus.CONFIRMED,
            self._src(decl.config_path, key="experiment_id"),
        )

    def _dataset_field(self, decl: GroupDecl | None) -> ProvenanceField[str]:
        if decl is None or not decl.experiment_id:
            return ProvenanceField.unknown(note="no environment document matches this group")
        return ProvenanceField.of(
            str(decl.experiment_id),
            ProvenanceStatus.SUPPORTED,
            self._src(decl.config_path, key="experiment_id"),
            note="the experiment id is what the loader selects on; the data itself carries no version",
        )

    def _declared_repetitions(self, decl: GroupDecl | None) -> ProvenanceField[int]:
        if decl is None:
            return ProvenanceField.unknown(note="no cw2 config document for this group")
        if not isinstance(decl.repetitions, int):
            return ProvenanceField.unknown(note="matching config declares no DEFAULT.repetitions")
        return ProvenanceField.of(
            decl.repetitions,
            ProvenanceStatus.CONFIRMED,
            self._src(decl.config_path, key="DEFAULT.repetitions"),
            note="declared repetition count of the launch protocol, not per-run evidence",
        )

    def _membership_rule(self, call: FetchCall | None, is_eval: bool) -> ProvenanceField[str]:
        if not is_eval:
            return ProvenanceField.unknown(
                note="hyperparameter search has no published aggregation"
            )
        path = call.source_path if call else relative(self.root, self._fetch_path())
        return ProvenanceField.of(
            "runs whose history was written without the .csv.bad suffix "
            "(the fetch script writes .bad for ids passed as bad_run_ids)",
            ProvenanceStatus.CONFIRMED,
            self._src(path, key="fetch_exp3_eval", line=call.line if call else None),
        )

    def _seed_field(self, config_path: Path | None) -> ProvenanceField[int]:
        """Only a recorded seed key can produce a value; the run slot never becomes a seed."""
        if config_path is None:
            return ProvenanceField.unknown(note="no archived config for this slot")
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, yaml.YAMLError) as exc:
            return ProvenanceField.unknown(
                note=f"archived config unreadable ({type(exc).__name__})"
            )
        flat = self._flatten(self._unwrap_config(raw) if isinstance(raw, dict) else {})
        keys = [key for key in flat if "seed" in key.lower()]
        rel = relative(self.root, config_path)
        if not keys:
            return ProvenanceField.unknown(
                note="archived config contains no seed key; the runner derived seed = start_seed + rep in memory"
            )
        values = {
            flat[key]
            for key in keys
            if isinstance(flat[key], int) and not isinstance(flat[key], bool)
        }
        if len(values) > 1:
            return ProvenanceField(
                value=None,
                status=ProvenanceStatus.CONFLICTING,
                source=SourceRef(
                    path=rel, key=", ".join(sorted(keys)), note="the archived configs disagree"
                ),
            )
        if values:
            return ProvenanceField.of(
                int(next(iter(values))), ProvenanceStatus.CONFIRMED, self._src(rel, key=keys[0])
            )
        return ProvenanceField.unknown(note=f"seed key '{keys[0]}' is present but not an integer")

    def _attach_config(self, run: ExperimentRun, config_path: Path) -> None:
        rel = relative(self.root, config_path)
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, yaml.YAMLError) as exc:
            run.config_source = ProvenanceField.unknown(
                note=f"archived config unreadable ({type(exc).__name__})"
            )
            return
        unwrapped = self._unwrap_config(raw) if isinstance(raw, dict) else {}
        run.config_source = ProvenanceField.of(
            rel,
            ProvenanceStatus.CONFIRMED,
            self._src(rel),
            note="resolved config captured per run by the fetch script",
        )
        run.resolved_config = ProvenanceField.of(
            dict(unwrapped),
            ProvenanceStatus.CONFIRMED,
            self._src(rel),
            note="only what the tracking service logged; package defaults stay invisible",
        )
        run.unrecorded_effective_parameters = [
            "seed",
            "start_seed",
            "wall-clock budget",
            "iterations actually run",
        ]

    def _exclusion_category(
        self, claim: ExclusionClaim | None
    ) -> ProvenanceField[ExclusionCategory]:
        if claim is None:
            return ProvenanceField.unknown(
                note="the .bad marker proves exclusion but not its category"
            )
        return ProvenanceField.of(
            claim.category,
            ProvenanceStatus.SUPPORTED,
            self._src(claim.source_path, key="exclusion statement", line=claim.line),
            note="stated in project prose, so it is not machine-readable evidence",
        )

    def _exclusion_reason(
        self, claim: ExclusionClaim | None, history_rel: str | None
    ) -> ProvenanceField[str]:
        if claim is None:
            return ProvenanceField.unknown(
                note="no machine-readable exclusion reason; the project prose states none for this family"
            )
        return ProvenanceField.of(
            claim.reason,
            ProvenanceStatus.SUPPORTED,
            self._src(claim.source_path, key="exclusion statement", line=claim.line),
            note="prose evidence only, so it cannot be CONFIRMED machine-readable",
        )

    def _exclusion_evidence(
        self,
        call: FetchCall | None,
        decl: GroupDecl | None,
        claim: ExclusionClaim | None,
        history_rel: str | None,
    ) -> ProvenanceField[str]:
        pieces: list[str] = [
            f"membership marker: {history_rel}" if history_rel else "membership marker: missing"
        ]
        if call and call.bad_run_ids:
            listed = len(call.bad_run_ids)
            alias = decl.method_alias if decl else None
            tagged = (
                len(
                    [
                        rid
                        for rid, token in call.bad_id_comments.items()
                        if alias and _normalize(token) == _normalize(alias)
                    ]
                )
                if alias
                else 0
            )
            pieces.append(
                f"{call.source_path}:{call.line} lists {listed} bad_run_ids for '{call.folder}'"
                + (f", {tagged} commented '{alias}'" if tagged else "")
            )
            pieces.append("no artifact binds a listed id to this slot")
        else:
            pieces.append("the fetch declaration for this folder lists no bad_run_ids")
        if claim:
            pieces.append(
                f"{claim.source_path}:{claim.line} states {claim.raw_method} on {claim.raw_env}: {claim.count}"
            )
        source_line = call.line if call and call.bad_run_ids else (claim.line if claim else None)
        source_path = (
            call.source_path
            if call and call.bad_run_ids
            else (claim.source_path if claim else None)
        )
        if source_path is None:
            return ProvenanceField.unknown(note="no artifact lists this exclusion")
        return ProvenanceField.of(
            "; ".join(pieces),
            ProvenanceStatus.SUPPORTED,
            self._src(source_path, key="bad_run_ids / exclusion statement", line=source_line),
            note="the ids sit in commented-out calls, so they are documentation rather than executed code",
        )

    # ----------------------------------------------------------- aggregations
    def discover_aggregations(self, root: Path) -> list[AggregationRecord]:
        reported = self._reported_cells()
        runs_by_family: dict[str, list[ExperimentRun]] = {}
        for run in self.discover_runs(root):
            runs_by_family.setdefault(run.family_id, []).append(run)
        records: list[AggregationRecord] = []
        for family in self.discover_families(root):
            if family.kind is not FamilyKind.EVALUATION or not family.primary_metric:
                continue
            runs = runs_by_family.get(family.family_id, [])
            included = [run for run in runs if run.included_in_aggregation.value is True]
            excluded = [run for run in runs if run.included_in_aggregation.value is False]
            with_history = [run for run in runs if run.metrics]
            records.append(
                self._aggregation(
                    family, family.primary_metric, included, excluded, "included", reported
                )
            )
            if excluded:
                records.append(
                    self._aggregation(
                        family, family.primary_metric, with_history, [], "all_completed", reported
                    )
                )
            for name in family.secondary_metrics:
                members = [run for run in included if run.metric(name)]
                if members:
                    records.append(
                        self._aggregation(family, name, members, [], "included", reported)
                    )
        return records

    def _aggregation(
        self,
        family: ExperimentFamily,
        metric_name: str,
        members: Sequence[ExperimentRun],
        excluded: Sequence[ExperimentRun],
        variant: str,
        reported: dict[tuple[str, str, str], dict[str, Any]],
    ) -> AggregationRecord:
        member_ids = [run.run_id for run in members]
        transform = "negate" if metric_name in NEGATED_METRICS else "identity"
        membership = family.membership_rule
        if variant == "all_completed":
            membership = ProvenanceField.of(
                "every slot with a readable history CSV, the declared exclusions included again",
                ProvenanceStatus.INFERRED,
                family.membership_rule.source,
                note="a counterfactual membership, built to measure how far the declared exclusions move the number",
            )
        elif metric_name in family.secondary_metrics:
            membership = ProvenanceField.of(
                "per-run value is np.sum over the declared secondary columns, then the same included set",
                ProvenanceStatus.CONFIRMED,
                self._src(relative(self.root, self._fetch_path()), key="np.sum(this_secondaries)"),
            )
        record = AggregationRecord(
            aggregation_id=f"{family.family_id}/{metric_name}@{variant}",
            family_id=family.family_id,
            metric_name=metric_name,
            statistic="mean",
            transform=transform,
            member_run_ids=member_ids,
            excluded_run_ids=[run.run_id for run in excluded],
            n=len(member_ids),
            std_ddof=0,
            display_multiplier=3.0,
            membership_rule=membership,
        )
        cell = reported.get((family.family_id, metric_name, variant))
        if cell is not None:
            self._attach_reported(record, cell)
        return record

    def _reported_cells(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        """Reported table cells, only when the caller points at a published-summary file."""
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
            # Rounding half-width of the printed digits, plus slack so that a value sitting
            # exactly on a rounding boundary is not reported as a mismatch.
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

    def code_repository(self) -> ArtifactRef:
        path = self._fetch_path()
        if path.is_file():
            return make_artifact_ref(self.root, path)
        return ArtifactRef(path=str(FETCH_SCRIPT), artifact_type=ArtifactType.SCRIPT)

    @property
    def notes(self) -> list[str]:
        return sorted(set(self._notes))


def spec() -> AdapterSpec:
    return AdapterSpec(
        name="gmmvi-exp3",
        description=GMMVIAdapter(Path(".")).describe(),
        factory=GMMVIAdapter,
        options=("repo_root", "results_root", "reported_table"),
    )


def install() -> None:
    register(spec())


__all__ = ["ExclusionClaim", "FetchCall", "GMMVIAdapter", "GroupDecl", "install", "spec"]
