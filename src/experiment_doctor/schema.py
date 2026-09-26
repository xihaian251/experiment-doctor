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

from pydantic import BaseModel, Field, model_validator

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef


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


class ArtifactRef(BaseModel):
    """Provenance-relevant artifact metadata only; no hashing of large files."""

    path: str
    artifact_type: ArtifactType = ArtifactType.UNKNOWN
    size: int | None = None
    mtime: float | None = None
    sha256: str | None = None

    @property
    def is_hashed(self) -> bool:
        return self.sha256 is not None


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

    v0.1 convention: ``recomputed_spread = display_multiplier * std / sqrt(N)``.
    GMMVI's tables therefore use ``std_ddof=0`` and ``display_multiplier=3``
    (3x standard error), which is neither ``std`` nor a 95% CI.
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
    display_multiplier: float = 1.0
    reported_value: float | None = None
    reported_spread: float | None = None
    recomputed_value: float | None = None
    recomputed_spread: float | None = None
    tolerance: float = 1e-9
    spread_tolerance: float = 1e-9
    comparison_status: ComparisonStatus = ComparisonStatus.UNKNOWN
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
