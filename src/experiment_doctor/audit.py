"""The five v0.1 audit checks and field-level provenance coverage.

v0.1 deliberately checks only:

A. run identity            B. seed integrity           C. metric provenance
D. aggregation membership  E. aggregation recomputation

There is no verdict, no significance test and no composite trust score.  Status
vocabulary is descriptive (CONSISTENT / MIXED_CONFIG / MATCH / MISMATCH / UNKNOWN),
never PASS/FAIL.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from experiment_doctor.provenance import EvidenceCounts, ProvenanceField, ProvenanceStatus
from experiment_doctor.schema import (
    AggregationRecord,
    ComparisonStatus,
    ExperimentFamily,
    ExperimentProject,
    ExperimentRun,
    Finding,
    FindingCategory,
    IdentityStatus,
    RunStatus,
    Severity,
)

#: A run counts as "seed evidence" only when a project artifact recorded the value.
_SEED_EVIDENCE = {ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED}


def mean_std(values: Sequence[float], ddof: int = 0) -> tuple[float | None, float | None]:
    """Mean and standard deviation with an explicit degrees-of-freedom choice."""
    if not values:
        return None, None
    mean = sum(values) / len(values)
    denominator = len(values) - ddof
    if denominator <= 0:
        return mean, None
    variance = sum((value - mean) ** 2 for value in values) / denominator
    return mean, math.sqrt(variance)


def displayed_spread(std: float | None, multiplier: float, n: int) -> float | None:
    """``multiplier * std / sqrt(n)``, i.e. the project's own reported spread rule."""
    if std is None or n <= 0:
        return None
    return multiplier * std / math.sqrt(n)


def close_enough(a: float | None, b: float | None, tolerance: float) -> bool | None:
    if a is None or b is None:
        return None
    if not math.isfinite(a) or not math.isfinite(b):
        return None
    return abs(a - b) <= tolerance


def _canonical_config(config: dict[str, Any] | None) -> str | None:
    if config is None:
        return None
    return hashlib.sha256(_dump(config).encode("utf-8")).hexdigest()[:16]


def _dump(node: Any) -> str:
    if isinstance(node, dict):
        return "{" + ",".join(f"{key}:{_dump(node[key])}" for key in sorted(node)) + "}"
    if isinstance(node, (list, tuple)):
        return "[" + ",".join(_dump(item) for item in node) + "]"
    if isinstance(node, float):
        return f"{node:.12g}"
    return str(node)


class FamilyIdentityResult(BaseModel):
    family_id: str
    status: IdentityStatus
    n_runs: int
    distinct_methods: int = 0
    distinct_tasks: int = 0
    distinct_config_hashes: int = 0
    note: str | None = None


class SeedIntegrityResult(BaseModel):
    family_id: str
    status: str
    n_runs: int
    runs_with_seed_evidence: int = 0
    runs_with_unknown_seed: int = 0
    runs_with_conflicting_seed: int = 0
    distinct_seeds: int = 0
    duplicated_seeds: list[int] = Field(default_factory=list)
    declared_repetitions: int | None = None
    note: str | None = None


class MetricProvenanceResult(BaseModel):
    family_id: str
    primary_metric: str | None = None
    metric_names: list[str] = Field(default_factory=list)
    runs_with_metrics: int = 0
    direction_confirmed: int = 0
    direction_supported: int = 0
    direction_inferred: int = 0
    direction_unknown: int = 0
    runs_missing_primary_value: int = 0
    note: str | None = None


class MembershipResult(BaseModel):
    family_id: str
    n_runs: int
    included: int = 0
    excluded: int = 0
    unknown_membership: int = 0
    absent_slots: int = 0
    excluded_without_evidence: int = 0
    reason_status: str = "UNKNOWN"
    rule_status: str = "UNKNOWN"
    note: str | None = None


class RecomputeResult(BaseModel):
    aggregation_id: str
    family_id: str
    metric_name: str
    variant: str
    comparison_status: ComparisonStatus
    n_reported: int | None = None
    n_recomputed: int = 0
    reported_value: float | None = None
    recomputed_value: float | None = None
    reported_spread: float | None = None
    recomputed_spread: float | None = None
    mean_match: bool | None = None
    spread_match: bool | None = None
    note: str | None = None


class AuditResult(BaseModel):
    project_id: str
    root: str
    adapter: str
    identity: list[FamilyIdentityResult] = Field(default_factory=list)
    seeds: list[SeedIntegrityResult] = Field(default_factory=list)
    metrics: list[MetricProvenanceResult] = Field(default_factory=list)
    membership: list[MembershipResult] = Field(default_factory=list)
    recomputation: list[RecomputeResult] = Field(default_factory=list)
    coverage: dict[str, EvidenceCounts] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "families": len(self.identity),
            "runs": sum(item.n_runs for item in self.identity),
            "aggregations": len(self.recomputation),
            "findings": len(self.findings),
            "matched": sum(
                1 for item in self.recomputation if item.comparison_status is ComparisonStatus.MATCH
            ),
            "mismatched": sum(
                1
                for item in self.recomputation
                if item.comparison_status is ComparisonStatus.MISMATCH
            ),
            "comparison_unknown": sum(
                1
                for item in self.recomputation
                if item.comparison_status is ComparisonStatus.UNKNOWN
            ),
        }


@dataclass
class CoverageTarget:
    """One field whose evidence grade is counted across all runs."""

    name: str
    extract: Any
    note: str | None = None


COVERAGE_FIELDS: tuple[CoverageTarget, ...] = (
    CoverageTarget("seed", lambda run: run.seed),
    CoverageTarget("tracker_run_id", lambda run: run.tracker_run_id),
    CoverageTarget("repetition_index", lambda run: run.repetition_index),
    CoverageTarget("code_commit", lambda run: run.code_commit),
    CoverageTarget("code_dirty", lambda run: run.code_dirty),
    CoverageTarget("dataset", lambda run: run.dataset),
    CoverageTarget("dataset_version", lambda run: run.dataset_version),
    CoverageTarget("method", lambda run: run.method),
    CoverageTarget("task", lambda run: run.task),
    CoverageTarget("resolved_config", lambda run: run.resolved_config),
    CoverageTarget("config_source", lambda run: run.config_source),
    CoverageTarget("entrypoint", lambda run: run.entrypoint),
    CoverageTarget("command", lambda run: run.command),
    CoverageTarget("start_time", lambda run: run.start_time),
    CoverageTarget("end_time", lambda run: run.end_time),
    CoverageTarget("termination_cause", lambda run: run.termination_cause),
    CoverageTarget("compute_budget", lambda run: run.compute_budget),
    CoverageTarget("runtime_seconds", lambda run: run.runtime_seconds),
    CoverageTarget("history_rows", lambda run: run.history_rows),
    CoverageTarget("included_in_aggregation", lambda run: run.included_in_aggregation),
    CoverageTarget("exclusion_category", lambda run: run.exclusion_category),
    CoverageTarget("exclusion_reason", lambda run: run.exclusion_reason),
    CoverageTarget("exclusion_evidence", lambda run: run.exclusion_evidence),
)


def audit_project(project: ExperimentProject) -> AuditResult:
    """Run the five checks over a scanned project and fill the aggregation records."""
    runs_by_family: dict[str, list[ExperimentRun]] = {}
    for run in project.runs:
        runs_by_family.setdefault(run.family_id, []).append(run)

    result = AuditResult(project_id=project.project_id, root=project.root, adapter=project.adapter)
    for family in project.families:
        runs = runs_by_family.get(family.family_id, [])
        result.identity.append(check_run_identity(family, runs, result.findings))
        result.seeds.append(check_seed_integrity(family, runs, result.findings))
        result.metrics.append(check_metric_provenance(family, runs, result.findings))
        result.membership.append(
            check_aggregation_membership(family, runs, project, result.findings)
        )
    for record in project.aggregations:
        result.recomputation.append(check_aggregation_recompute(record, project, result.findings))
    result.coverage = provenance_coverage(project.runs)
    _add_coverage_findings(project, result)
    result.findings.sort(
        key=lambda finding: (-_SEVERITY_ORDER[finding.severity], finding.entity_id or "")
    )
    return result


_SEVERITY_ORDER = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}


# ------------------------------------------------------------------- check A
def check_run_identity(
    family: ExperimentFamily, runs: list[ExperimentRun], findings: list[Finding]
) -> FamilyIdentityResult:
    if not runs:
        finding = Finding(
            category=FindingCategory.RUN_IDENTITY,
            title="family has no discovered runs",
            severity=Severity.LOW,
            entity_type="family",
            entity_id=family.family_id,
            evidence=[f"declared repetitions: {family.declared_repetitions.value}"],
            recommendation="check whether the result directory is empty or was skipped by discovery",
        )
        findings.append(finding)
        return FamilyIdentityResult(
            family_id=family.family_id,
            status=IdentityStatus.UNKNOWN,
            n_runs=0,
            note="no runs to compare",
        )

    methods = {run.method.value for run in runs if run.method.has_value}
    tasks = {run.task.value for run in runs if run.task.has_value}
    hashes = {
        _canonical_config(run.resolved_config.value)
        for run in runs
        if run.resolved_config.has_value
    }
    hashes.discard(None)
    config_evidenced = len(hashes)

    if config_evidenced == 0 and not methods:
        status = IdentityStatus.UNKNOWN
        note = "neither method nor resolved config is evidenced, so identity cannot be compared"
    elif len(methods) <= 1 and len(tasks) <= 1 and config_evidenced <= 1:
        status = IdentityStatus.CONSISTENT
        note = "all runs share one evidenced method/task/configuration"
    else:
        status = IdentityStatus.MIXED_CONFIG
        note = "the runs of this family do not share one evidenced configuration"
    result = FamilyIdentityResult(
        family_id=family.family_id,
        status=status,
        n_runs=len(runs),
        distinct_methods=len(methods),
        distinct_tasks=len(tasks),
        distinct_config_hashes=config_evidenced,
        note=note,
    )
    if status is IdentityStatus.MIXED_CONFIG:
        findings.append(
            Finding(
                category=FindingCategory.RUN_IDENTITY,
                title="runs in one family do not share a single identity",
                severity=Severity.MEDIUM if family.primary_metric else Severity.INFO,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[
                    f"distinct methods: {len(methods)}",
                    f"distinct tasks: {len(tasks)}",
                    f"distinct resolved-config hashes: {config_evidenced} over {len(runs)} runs",
                    note or "",
                ],
                recommendation=(
                    "confirm whether this family is a hyperparameter grid (mixed configs expected) "
                    "or an identity leak (mixed configs unintended)"
                ),
            )
        )
    return result


# ------------------------------------------------------------------- check B
def check_seed_integrity(
    family: ExperimentFamily, runs: list[ExperimentRun], findings: list[Finding]
) -> SeedIntegrityResult:
    evidenced = [
        run.seed.value
        for run in runs
        if run.seed.status in _SEED_EVIDENCE and run.seed.value is not None
    ]
    unknown = sum(1 for run in runs if run.seed.status is ProvenanceStatus.UNKNOWN)
    conflicting = sum(1 for run in runs if run.seed.status is ProvenanceStatus.CONFLICTING)
    distinct = sorted({value for value in evidenced})
    duplicated = sorted({value for value in evidenced if evidenced.count(value) > 1})
    declared = family.declared_repetitions.value

    if not evidenced and conflicting == 0:
        status = "ALL_SEEDS_UNKNOWN"
        note = (
            "no artifact records a seed for any run of this family; the run count is not evidence of "
            "distinct seeds and was not treated as such"
        )
        findings.append(
            Finding(
                category=FindingCategory.PROVENANCE_GAP,
                title="seed is not recoverable from any artifact",
                severity=Severity.MEDIUM,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[
                    f"runs: {len(runs)}",
                    f"seed status: {unknown} UNKNOWN, {conflicting} CONFLICTING",
                    f"declared repetitions: {declared}",
                    "the numeric run slot index was not converted into a seed",
                ],
                recommendation=(
                    "record the seed (and its derivation) inside the run config at run time; a "
                    "'10-seed' claim cannot be verified from artifacts that never stored a seed"
                ),
            )
        )
    elif conflicting:
        status = "CONFLICTING_SEEDS"
        note = "at least one run's artifacts disagree about its seed"
        findings.append(
            Finding(
                category=FindingCategory.SEED_INTEGRITY,
                title="conflicting seed evidence",
                severity=Severity.HIGH,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[f"{conflicting} runs carry conflicting seed records"],
                recommendation="resolve which artifact is authoritative before quoting a seed count",
            )
        )
    elif duplicated:
        status = "DUPLICATE_SEEDS"
        note = f"seeds appear more than once: {duplicated}"
        findings.append(
            Finding(
                category=FindingCategory.SEED_INTEGRITY,
                title="duplicate seeds inside one family",
                severity=Severity.HIGH,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[
                    f"duplicated seed values: {duplicated}",
                    f"distinct seeds: {len(distinct)}",
                ],
                recommendation="check whether repeated seeds were intended (reruns) or collapse the effective sample size",
            )
        )
    elif declared is not None and len(distinct) != declared:
        status = "SEED_COUNT_DIFFERS_FROM_DECLARED"
        note = f"{len(distinct)} distinct seeds recorded against {declared} declared repetitions"
        findings.append(
            Finding(
                category=FindingCategory.SEED_INTEGRITY,
                title="recorded seed count differs from the declared repetition count",
                severity=Severity.MEDIUM,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[
                    f"distinct seeds: {len(distinct)}",
                    f"declared repetitions: {declared}",
                    f"runs: {len(runs)}",
                ],
                recommendation="reconcile the launch protocol with the recorded seeds before quoting N",
            )
        )
    else:
        status = "CONSISTENT"
        note = "one distinct evidenced seed per run"

    return SeedIntegrityResult(
        family_id=family.family_id,
        status=status,
        n_runs=len(runs),
        runs_with_seed_evidence=len(evidenced),
        runs_with_unknown_seed=unknown,
        runs_with_conflicting_seed=conflicting,
        distinct_seeds=len(distinct),
        duplicated_seeds=duplicated,
        declared_repetitions=declared,
        note=note,
    )


# ------------------------------------------------------------------- check C
def check_metric_provenance(
    family: ExperimentFamily, runs: list[ExperimentRun], findings: list[Finding]
) -> MetricProvenanceResult:
    names: list[str] = []
    confirmed = supported = inferred = unknown = 0
    runs_with_metrics = 0
    for run in runs:
        if run.metrics:
            runs_with_metrics += 1
        for metric in run.metrics:
            if metric.name not in names:
                names.append(metric.name)
            match metric.direction.status:
                case ProvenanceStatus.CONFIRMED:
                    confirmed += 1
                case ProvenanceStatus.SUPPORTED:
                    supported += 1
                case ProvenanceStatus.INFERRED:
                    inferred += 1
                case ProvenanceStatus.UNKNOWN:
                    unknown += 1
                case ProvenanceStatus.CONFLICTING:
                    unknown += 1
    missing_primary = 0
    if family.primary_metric:
        for run in runs:
            primary = run.metric(family.primary_metric)
            if primary is None:
                missing_primary += 1 if run.metrics else 0
            elif not primary.value.has_value and run.included_in_aggregation.value is not None:
                missing_primary += 1

    result = MetricProvenanceResult(
        family_id=family.family_id,
        primary_metric=family.primary_metric,
        metric_names=names,
        runs_with_metrics=runs_with_metrics,
        direction_confirmed=confirmed,
        direction_supported=supported,
        direction_inferred=inferred,
        direction_unknown=unknown,
        runs_missing_primary_value=missing_primary,
    )
    if not names:
        findings.append(
            Finding(
                category=FindingCategory.METRIC_PROVENANCE,
                title="no metric values recovered for this family",
                severity=Severity.MEDIUM,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[f"runs: {len(runs)}", "metrics: none"],
                recommendation="check whether the artifact format is understood or the histories are empty",
            )
        )
    if unknown or inferred:
        findings.append(
            Finding(
                category=FindingCategory.METRIC_PROVENANCE,
                title="metric direction is not fully evidenced",
                severity=Severity.MEDIUM if unknown else Severity.LOW,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[
                    f"direction CONFIRMED: {confirmed}, SUPPORTED: {supported}",
                    f"direction INFERRED: {inferred}, UNKNOWN/CONFLICTING: {unknown}",
                    f"metrics: {', '.join(names) or '-'}",
                ],
                recommendation=(
                    "record minimize/maximize per metric in the project; a direction convention that "
                    "is wrong or missing can invert which run is called best"
                ),
            )
        )
    if missing_primary:
        findings.append(
            Finding(
                category=FindingCategory.METRIC_PROVENANCE,
                title="some runs have no value for the family's primary metric",
                severity=Severity.LOW,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[
                    f"primary metric: {family.primary_metric}",
                    f"runs affected: {missing_primary}",
                ],
                recommendation="decide explicitly whether these runs are absent, failed or truncated",
            )
        )
    return result


# ------------------------------------------------------------------- check D
def check_aggregation_membership(
    family: ExperimentFamily,
    runs: list[ExperimentRun],
    project: ExperimentProject,
    findings: list[Finding],
) -> MembershipResult:
    included = sum(1 for run in runs if run.included_in_aggregation.value is True)
    excluded_runs = [run for run in runs if run.included_in_aggregation.value is False]
    unknown = sum(1 for run in runs if run.included_in_aggregation.value is None)
    absent = sum(1 for run in runs if run.status is RunStatus.ABSENT_NO_ARTIFACT)
    no_evidence = [run for run in excluded_runs if not run.exclusion_evidence.has_value]

    reason_statuses = {run.exclusion_reason.status for run in excluded_runs}
    reason_status = (
        "CONFIRMED"
        if reason_statuses == {ProvenanceStatus.CONFIRMED}
        else (
            "NONE"
            if not excluded_runs
            else "MIXED"
            if len(reason_statuses) > 1
            else str(next(iter(reason_statuses)).value)
        )
    )

    result = MembershipResult(
        family_id=family.family_id,
        n_runs=len(runs),
        included=included,
        excluded=len(excluded_runs),
        unknown_membership=unknown,
        absent_slots=absent,
        excluded_without_evidence=len(no_evidence),
        reason_status=reason_status,
        rule_status=str(family.membership_rule.status.value),
        note=(
            f"declared repetitions {family.declared_repetitions.value} vs {len(runs)} slots "
            f"({included} included, {len(excluded_runs)} excluded)"
        ),
    )

    if excluded_runs:
        evidence = [
            f"included: {included}, excluded: {len(excluded_runs)}, membership rule: {family.membership_rule.status.value}",
            f"exclusion reason status: {reason_status}",
            f"excluded runs without any reason: {len(no_evidence)}",
        ]
        findings.append(
            Finding(
                category=FindingCategory.AGGREGATION_MEMBERSHIP,
                title="aggregation excludes runs",
                severity=Severity.MEDIUM if reason_status != "CONFIRMED" else Severity.LOW,
                entity_type="family",
                entity_id=family.family_id,
                evidence=evidence
                + [
                    f"{run.run_id}: category={run.exclusion_category.status.value} reason={run.exclusion_reason.status.value}"
                    for run in excluded_runs
                ],
                recommendation=(
                    "keep the excluded-run list and its reason in a machine-readable artifact, not only "
                    "in prose, so the published mean can be reconstructed without reading the README"
                ),
            )
        )
    if no_evidence:
        findings.append(
            Finding(
                category=FindingCategory.AGGREGATION_MEMBERSHIP,
                title="excluded runs without any stated reason",
                severity=Severity.HIGH,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[
                    f"{len(no_evidence)} runs carry the exclusion marker but no reason evidence"
                ],
                recommendation="record why each run left the aggregation set",
            )
        )
    declared = family.declared_repetitions.value
    if declared is not None and family.kind.value == "evaluation" and len(runs) != declared:
        findings.append(
            Finding(
                category=FindingCategory.AGGREGATION_MEMBERSHIP,
                title="discovered run count differs from the declared protocol",
                severity=Severity.MEDIUM,
                entity_type="family",
                entity_id=family.family_id,
                evidence=[f"declared repetitions: {declared}", f"discovered slots: {len(runs)}"],
                recommendation="check for runs whose artifacts were never fetched or were overwritten",
            )
        )
    for record in project.aggregations:
        if record.family_id != family.family_id:
            continue
        stray = [
            member_id
            for member_id in record.member_run_ids
            if (member := project.run(member_id)) is not None
            and member.included_in_aggregation.value is False
        ]
        if stray:
            findings.append(
                Finding(
                    category=FindingCategory.AGGREGATION_MEMBERSHIP,
                    title="aggregation contains runs the project marked as excluded",
                    severity=Severity.HIGH,
                    entity_type="aggregation",
                    entity_id=record.aggregation_id,
                    evidence=[f"{len(stray)} members have included_in_aggregation=False"],
                    recommendation="reconcile membership with the exclusion markers",
                )
            )
    return result


# ------------------------------------------------------------------- check E
def check_aggregation_recompute(
    record: AggregationRecord, project: ExperimentProject, findings: list[Finding]
) -> RecomputeResult:
    values: list[float] = []
    missing: list[str] = []
    for member_id in record.member_run_ids:
        run = project.run(member_id)
        if run is None:
            missing.append(member_id)
            continue
        metric = run.metric(record.metric_name)
        if metric is None or not metric.value.has_value:
            missing.append(member_id)
            continue
        value = float(metric.value.value)  # type: ignore[arg-type]
        if record.transform == "negate":
            value = -value
        values.append(value)

    record.values = values
    record.n = len(values)
    mean, std = (
        mean_std(values, ddof=record.std_ddof) if record.statistic == "mean" else (None, None)
    )
    record.mean = mean
    record.std = std
    record.recomputed_value = mean
    record.recomputed_spread = displayed_spread(std, record.display_multiplier, record.n)

    mean_match: bool | None = None
    spread_match: bool | None = None
    if record.statistic != "mean":
        record.comparison_status = ComparisonStatus.UNKNOWN
        note = f"v0.1 recomputes only statistic='mean', this record declares statistic='{record.statistic}'"
    elif not values:
        record.comparison_status = ComparisonStatus.UNKNOWN
        note = "no member metric values could be recovered"
    elif not record.has_reported:
        record.comparison_status = ComparisonStatus.UNKNOWN
        note = "recomputed from raw run metrics; the project ships no machine-readable reported value to compare against"
    else:
        mean_match = close_enough(record.recomputed_value, record.reported_value, record.tolerance)
        if record.reported_spread is not None:
            spread_match = close_enough(
                record.recomputed_spread, record.reported_spread, record.spread_tolerance
            )
        if mean_match is True and spread_match is not False:
            record.comparison_status = ComparisonStatus.MATCH
        elif mean_match is False or spread_match is False:
            record.comparison_status = ComparisonStatus.MISMATCH
        else:
            record.comparison_status = ComparisonStatus.UNKNOWN
        note = None

    result = RecomputeResult(
        aggregation_id=record.aggregation_id,
        family_id=record.family_id,
        metric_name=record.metric_name,
        variant=record.variant,
        comparison_status=record.comparison_status,
        n_reported=None,
        n_recomputed=record.n,
        reported_value=record.reported_value,
        recomputed_value=record.recomputed_value,
        reported_spread=record.reported_spread,
        recomputed_spread=record.recomputed_spread,
        mean_match=mean_match,
        spread_match=spread_match,
        note=note,
    )
    if missing:
        result.note = f"{len(missing)} members had no recoverable metric value"
        findings.append(
            Finding(
                category=FindingCategory.AGGREGATION_MISMATCH,
                title="aggregation members without recoverable metric values",
                severity=Severity.MEDIUM,
                entity_type="aggregation",
                entity_id=record.aggregation_id,
                evidence=[
                    f"members: {len(record.member_run_ids)}",
                    f"values recovered: {len(values)}",
                ],
                recommendation="check whether those runs failed, were truncated, or use a different metric column",
            )
        )
    if record.comparison_status is ComparisonStatus.MISMATCH:
        findings.append(
            Finding(
                category=FindingCategory.AGGREGATION_MISMATCH,
                title="reported aggregation does not match recomputation from the runs",
                severity=Severity.HIGH,
                entity_type="aggregation",
                entity_id=record.aggregation_id,
                evidence=[
                    f"N recomputed: {record.n}",
                    f"reported: {record.reported_value} +/- {record.reported_spread}",
                    f"recomputed: {record.recomputed_value} +/- {record.recomputed_spread}",
                    f"tolerance: {record.tolerance}",
                    f"membership rule: {record.membership_rule.value} ({record.membership_rule.status.value})",
                ],
                recommendation=(
                    "identify which membership, reduction or sign convention differs; do not adjust the "
                    "tolerance to force a match"
                ),
            )
        )
    return result


# ------------------------------------------------------------------ coverage
def provenance_coverage(runs: list[ExperimentRun]) -> dict[str, EvidenceCounts]:
    """Field-level evidence counts.  Intentionally no aggregate score."""
    coverage = {target.name: EvidenceCounts(note=target.note) for target in COVERAGE_FIELDS}
    metric_direction: EvidenceCounts = EvidenceCounts(
        note="evidence grade of metric.direction per metric record"
    )
    metric_value: EvidenceCounts = EvidenceCounts(
        note="a final metric value was recovered from an artifact"
    )
    for run in runs:
        for target in COVERAGE_FIELDS:
            field_value: ProvenanceField[Any] = target.extract(run)
            coverage[target.name].add(field_value)
        for metric in run.metrics:
            metric_direction.add(metric.direction)
            metric_value.add(metric.value)
    coverage["metric_direction"] = metric_direction
    coverage["metric_value"] = metric_value
    return coverage


def _add_coverage_findings(project: ExperimentProject, result: AuditResult) -> None:
    """One gap finding per field that no run evidences at all."""
    total = len(project.runs)
    if not total:
        return
    for name, counts in sorted(result.coverage.items()):
        if counts.unknown != total:
            continue
        severity = Severity.HIGH if name in _IDENTITY_CRITICAL else Severity.MEDIUM
        result.findings.append(
            Finding(
                category=FindingCategory.PROVENANCE_GAP,
                title=f"'{name}' is UNKNOWN for every discovered run",
                severity=severity,
                entity_type="project",
                entity_id=project.project_id,
                evidence=[f"0 / {total} runs carry evidence for this field", counts.note or ""],
                recommendation=(
                    "record this field at run time; post-hoc reconstruction can only ever label it UNKNOWN"
                ),
            )
        )


_IDENTITY_CRITICAL = {"seed", "code_commit", "termination_cause"}


__all__ = [
    "AuditResult",
    "audit_project",
    "check_aggregation_membership",
    "check_aggregation_recompute",
    "check_metric_provenance",
    "check_run_identity",
    "check_seed_integrity",
    "displayed_spread",
    "mean_std",
    "provenance_coverage",
]
