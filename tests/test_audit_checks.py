"""The five v0.1 audit checks, at unit level and on the miniature project."""

from __future__ import annotations

from experiment_doctor.audit import (
    check_aggregation_membership,
    check_metric_provenance,
    check_run_identity,
    check_seed_integrity,
)
from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.schema import (
    ExperimentProject,
    Finding,
    IdentityStatus,
    MetricDirection,
    MetricRecord,
    RunStatus,
)
from tests.builders import evidenced_seed, make_family, make_run, project_with


def test_run_identity() -> None:
    findings: list[Finding] = []
    family = make_family()
    config = {"iterations": 1000000, "repetitions": 3}
    shared = ProvenanceField.of(
        config, ProvenanceStatus.CONFIRMED, SourceRef(path="run_0_config.yml")
    )

    runs = [
        make_run(
            "F/f#slot_0",
            method=ProvenanceField.of(
                "SAMTRUX", ProvenanceStatus.CONFIRMED, SourceRef(path="c.yml")
            ),
            resolved_config=shared,
        ),
        make_run("F/f#slot_1", resolved_config=shared),
    ]
    result = check_run_identity(family, runs, findings)
    assert result.status is IdentityStatus.CONSISTENT
    assert result.distinct_config_hashes == 1

    diverging = make_run(
        "F/f#slot_2",
        resolved_config=ProvenanceField.of(
            {"iterations": 5}, ProvenanceStatus.CONFIRMED, SourceRef(path="run_2_config.yml")
        ),
    )
    mixed = check_run_identity(family, [*runs, diverging], findings)
    assert mixed.status is IdentityStatus.MIXED_CONFIG
    assert mixed.distinct_config_hashes == 2
    assert any(finding.category.value == "RUN_IDENTITY" for finding in findings)

    empty = check_run_identity(family, [], findings)
    assert empty.status is IdentityStatus.UNKNOWN

    bare = check_run_identity(family, [make_run("F/f#slot_0")], findings)
    assert bare.status is IdentityStatus.UNKNOWN, (
        "no method and no config is not evidence of consistency"
    )


def test_unknown_seed_not_inferred(mini_project: ExperimentProject) -> None:
    family = mini_project.family("Planar4_EVAL/samtrux_planar_4")
    assert family is not None
    runs = mini_project.runs_of(family.family_id)
    assert len(runs) == 3
    for run in runs:
        assert run.seed.status is ProvenanceStatus.UNKNOWN
        assert run.seed.value is None
        assert run.repetition_index.value is None
        assert run.tracker_run_id.value is None

    findings: list[Finding] = []
    result = check_seed_integrity(family, runs, findings)
    assert result.status == "ALL_SEEDS_UNKNOWN"
    assert result.runs_with_seed_evidence == 0
    assert result.distinct_seeds == 0
    assert any("seed" in finding.title for finding in findings)
    assert any(
        "slot index was not converted into a seed" in line
        for finding in findings
        for line in finding.evidence
    )
    assert all(run.seed.value != run.result_slot_index for run in runs)


def test_duplicate_seed() -> None:
    findings: list[Finding] = []
    family = make_family(
        declared_repetitions=ProvenanceField.of(
            3, ProvenanceStatus.CONFIRMED, SourceRef(path="c.yml")
        )
    )
    runs = [
        make_run("F/f#0", seed=evidenced_seed(1)),
        make_run("F/f#1", seed=evidenced_seed(1)),
        make_run("F/f#2", seed=evidenced_seed(2)),
    ]
    result = check_seed_integrity(family, runs, findings)
    assert result.status == "DUPLICATE_SEEDS"
    assert result.duplicated_seeds == [1]
    assert result.distinct_seeds == 2
    assert result.runs_with_seed_evidence == 3

    fewer = check_seed_integrity(
        family,
        [make_run("F/f#0", seed=evidenced_seed(1)), make_run("F/f#1", seed=evidenced_seed(2))],
        findings,
    )
    assert fewer.status == "SEED_COUNT_DIFFERS_FROM_DECLARED"

    split = check_seed_integrity(
        family,
        [
            make_run(
                "F/f#0",
                seed=ProvenanceField[int].conflicting([SourceRef(path="a"), SourceRef(path="b")]),
            ),
            make_run("F/f#1", seed=evidenced_seed(2)),
        ],
        findings,
    )
    assert split.status == "CONFLICTING_SEEDS"


def test_metric_direction(mini_project: ExperimentProject) -> None:
    planar = mini_project.runs_of("Planar4_EVAL/samtrux_planar_4")[0]
    elbo = planar.metric("-elbo")
    mmd = planar.metric("MMD:")
    assert elbo is not None and mmd is not None
    assert elbo.direction.value is MetricDirection.MINIMIZE
    assert elbo.direction.status is ProvenanceStatus.CONFIRMED
    assert elbo.direction.source is not None and "fetch_exp3.py" in (
        elbo.direction.source.path or ""
    )
    # MMD carries no explicit flag of its own: it inherits the branch chain's default.
    assert mmd.direction.value is MetricDirection.MINIMIZE
    assert mmd.direction.status is ProvenanceStatus.CONFIRMED

    modes = mini_project.runs_of("GMM20_EVAL/samtrux_gmm20")[0].metric("num_detected_modes")
    assert modes is not None and modes.direction.value is MetricDirection.MAXIMIZE
    assert modes.direction.status is ProvenanceStatus.CONFIRMED

    # A metric the project's code says nothing about stays unevidenced.
    silent = MetricRecord(
        name="surprise",
        value=ProvenanceField.of(1.0, ProvenanceStatus.CONFIRMED, SourceRef(path="x.csv")),
    )
    assert silent.direction.status is ProvenanceStatus.UNKNOWN
    assert silent.direction.value is None

    family = make_family(secondary_metrics=["surprise"])
    run = make_run(
        "F/f#0",
        metrics=[silent],
        status=RunStatus.COMPLETED_INCLUDED,
        included_in_aggregation=ProvenanceField.of(
            True, ProvenanceStatus.CONFIRMED, SourceRef(path="run_0.csv")
        ),
    )
    findings: list[Finding] = []
    result = check_metric_provenance(family, [run], findings)
    assert result.direction_unknown == 1
    assert result.direction_confirmed == 0
    assert result.runs_with_metrics == 1


def test_membership_exclusion(mini_project: ExperimentProject) -> None:
    family = mini_project.family("Planar4_EVAL/sepyfux_planar_4")
    assert family is not None
    runs = mini_project.runs_of(family.family_id)
    assert len(runs) == 4
    assert sum(1 for run in runs if run.included_in_aggregation.value is True) == 2
    assert sum(1 for run in runs if run.included_in_aggregation.value is False) == 2

    for run in runs:
        assert run.included_in_aggregation.status is ProvenanceStatus.CONFIRMED
        assert run.included_in_aggregation.source is not None
        assert ".csv" in (run.included_in_aggregation.source.path or "")
    assert {run.status for run in runs if run.included_in_aggregation.value is False} == {
        RunStatus.COMPLETED_EXCLUDED
    }

    findings: list[Finding] = []
    result = check_aggregation_membership(family, runs, mini_project, findings)
    assert (result.included, result.excluded) == (2, 2)
    assert result.unknown_membership == 0
    assert result.excluded_without_evidence == 0
    assert result.rule_status == ProvenanceStatus.CONFIRMED.value
    assert result.reason_status == ProvenanceStatus.SUPPORTED.value, (
        "the cause is prose, not a machine-readable field"
    )

    records = {record.aggregation_id: record for record in mini_project.aggregations}
    included = records[f"{family.family_id}/-elbo@included"]
    everything = records[f"{family.family_id}/-elbo@all_completed"]
    assert (included.n, everything.n) == (2, 4)
    assert included.membership_rule.status is ProvenanceStatus.CONFIRMED
    assert everything.membership_rule.status is ProvenanceStatus.INFERRED
    assert included.recomputed_value == 1.5
    assert everything.recomputed_value == 75.75
    assert included.excluded_run_ids and not everything.excluded_run_ids


def test_membership_unknown_without_a_rule() -> None:
    """A family whose artifacts say nothing about membership must not default to 'included'."""
    findings: list[Finding] = []
    family = make_family(family_id="Planar4/samtrux_planar_4", result_dir="Planar4")
    run = make_run("Planar4/samtrux_planar_4#slot_0", family_id=family.family_id)
    project = project_with([run], family)
    result = check_aggregation_membership(family, [run], project, findings)
    assert result.unknown_membership == 1
    assert result.included == 0 and result.excluded == 0
    assert result.rule_status == ProvenanceStatus.UNKNOWN.value
