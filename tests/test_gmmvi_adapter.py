"""End-to-end on a miniature gmmvi project: every number below is hand-checkable."""

from __future__ import annotations

import math

from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.schema import (
    AggregationRecord,
    ComparisonStatus,
    ExperimentProject,
    FamilyKind,
    MetricDirection,
    RunStatus,
)

PLANAR = "Planar4_EVAL/samtrux_planar_4"
SEPY = "Planar4_EVAL/sepyfux_planar_4"
GMM20 = "GMM20_EVAL/samtrux_gmm20"


def _records(project: ExperimentProject) -> dict[str, AggregationRecord]:
    return {record.aggregation_id: record for record in project.aggregations}


def _close(value: float | None, expected: float, rel_tol: float) -> bool:
    return value is not None and math.isclose(value, expected, rel_tol=rel_tol)


def _three_sigma(std: float, n: int) -> float:
    return 3.0 * std / math.sqrt(n)


def _recompute_matches(record: AggregationRecord, value: float, spread: float) -> bool:
    return _close(record.recomputed_value, value, 1e-12) and _close(
        record.recomputed_spread, spread, 1e-9
    )


def test_gmmvi_small_fixture(
    mini_project: ExperimentProject, mini_project_plain: ExperimentProject
) -> None:
    assert mini_project.adapter == "gmmvi-exp3"
    repo = mini_project.code_repository
    assert repo.value == "OlegArenz/gmmvi_reproducibility"
    assert repo.status is ProvenanceStatus.SUPPORTED, (
        "named in README.rst, not proven to be the code that ran"
    )
    assert {family.family_id for family in mini_project.families} == {PLANAR, SEPY, GMM20}
    assert all(family.kind is FamilyKind.EVALUATION for family in mini_project.families)
    assert len(mini_project.runs) == 9

    planar = mini_project.family(PLANAR)
    assert planar is not None and planar.primary_metric == "-elbo"
    assert planar.secondary_metrics == ["MMD:"]
    # The eval protocol, not the identically-named hyperopt one (repetitions 1).
    assert planar.declared_repetitions.value == 3
    assert planar.membership_rule.status is ProvenanceStatus.CONFIRMED

    first = mini_project.runs_of(PLANAR)[0]
    assert first.method.value == "SAMTRUX"
    assert first.method.status is ProvenanceStatus.CONFIRMED
    assert first.status is RunStatus.COMPLETED_INCLUDED
    assert first.history_rows.value == 3
    assert first.runtime_seconds.value == 300.0
    assert first.seed.status is ProvenanceStatus.UNKNOWN
    assert first.code_commit.status is ProvenanceStatus.UNKNOWN
    assert first.code_repository.status is ProvenanceStatus.SUPPORTED
    assert first.seed_derivation.status is ProvenanceStatus.UNKNOWN
    assert "start_seed" in (first.seed_derivation.confidence_note or "")
    assert first.tracker_run_id.status is ProvenanceStatus.UNKNOWN
    elbo = first.metric("-elbo")
    assert elbo is not None and elbo.value.value == 10.0, (
        "the last logged row is the aggregated value"
    )
    assert elbo.direction.value is MetricDirection.MINIMIZE

    records = _records(mini_project)
    assert len(records) == 7
    assert set(records) == {
        f"{PLANAR}/-elbo@included",
        f"{PLANAR}/MMD:@included",
        f"{SEPY}/-elbo@included",
        f"{SEPY}/-elbo@all_completed",
        f"{SEPY}/MMD:@included",
        f"{GMM20}/-elbo@included",
        f"{GMM20}/num_detected_modes@included",
    }

    elbo_record = records[f"{PLANAR}/-elbo@included"]
    assert (
        elbo_record.n == 3 and elbo_record.std_ddof == 0 and elbo_record.display_multiplier == 3.0
    )
    assert _recompute_matches(elbo_record, 11.0, _three_sigma(math.sqrt(2.0 / 3.0), 3))
    assert _recompute_matches(
        records[f"{PLANAR}/MMD:@included"], 0.02, _three_sigma(math.sqrt(2e-4 / 3.0), 3)
    )
    assert _recompute_matches(records[f"{GMM20}/-elbo@included"], 6.0, _three_sigma(1.0, 2))
    assert _recompute_matches(
        records[f"{GMM20}/num_detected_modes@included"], 9.0, _three_sigma(1.0, 2)
    )

    excluded = records[f"{SEPY}/-elbo@all_completed"]
    assert excluded.n == 4 and excluded.recomputed_value == 75.75
    counterfactual = excluded.recomputed_spread
    included = records[f"{SEPY}/-elbo@included"].recomputed_spread
    assert counterfactual is not None and included is not None
    assert counterfactual > included, "the two dropped seeds were the far ones"

    # With the published cells supplied, every recomputation lands on them.
    assert {
        record.comparison_status for record in mini_project.aggregations if record.has_reported
    } == {ComparisonStatus.MATCH}
    # Without them, comparison is honestly UNKNOWN rather than assumed.
    assert all(
        record.comparison_status is ComparisonStatus.UNKNOWN
        for record in mini_project_plain.aggregations
    )
    assert all(not record.has_reported for record in mini_project_plain.aggregations)


def test_gmmvi_exclusion_prose_binding(mini_project: ExperimentProject) -> None:
    bad = [run for run in mini_project.runs_of(SEPY) if run.included_in_aggregation.value is False]
    assert len(bad) == 2
    for run in bad:
        assert run.status is RunStatus.COMPLETED_EXCLUDED
        assert run.included_in_aggregation.status is ProvenanceStatus.CONFIRMED
        assert run.exclusion_reason.status is ProvenanceStatus.SUPPORTED
        assert "2 bad seeds" in (run.exclusion_reason.value or "")
        assert run.exclusion_evidence.status is ProvenanceStatus.SUPPORTED
        assert "README.rst" in (run.exclusion_evidence.value or "")
        assert "fetch_exp3.py" in (run.exclusion_evidence.value or "")
    clean = [run for run in mini_project.runs_of(PLANAR)]
    assert all(run.exclusion_reason.value is None for run in clean)
