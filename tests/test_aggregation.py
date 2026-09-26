"""Aggregation arithmetic: which std, which spread, and what a mismatch means."""

from __future__ import annotations

import math

from experiment_doctor.audit import (
    audit_project,
    check_aggregation_recompute,
    close_enough,
    displayed_spread,
    mean_std,
)
from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.schema import (
    AggregationRecord,
    ComparisonStatus,
    ExperimentProject,
    Finding,
    RunStatus,
    SpreadBasis,
)
from tests.builders import make_family, make_run, metric, project_with

VALUES = [1.0, 2.0, 3.0]


def test_aggregation_population_std() -> None:
    mean, std = mean_std(VALUES, ddof=0)
    assert mean == 2.0
    assert std is not None and math.isclose(std, math.sqrt(2.0 / 3.0), rel_tol=1e-12)

    spread = displayed_spread(std, 3.0, 3)
    assert spread is not None and math.isclose(spread, 3.0 * std / math.sqrt(3), rel_tol=1e-12)
    # The published "+/- 3 sigma" of a 3-seed table is 3x the standard error, not std.
    assert spread < std * 3.0


def test_aggregation_spread_basis_is_declared_not_assumed() -> None:
    """A project whose published +/- is std must not have to claim a sqrt(N) division."""
    _, std = mean_std(VALUES, ddof=0)
    standard_error = displayed_spread(std, 1.0, 3)
    standard_deviation = displayed_spread(std, 1.0, 3, SpreadBasis.STANDARD_DEVIATION)
    assert standard_error is not None and standard_deviation is not None
    assert math.isclose(standard_deviation, std, rel_tol=1e-12), "std is not divided by sqrt(N)"
    assert math.isclose(standard_deviation, standard_error * math.sqrt(3), rel_tol=1e-12)
    # The default keeps every pre-existing record on the old rule.
    assert displayed_spread(std, 3.0, 3) == displayed_spread(
        std, 3.0, 3, SpreadBasis.STANDARD_ERROR
    )


def test_spread_basis_reaches_the_recomputation() -> None:
    runs = [
        make_run(f"r{i}", metrics=[metric("acc", value), metric("acc@best", value)])
        for i, value in enumerate(VALUES)
    ]
    family = make_family(primary_metric="acc@best")
    record = AggregationRecord(
        aggregation_id="F/f/acc@best@included",
        family_id="F/f",
        metric_name="acc@best",
        member_run_ids=[run.run_id for run in runs],
        n=len(runs),
        std_ddof=0,
        spread_basis=SpreadBasis.STANDARD_DEVIATION,
        display_multiplier=1.0,
        reported_value=2.0,
        reported_spread=mean_std(VALUES, ddof=0)[1],
        spread_tolerance=1e-9,
    )
    check_aggregation_recompute(record, project_with(runs, family, [record]), [])
    assert record.recomputed_spread is not None and record.reported_spread is not None
    assert math.isclose(record.recomputed_spread, record.reported_spread, abs_tol=1e-12)
    assert record.comparison_status is ComparisonStatus.MATCH


def test_aggregation_sample_std() -> None:
    mean, std = mean_std(VALUES, ddof=1)
    assert mean == 2.0
    assert std is not None and math.isclose(std, 1.0, rel_tol=1e-12)
    assert mean_std([], ddof=0) == (None, None)
    assert mean_std([5.0], ddof=1) == (5.0, None), "one value has no sample spread"
    assert displayed_spread(None, 3.0, 1) is None

    ddof0 = mean_std(VALUES, ddof=0)[1]
    ddof1 = mean_std(VALUES, ddof=1)[1]
    assert ddof0 is not None and ddof1 is not None and ddof0 < ddof1
    assert close_enough(ddof0, ddof1, 1e-9) is False, "the two are not interchangeable"


def test_aggregation_mismatch(mini_project_mismatch: ExperimentProject) -> None:
    project = mini_project_mismatch
    records = {record.aggregation_id: record for record in project.aggregations}
    bad = records["Planar4_EVAL/sepyfux_planar_4/-elbo@included"]
    assert bad.reported_value == 5.00
    assert bad.recomputed_value == 1.5
    assert bad.n == 2, "the published cell was averaged over the surviving seeds"

    results = {item.aggregation_id: item for item in audit_project(project).recomputation}
    bad_result = results[bad.aggregation_id]
    assert bad_result.comparison_status is ComparisonStatus.MISMATCH
    assert bad_result.mean_match is False, (
        "a perturbed published value must fail on the mean, not the spread"
    )
    assert bad_result.spread_match is True

    good = results["Planar4_EVAL/samtrux_planar_4/-elbo@included"]
    assert good.comparison_status is ComparisonStatus.MATCH
    assert good.mean_match is True and good.spread_match is True


def test_negated_metric_transform() -> None:
    """A metric logged as a loss must be negated before it can match a reported ELBO."""
    family = make_family(family_id="MB_EVAL/m_bcmb", primary_metric="elbo_fb:")
    runs = [
        make_run(
            "MB_EVAL/m_bcmb#slot_0",
            family_id=family.family_id,
            status=RunStatus.COMPLETED_INCLUDED,
            metrics=[metric("elbo_fb:", 3.0)],
            included_in_aggregation=ProvenanceField.of(
                True, ProvenanceStatus.CONFIRMED, SourceRef(path="run_0.csv")
            ),
        ),
        make_run(
            "MB_EVAL/m_bcmb#slot_1",
            family_id=family.family_id,
            status=RunStatus.COMPLETED_INCLUDED,
            metrics=[metric("elbo_fb:", 5.0)],
            included_in_aggregation=ProvenanceField.of(
                True, ProvenanceStatus.CONFIRMED, SourceRef(path="run_1.csv")
            ),
        ),
    ]
    project = project_with(runs, family)

    record = AggregationRecord(
        aggregation_id="MB_EVAL/m_bcmb/elbo_fb:@included",
        family_id=family.family_id,
        metric_name="elbo_fb:",
        member_run_ids=[run.run_id for run in runs],
        transform="negate",
        std_ddof=0,
        display_multiplier=3.0,
        reported_value=-4.0,
        reported_spread=2.12,
        tolerance=0.005,
        spread_tolerance=0.005,
    )
    project.aggregations.append(record)
    findings: list[Finding] = []
    result = check_aggregation_recompute(record, project, findings)

    assert result.recomputed_value == -4.0, "the loss-basis mean must be negated"
    assert result.comparison_status is ComparisonStatus.MATCH
    assert record.values == [-3.0, -5.0]
