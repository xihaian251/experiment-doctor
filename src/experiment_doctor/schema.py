"""Experiment Doctor v0 schema.

Frozen from the Phase 0 forensic reconstruction
(``phase0-gmmvi/evidence/experiment_run_v0_schema.json``): the field set below is
that document, minimally engineered into Pydantic models.  Nothing here invents
fields the evidence did not ask for, and nothing here pretends a reconstructed
value was recorded by the project that produced it.

Constraint carried over from Phase 0 (A): ``run_id`` != ``seed`` !=
``repetition_index`` != ``family_id``.  They are four separate fields on four
separate objects and must never be collapsed.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from experiment_doctor.provenance import (
    ProvenanceField,
    ProvenanceStatus,
    SourceRef,
    unknown_field,
)


class RunStatus(str, Enum):
    """Phase 0 ``status_vocabulary``."""

    COMPLETED_INCLUDED = "COMPLETED_INCLUDED"
    COMPLETED_EXCLUDED = "COMPLETED_EXCLUDED"
    FAILED_OOM = "FAILED_OOM"
    FAILED_OTHER = "FAILED_OTHER"
    TRUNCATED_TIME_LIMIT = "TRUNCATED_TIME_LIMIT"
    ABSENT_NO_ARTIFACT = "ABSENT_NO_ARTIFACT"
    UNKNOWN = "UNKNOWN"


class TerminationCause(str, Enum):
    """Phase 0 ``execution.termination_cause`` enum.

    A "final metric" can be the metric at an iteration cap, at a wall-clock
    deadline, or at convergence; those are not the same quantity.
    """

    ITERATION_CAP = "iteration_cap"
    TIME_LIMIT = "time_limit"
    CRASH = "crash"
    OOM = "oom"
    CONVERGED = "converged"
    UNKNOWN = "unknown"


class MetricDirection(str, Enum):
    MINIMIZE = "MINIMIZE"
    MAXIMIZE = "MAXIMIZE"
    UNKNOWN = "UNKNOWN"


class ArtifactType(str, Enum):
    CONFIG = "CONFIG"
    LOG = "LOG"
    METRIC = "METRIC"
    CHECKPOINT = "CHECKPOINT"
    SUMMARY = "SUMMARY"
    TABLE = "TABLE"
    SCRIPT = "SCRIPT"
    ENVIRONMENT = "ENVIRONMENT"
    UNKNOWN = "UNKNOWN"


class ExclusionCategory(str, Enum):
    """Phase 0 ``selection.exclusion_category`` enum."""

    COMPLETED_OUTLIER = "completed_outlier"
    OOM = "oom"
    OTHER = "other"
    NONE = "none"
    UNKNOWN = "unknown"


class ComparisonStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


class SpreadBasis(str, Enum):
    """What a project's published ``±`` is, per its own aggregation code.

    v0.1's core recomputation originally assumed every project divides by
    ``sqrt(N)``.  Real projects do not all do that: some publish the spread of
    the runs themselves.  The basis is declared, never guessed.
    """

    STANDARD_ERROR = "standard_error"
    STANDARD_DEVIATION = "standard_deviation"


class SpreadSemantics(str, Enum):
    """What a ``±`` actually is, on either side of the ED008 comparison.

    ``SpreadBasis`` says how the recomputation divides; this says what a number
    *means*.  A project can be internally consistent while its prose calls the
    same quantity something else, so the implemented side and the documented side
    are recorded separately and each carries its own evidence.
    """

    STANDARD_DEVIATION = "standard_deviation"
    STANDARD_ERROR = "standard_error"
    SCALED_STANDARD_ERROR = "scaled_standard_error"
    CONFIDENCE_INTERVAL_HALF_WIDTH = "confidence_interval_half_width"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class SelectionPolicy(str, Enum):
    """Which observation of a run a reported metric stands for (ED005's vocabulary).

    Best and last are different quantities whenever the metric is tracked to a
    maximum; neither is a proxy for the other and a project is free to publish
    either one.
    """

    BEST = "best"
    LAST = "last"
    SPECIFIC_STEP = "specific_step"
    OTHER = "other"
    UNKNOWN = "unknown"


class IdentityStatus(str, Enum):
    """Run-identity check outcome.  Deliberately not PASS/FAIL."""

    CONSISTENT = "CONSISTENT"
    MIXED_CONFIG = "MIXED_CONFIG"
    UNKNOWN = "UNKNOWN"


class FamilyKind(str, Enum):
    EVALUATION = "evaluation"
    HYPERPARAMETER_SEARCH = "hyperparameter_search"
    UNKNOWN = "unknown"


class FindingCategory(str, Enum):
    PROVENANCE_GAP = "PROVENANCE_GAP"
    SEED_INTEGRITY = "SEED_INTEGRITY"
    RUN_IDENTITY = "RUN_IDENTITY"
    AGGREGATION_MEMBERSHIP = "AGGREGATION_MEMBERSHIP"
    AGGREGATION_MISMATCH = "AGGREGATION_MISMATCH"
    METRIC_PROVENANCE = "METRIC_PROVENANCE"


class Severity(str, Enum):
    """Ordering key only.  v0.1 emits no verdict, so there is no CRITICAL/BLOCKING."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ArtifactRole(str, Enum):
    """What an artifact is *for*, declared rather than guessed (P1-b).

    ``artifact_type`` says what a file is; the role says what provenance question
    it answers.  ``DECLARED_ENVIRONMENT`` is deliberately separated from every
    runtime role so a dependency file can never be cited as something the run
    executed with.  Closed enum: free strings are rejected by validation.
    """

    SOURCE_CODE = "SOURCE_CODE"
    CONFIG = "CONFIG"
    LOG = "LOG"
    CHECKPOINT = "CHECKPOINT"
    DATASET = "DATASET"
    DECLARED_ENVIRONMENT = "DECLARED_ENVIRONMENT"
    RESULT = "RESULT"
    REPORT = "REPORT"


class DeclaredEnvironmentType(str, Enum):
    """Which dialect a repository-level dependency declaration uses."""

    REQUIREMENTS = "requirements"
    ENVIRONMENT_YAML = "environment_yaml"
    CONDA_YAML = "conda_yaml"
    DOCKERFILE = "dockerfile"
    SLURM_TEMPLATE = "slurm_template"
    UNKNOWN = "unknown"


class ArtifactRef(BaseModel):
    """Provenance-relevant artifact metadata only; no hashing of large files."""

    path: str
    artifact_type: ArtifactType = ArtifactType.UNKNOWN
    #: None means no component has classified this artifact's role yet, which is
    #: what every pre-refinement scan record means.
    artifact_role: ArtifactRole | None = None
    size: int | None = None
    mtime: float | None = None
    sha256: str | None = None

    @property
    def is_hashed(self) -> bool:
        return self.sha256 is not None


class RuntimeEnvironment(BaseModel):
    """What the run's own artifacts recorded about the software and machine it executed on.

    This is the runtime side of the P1-a split: the legacy ``environment`` scalar
    could not express "a declaration exists but the runtime is unknown", so the
    two concepts now have separate types.  Every aspect carries its own evidence
    grade, and no value may be copied in here from a repository declaration —
    declared intent belongs to :class:`DeclaredEnvironment` and is never upgraded.
    """

    python_version: ProvenanceField[str] = Field(default_factory=unknown_field)
    framework_versions: ProvenanceField[dict[str, str]] = Field(default_factory=unknown_field)
    cuda_version: ProvenanceField[str] = Field(default_factory=unknown_field)
    hardware: ProvenanceField[str] = Field(default_factory=unknown_field)
    os: ProvenanceField[str] = Field(default_factory=unknown_field)
    source_artifacts: list[SourceRef] = Field(default_factory=list)

    def evidenced_fields(self) -> dict[str, ProvenanceField[Any]]:
        """The aspects some artifact actually states, keyed by field name."""
        aspects: dict[str, ProvenanceField[Any]] = {}
        for name in ("python_version", "framework_versions", "cuda_version", "hardware", "os"):
            field: ProvenanceField[Any] = getattr(self, name)
            if field.status in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED):
                aspects[name] = field
        return aspects

    def is_evidenced(self) -> bool:
        return bool(self.evidenced_fields())

    def version_map(self) -> dict[str, str]:
        """Flat lower-cased package-to-version view for the declared-vs-runtime comparison.

        Only version-bearing aspects enter: hardware and OS names are not pins a
        dependency file could contradict, so they must not manufacture a conflict.
        """
        versions: dict[str, str] = {}
        for name, field in self.evidenced_fields().items():
            if name == "framework_versions" and isinstance(field.value, dict):
                versions.update(
                    {
                        str(key).strip().lower(): str(value).strip().lower()
                        for key, value in field.value.items()
                    }
                )
            elif name == "python_version" and field.value is not None:
                versions["python"] = str(field.value).strip().lower()
            elif name == "cuda_version" and field.value is not None:
                versions["cuda"] = str(field.value).strip().lower()
        return versions


class DeclaredEnvironment(BaseModel):
    """One repository artifact stating the dependencies its author intended.

    A declaration is evidence about a file, never about an execution: nothing in
    here may be promoted into a :class:`RuntimeEnvironment`, which is why ED010
    can report "declared exists / runtime unknown" without contradiction.
    """

    artifact_id: str
    artifact_type: DeclaredEnvironmentType = DeclaredEnvironmentType.UNKNOWN
    source_path: str
    declared_dependencies: ProvenanceField[dict[str, str]] = Field(default_factory=unknown_field)
    provenance: ProvenanceStatus = ProvenanceStatus.SUPPORTED

    def version_map(self) -> dict[str, str]:
        """The pins this declaration states, or an empty map when it names none."""
        if self.declared_dependencies.status not in (
            ProvenanceStatus.CONFIRMED,
            ProvenanceStatus.SUPPORTED,
        ):
            return {}
        value = self.declared_dependencies.value or {}
        return {str(key).strip().lower(): str(item).strip().lower() for key, item in value.items()}


class EnvironmentRelationship(str, Enum):
    """How one run's runtime record and the repository's declaration stand together."""

    MATCHED = "MATCHED"
    CONFLICTING = "CONFLICTING"
    ONLY_DECLARED = "ONLY_DECLARED"
    ONLY_RUNTIME = "ONLY_RUNTIME"
    UNKNOWN = "UNKNOWN"


class RunEnvironmentBinding(BaseModel):
    """The light relation between one run and the environment evidence around it.

    Built from evidence, never from assumption: ``MATCHED`` appears only when
    both sides state a version for the same package and those versions agree;
    disjoint facts stay ``UNKNOWN`` rather than being read as agreement.
    """

    run_id: str
    runtime_environment: RuntimeEnvironment | None = None
    declared_environment: DeclaredEnvironment | None = None
    relationship_status: EnvironmentRelationship = EnvironmentRelationship.UNKNOWN

    @classmethod
    def build(
        cls,
        run_id: str,
        runtime_environment: RuntimeEnvironment | None,
        declared_environment: DeclaredEnvironment | None,
    ) -> RunEnvironmentBinding:
        return cls(
            run_id=run_id,
            runtime_environment=runtime_environment,
            declared_environment=declared_environment,
            relationship_status=relate_environment_evidence(
                runtime_environment, declared_environment
            ),
        )


def relate_environment_evidence(
    runtime: RuntimeEnvironment | None,
    declared: DeclaredEnvironment | None,
) -> EnvironmentRelationship:
    if runtime is None and declared is None:
        return EnvironmentRelationship.UNKNOWN
    if runtime is None:
        return EnvironmentRelationship.ONLY_DECLARED
    if declared is None:
        return EnvironmentRelationship.ONLY_RUNTIME
    runtime_versions = runtime.version_map()
    declared_versions = declared.version_map()
    shared = sorted(runtime_versions.keys() & declared_versions.keys())
    if not shared:
        return EnvironmentRelationship.UNKNOWN
    if any(runtime_versions[name] != declared_versions[name] for name in shared):
        return EnvironmentRelationship.CONFLICTING
    return EnvironmentRelationship.MATCHED


class MetricRecord(BaseModel):
    """One metric observation for a run, on the reported basis.

    ``value`` is the last logged value of that metric for the run (the quantity
    projects aggregate), not the whole history.  ``direction`` must be evidenced:
    a name-based heuristic may only ever be ``INFERRED``.
    """

    name: str
    value: ProvenanceField[float] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    step: ProvenanceField[int] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    epoch: ProvenanceField[int] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    direction: ProvenanceField[MetricDirection] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    source: SourceRef | None = None
    status: ProvenanceStatus = ProvenanceStatus.UNKNOWN

    @model_validator(mode="after")
    def _no_confirmed_guess(self) -> MetricRecord:
        if self.direction.status is ProvenanceStatus.CONFIRMED and self.direction.source is None:
            raise ValueError("CONFIRMED metric direction requires a source")
        if (
            self.direction.status is ProvenanceStatus.CONFIRMED
            and self.direction.value is MetricDirection.UNKNOWN
        ):
            raise ValueError("a CONFIRMED direction cannot be UNKNOWN")
        return self


class ExperimentRun(BaseModel):
    """One executed (or intended) run of one experiment family."""

    run_id: str
    family_id: str

    # --- identity (Phase 0 constraint A) -----------------------------------
    tracker_run_id: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    result_slot_index: int | None = None
    repetition_index: ProvenanceField[int] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    parent_run_id: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )

    # --- method / task / data ----------------------------------------------
    method: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    task: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    dataset: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    dataset_version: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )

    # --- randomness ---------------------------------------------------------
    seed: ProvenanceField[int] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    seed_derivation: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )

    # --- code ---------------------------------------------------------------
    code_repository: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    code_commit: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    code_dirty: ProvenanceField[bool] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )

    # --- config --------------------------------------------------------------
    config_source: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    resolved_config: ProvenanceField[dict[str, object]] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    unrecorded_effective_parameters: list[str] = Field(default_factory=list)

    # --- execution -----------------------------------------------------------
    entrypoint: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    command: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    start_time: ProvenanceField[float] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    end_time: ProvenanceField[float] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    status: RunStatus = RunStatus.UNKNOWN
    termination_cause: ProvenanceField[TerminationCause] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    environment: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    #: The structured runtime-software slot (P1-a).  The legacy ``environment``
    #: scalar stays exactly as it was — a project may keep using it for the task
    #: environment — and this slot is where a run-local software record belongs.
    runtime_environment: RuntimeEnvironment | None = None
    compute_budget: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )

    # --- needed to evidence the fields above ---------------------------------
    history_rows: ProvenanceField[int] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    runtime_seconds: ProvenanceField[float] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )

    artifacts: list[ArtifactRef] = Field(default_factory=list)
    metrics: list[MetricRecord] = Field(default_factory=list)

    # --- aggregation membership (Phase 0 constraint D) -----------------------
    included_in_aggregation: ProvenanceField[bool] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    exclusion_category: ProvenanceField[ExclusionCategory] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    exclusion_reason: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    exclusion_evidence: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )

    def metric(self, name: str) -> MetricRecord | None:
        for record in self.metrics:
            if record.name == name:
                return record
        return None


class ExperimentFamily(BaseModel):
    """A group of runs sharing one experiment identity (e.g. one method on one environment)."""

    family_id: str
    name: str
    kind: FamilyKind = FamilyKind.UNKNOWN
    result_dir: str | None = None
    method: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    task: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    run_ids: list[str] = Field(default_factory=list)
    declared_repetitions: ProvenanceField[int] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    membership_rule: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    primary_metric: str | None = None
    secondary_metrics: list[str] = Field(default_factory=list)


class AggregationRecord(BaseModel):
    """One published/aggregated number, and the recomputation of it.

    v0.1 convention: ``spread_basis`` declares whether the project's ``±`` is a
    standard error (``display_multiplier * std / sqrt(N)``, the default) or the
    standard deviation itself (``display_multiplier * std``).  ``std_ddof`` picks
    the estimator.  GMMVI's tables use ``standard_error`` with ``std_ddof=0`` and
    ``display_multiplier=3`` (3x standard error), which is neither ``std`` nor a
    95% CI; TorchSSL's use ``standard_deviation`` with ``std_ddof=0`` and
    ``display_multiplier=1``, whatever the prose around the table calls them.
    ``statistic`` declares what the central value is; v0.1 only recomputes
    ``"mean"``, anything else stays ``UNKNOWN`` rather than being assumed.
    """

    aggregation_id: str
    family_id: str
    metric_name: str
    statistic: str = "mean"
    transform: str = "identity"
    member_run_ids: list[str] = Field(default_factory=list)
    excluded_run_ids: list[str] = Field(default_factory=list)
    n: int = 0
    values: list[float] = Field(default_factory=list)
    mean: float | None = None
    std: float | None = None
    std_ddof: int = 0
    spread_basis: SpreadBasis = SpreadBasis.STANDARD_ERROR
    display_multiplier: float = 1.0
    reported_value: float | None = None
    reported_spread: float | None = None
    recomputed_value: float | None = None
    recomputed_spread: float | None = None
    tolerance: float = 1e-9
    spread_tolerance: float = 1e-9
    comparison_status: ComparisonStatus = ComparisonStatus.UNKNOWN
    #: What the project's own aggregation code computes the ``±`` to be, evidenced
    #: by the line that computes it.  UNKNOWN means the formula is not recoverable.
    implemented_spread: ProvenanceField[SpreadSemantics] = Field(default_factory=unknown_field)
    #: What the project's prose says the ``±`` is.  UNKNOWN means it never says.
    documented_spread: ProvenanceField[SpreadSemantics] = Field(default_factory=unknown_field)
    #: Which observation of a run the code aggregates (ED005's implemented side).
    implemented_selection: ProvenanceField[SelectionPolicy] = Field(default_factory=unknown_field)
    #: Which observation of a run the prose claims it published (ED005's documented side).
    documented_selection: ProvenanceField[SelectionPolicy] = Field(default_factory=unknown_field)
    membership_rule: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    reported_source: SourceRef | None = None

    @property
    def has_reported(self) -> bool:
        return self.reported_value is not None

    @property
    def variant(self) -> str:
        """Which membership this record represents, from its id suffix."""
        return self.aggregation_id.rsplit("@", 1)[1] if "@" in self.aggregation_id else "included"


class Finding(BaseModel):
    """One audit observation.  No verdicts, no codes, no composite score."""

    category: FindingCategory
    title: str
    severity: Severity = Severity.INFO
    entity_type: str = "project"
    entity_id: str | None = None
    evidence: list[str] = Field(default_factory=list)
    recommendation: str | None = None


class ExperimentProject(BaseModel):
    """Scan result: everything discovered about one project directory."""

    root: str
    project_id: str
    adapter: str
    code_repository: ProvenanceField[str] = Field(
        default_factory=lambda: ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN)
    )
    families: list[ExperimentFamily] = Field(default_factory=list)
    runs: list[ExperimentRun] = Field(default_factory=list)
    aggregations: list[AggregationRecord] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    #: Repository-level dependency declarations registered as provenance (P1-b).
    #: Empty for every pre-refinement scan; declarations still count from the
    #: artifact inventory, so registering them here only adds detail, never status.
    declared_environments: list[DeclaredEnvironment] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def family(self, family_id: str) -> ExperimentFamily | None:
        for item in self.families:
            if item.family_id == family_id:
                return item
        return None

    def runs_of(self, family_id: str) -> list[ExperimentRun]:
        return [run for run in self.runs if run.family_id == family_id]

    def run(self, run_id: str) -> ExperimentRun | None:
        for item in self.runs:
            if item.run_id == run_id:
                return item
        return None
