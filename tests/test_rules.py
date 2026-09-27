"""Branch semantics for ED001-ED010, plus the false-inference firewall contracts.

Each rule is exercised on synthetic projects built from the unified schema only:
nothing here opens a fixture directory, so a status can only come from what the
rule reads off a schema object.  The firewall tests assert the outcomes the tool
must never produce from absent evidence.
"""

from __future__ import annotations

from typing import Any

import pytest

from experiment_doctor.audit import AuditResult, audit_project
from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.rules import (
    RULES,
    Rule,
    RuleContext,
    RuleResult,
    RuleStatus,
    run_rules,
    status_counts,
)
from experiment_doctor.rules.aggregation_consistency import AggregationNumericalConsistency
from experiment_doctor.rules.code_provenance import HistoricalCodeProvenance
from experiment_doctor.rules.config_provenance import ResolvedConfigurationProvenance
from experiment_doctor.rules.environment import RuntimeEnvironmentProvenance
from experiment_doctor.rules.identity import RunIdentityConsistency
from experiment_doctor.rules.membership import AggregationMembershipProvenance
from experiment_doctor.rules.metric_selection import MetricSelectionProvenance
from experiment_doctor.rules.seeds import SeedProvenanceIntegrity
from experiment_doctor.rules.spread_semantics import SpreadSemanticsConsistency
from experiment_doctor.rules.termination import TerminationProvenance
from experiment_doctor.schema import (
    AggregationRecord,
    ArtifactRef,
    ArtifactRole,
    ArtifactType,
    ComparisonStatus,
    DeclaredEnvironment,
    DeclaredEnvironmentType,
    EnvironmentRelationship,
    ExperimentProject,
    ExperimentRun,
    FamilyKind,
    RunEnvironmentBinding,
    RunStatus,
    RuntimeEnvironment,
    SelectionPolicy,
    Severity,
    SpreadBasis,
    SpreadSemantics,
    TerminationCause,
)
from tests.builders import (
    artifact,
    attested,
    evidenced_seed,
    make_aggregation,
    make_family,
    make_run,
    metric,
    project_with,
)

#: Words the tool never uses: they would turn an evidence gap into an accusation.
FORBIDDEN_LABELS = (
    "cherry-pick",
    "cherrypick",
    "misconduct",
    "fraud",
    "malicious",
    "dishonest",
    "suspicious",
)


def context_of(project: ExperimentProject) -> tuple[RuleContext, AuditResult]:
    """Audit first, so the rules see the same records the report sees."""
    audit = audit_project(project)
    return RuleContext(project=project, audit=audit), audit


def evaluate(rule: Rule, project: ExperimentProject) -> list[RuleResult]:
    context, _ = context_of(project)
    return rule.evaluate(context)


def one(rule: Rule, project: ExperimentProject) -> RuleResult:
    results = evaluate(rule, project)
    assert len(results) == 1, [result.entity_id for result in results]
    return results[0]


def texts(result: RuleResult) -> str:
    blob = " ".join([result.summary, *result.evidence, *result.limitations])
    return (blob + " " + (result.recommendation or "")).lower()


def family_runs(count: int = 3, **overrides: Any) -> list[ExperimentRun]:
    return [make_run(f"F/f/run_{i}", **overrides) for i in range(count)]


# --------------------------------------------------------------- ED001 identity


def test_ed001_passes_when_only_the_seed_dimension_varies() -> None:
    runs = [
        make_run(
            f"F/f/run_{i}",
            method=attested("VAE", "config.json"),
            task=attested("CIFAR10 density", "config.json"),
            seed=attested(i, "config.json"),
            resolved_config=attested({"layers": 2, "seed": str(i)}, "config.json"),
        )
        for i in range(3)
    ]
    result = one(RunIdentityConsistency(), project_with(runs, make_family()))
    assert result.status is RuleStatus.PASS
    assert result.measurements["unexplained_config_keys"] == 0


def test_ed001_fails_when_one_family_holds_two_methods() -> None:
    runs = [
        make_run("F/f/run_0", method=attested("VAE", "config.json")),
        make_run("F/f/run_1", method=attested("GMM", "config.json")),
    ]
    result = one(RunIdentityConsistency(), project_with(runs, make_family()))
    assert result.status is RuleStatus.FAIL
    assert result.severity is Severity.HIGH
    assert "method" in result.summary


def test_ed001_reports_an_unexplained_difference_as_inconclusive() -> None:
    runs = [
        make_run(
            f"F/f/run_{i}",
            method=attested("VAE", "config.json"),
            resolved_config=attested({"lr": lr}, "config.json"),
        )
        for i, lr in enumerate(("1e-3", "1e-4"))
    ]
    result = one(RunIdentityConsistency(), project_with(runs, make_family()))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.measurements["unexplained_config_keys"] == 1


def test_ed001_accepts_varied_configurations_in_a_search_family() -> None:
    runs = [
        make_run(
            f"F/f/run_{i}",
            method=attested("VAE", "config.json"),
            resolved_config=attested({"lr": lr}, "config.json"),
        )
        for i, lr in enumerate(("1e-3", "1e-4"))
    ]
    family = make_family(kind=FamilyKind.HYPERPARAMETER_SEARCH)
    result = one(RunIdentityConsistency(), project_with(runs, family))
    assert result.status is RuleStatus.PASS


def test_ed001_not_applicable_below_two_runs() -> None:
    runs = [make_run("F/f/run_0", method=attested("VAE", "config.json"))]
    result = one(RunIdentityConsistency(), project_with(runs, make_family()))
    assert result.status is RuleStatus.NOT_APPLICABLE
    assert result.severity is Severity.INFO


def test_ed001_cannot_compare_identity_with_no_evidence_at_all() -> None:
    result = one(RunIdentityConsistency(), project_with(family_runs(2), make_family()))
    assert result.status is RuleStatus.INCONCLUSIVE


# ------------------------------------------------------------------ ED002 seeds


def test_ed002_passes_on_distinct_seeds_recovered_from_run_artifacts() -> None:
    runs = [make_run(f"F/f/run_{i}", seed=evidenced_seed(1000 + i)) for i in range(3)]
    result = one(SeedProvenanceIntegrity(), project_with(runs, make_family()))
    assert result.status is RuleStatus.PASS
    assert result.measurements["distinct_seeds"] == 3


def test_ed002_fails_when_an_evidenced_seed_is_reused() -> None:
    runs = [make_run(f"F/f/run_{i}", seed=evidenced_seed(value)) for i, value in enumerate((7, 7))]
    result = one(SeedProvenanceIntegrity(), project_with(runs, make_family()))
    assert result.status is RuleStatus.FAIL
    assert result.measurements["duplicated_seeds"] == 1


def test_ed002_fails_when_artifacts_disagree_about_one_run_seed() -> None:
    runs = [
        make_run("F/f/run_0", seed=evidenced_seed(7)),
        make_run(
            "F/f/run_1",
            seed=ProvenanceField.conflicting(
                [SourceRef(path="config.yml"), SourceRef(path="log.txt")]
            ),
        ),
    ]
    result = one(SeedProvenanceIntegrity(), project_with(runs, make_family()))
    assert result.status is RuleStatus.FAIL


def test_ed002_not_applicable_for_a_search_family() -> None:
    runs = [make_run(f"F/f/run_{i}") for i in range(3)]
    family = make_family(kind=FamilyKind.HYPERPARAMETER_SEARCH)
    result = one(SeedProvenanceIntegrity(), project_with(runs, family))
    assert result.status is RuleStatus.NOT_APPLICABLE


def test_firewall_unknown_seeds_never_become_a_duplicate_seed_failure() -> None:
    """N runs with no recorded seed say nothing about whether the seeds were distinct."""
    runs = [
        make_run(f"F/f/run_{i}", result_slot_index=i, repetition_index=attested(i, "dir.json"))
        for i in range(10)
    ]
    result = one(SeedProvenanceIntegrity(), project_with(runs, make_family()))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.severity is Severity.MEDIUM
    assert result.measurements["runs_with_seed_evidence"] == 0
    assert "the run count is not evidence of distinct seeds" in " ".join(result.evidence)


def test_firewall_slot_and_run_index_are_not_counted_as_seeds() -> None:
    runs = [
        make_run(
            f"F/f/run_{i}",
            result_slot_index=i,
            seed_derivation=attested("slot index", "README.md"),
        )
        for i in range(2)
    ]
    result = one(SeedProvenanceIntegrity(), project_with(runs, make_family()))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.measurements["distinct_seeds"] == 0


# ------------------------------------------------------------- ED003 code commit


def test_ed003_passes_on_a_revision_written_into_the_run_s_own_log() -> None:
    run = make_run(
        "F/f/run_0",
        code_commit=attested("deadbeef", "F/f/run_0/log.txt", line=3),
        code_dirty=attested(False, "F/f/run_0/log.txt", line=3),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    result = one(HistoricalCodeProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.PASS
    assert result.measurements["source_kind"] == "LOG"


def test_firewall_unknown_commit_is_inconclusive_not_failed() -> None:
    result = one(HistoricalCodeProvenance(), project_with(family_runs(1), make_family()))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.severity is Severity.MEDIUM
    assert (
        result.summary == "historical code identity cannot be established from available artifacts"
    )


def test_ed003_never_substitutes_the_current_checkout_for_history() -> None:
    run = make_run(
        "F/f/run_0",
        code_commit=attested("deadbeef", "README.md"),
        code_repository=attested("https://example/repo", "README.md"),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    result = one(HistoricalCodeProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert "not by anything this run produced" in result.summary


def test_ed003_fails_on_mutually_exclusive_revisions() -> None:
    run = make_run(
        "F/f/run_0",
        code_commit=ProvenanceField.conflicting(
            [SourceRef(path="meta.json"), SourceRef(path="log.txt")]
        ),
    )
    result = one(HistoricalCodeProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.FAIL


# --------------------------------------------------------------- ED004 config


def test_ed004_passes_on_a_configuration_recorded_inside_the_run_directory() -> None:
    run = make_run(
        "F/f/run_0",
        config_source=attested("config/exp.json", "F/f/run_0/cmd.txt"),
        resolved_config=attested({"layers": 2}, "F/f/run_0/config.snapshot.json"),
        artifacts=[artifact("F/f/run_0/config.snapshot.json", ArtifactType.CONFIG)],
    )
    result = one(ResolvedConfigurationProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.PASS


def test_firewall_repository_yaml_never_proves_the_historical_configuration() -> None:
    run = make_run(
        "F/f/run_0",
        config_source=attested("config/base.yaml", "config/base.yaml"),
        resolved_config=attested({"layers": 2}, "config/base.yaml"),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    result = one(ResolvedConfigurationProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert "reconstructed from a declaration" in result.summary
    assert any("runtime overrides" in item for item in result.limitations)


def test_ed004_reports_no_configuration_recovered() -> None:
    run = make_run("F/f/run_0", config_source=attested("config/base.yaml", "README.md"))
    result = one(ResolvedConfigurationProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.measurements["keys_recovered"] == 0


def test_ed004_fails_when_two_artifacts_disagree() -> None:
    run = make_run(
        "F/f/run_0",
        resolved_config=ProvenanceField.conflicting(
            [SourceRef(path="a.json"), SourceRef(path="b.json")]
        ),
    )
    result = one(ResolvedConfigurationProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.FAIL


# ---------------------------------------------------------- ED005 metric selection


def selection_record(**overrides: object) -> AggregationRecord:
    fields: dict[str, object] = {
        "metric_name": "-elbo",
        "reported_value": 91.3,
        "reported_source": SourceRef(path="table.md", line=4),
    }
    fields.update(overrides)
    return make_aggregation(**fields)


def test_ed005_passes_when_code_and_prose_name_the_same_selection() -> None:
    record = selection_record(
        implemented_selection=attested(SelectionPolicy.BEST, "average_log.py", line=60),
        documented_selection=attested(SelectionPolicy.BEST, "README.md", line=58),
    )
    result = one(MetricSelectionProvenance(), project_with([], make_family(), [record]))
    assert result.status is RuleStatus.PASS
    assert result.measurements["implemented_selection"] == "best"


def test_ed005_fails_when_prose_promises_last_and_code_takes_best() -> None:
    record = selection_record(
        implemented_selection=attested(SelectionPolicy.BEST, "average_log.py", line=60),
        documented_selection=attested(SelectionPolicy.LAST, "README.md", line=58),
    )
    result = one(MetricSelectionProvenance(), project_with([], make_family(), [record]))
    assert result.status is RuleStatus.FAIL
    assert result.severity is Severity.HIGH


def test_ed005_fails_on_mutually_incompatible_selection_accounts() -> None:
    record = selection_record(
        implemented_selection=ProvenanceField.conflicting([SourceRef(path="a.py")]),
        documented_selection=attested(SelectionPolicy.BEST, "README.md"),
    )
    result = one(MetricSelectionProvenance(), project_with([], make_family(), [record]))
    assert result.status is RuleStatus.FAIL


def test_ed005_passes_when_only_the_code_states_the_selection() -> None:
    record = selection_record(
        implemented_selection=attested(SelectionPolicy.LAST, "fetch.py", line=108)
    )
    result = one(MetricSelectionProvenance(), project_with([], make_family(), [record]))
    assert result.status is RuleStatus.PASS
    assert any("known only from the code" in item for item in result.limitations)


def test_firewall_an_unattributed_number_is_an_evidence_gap_not_a_selection_defect() -> None:
    result = one(MetricSelectionProvenance(), project_with([], make_family(), [selection_record()]))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert any("evidence gap" in item for item in result.limitations)


def test_ed005_not_applicable_for_a_reconstructed_record() -> None:
    record = make_aggregation(
        aggregation_id="F/f/-elbo@all_completed",
        implemented_selection=attested(SelectionPolicy.BEST, "average_log.py"),
    )
    result = one(MetricSelectionProvenance(), project_with([], make_family(), [record]))
    assert result.status is RuleStatus.NOT_APPLICABLE


def test_ed005_reports_best_minus_last_as_a_measurement_not_a_defect() -> None:
    """The counterfactual difference is quantified while the published claim is honoured."""
    runs = [
        make_run(
            f"F/f/run_{i}",
            metrics=[metric("-elbo@best", best), metric("-elbo@last", last)],
        )
        for i, (best, last) in enumerate(((90.0, 80.0), (92.0, 82.0), (94.0, 84.0)))
    ]
    record = selection_record(
        member_run_ids=[run.run_id for run in runs],
        n=3,
        implemented_selection=attested(SelectionPolicy.BEST, "average_log.py", line=60),
        documented_selection=attested(SelectionPolicy.BEST, "README.md", line=58),
    )
    result = one(MetricSelectionProvenance(), project_with(runs, make_family(), [record]))
    assert result.status is RuleStatus.PASS
    assert result.measurements["best_minus_last"] == 10.0


# ------------------------------------------------------------- ED006 membership


def included_run(run_id: str) -> ExperimentRun:
    return make_run(run_id, included_in_aggregation=attested(True, "F/f/run.json"))


def excluded_run(run_id: str, reason: ProvenanceField[str] | None = None) -> ExperimentRun:
    return make_run(
        run_id,
        status=RunStatus.COMPLETED_EXCLUDED,
        included_in_aggregation=attested(False, "F/f/run.json"),
        exclusion_reason=reason if reason is not None else ProvenanceField.unknown(),
    )


def membership_record(**overrides: object) -> AggregationRecord:
    fields: dict[str, object] = {
        "reported_value": 2.31,
        "reported_source": SourceRef(path="table.md", line=4),
        "membership_rule": attested("all completed runs of the family", "fetch.py", line=90),
    }
    fields.update(overrides)
    return make_aggregation(**fields)


def test_ed006_passes_when_every_member_is_evidenced_as_included() -> None:
    runs = [included_run("F/f/run_0"), included_run("F/f/run_1")]
    record = membership_record(member_run_ids=[run.run_id for run in runs])
    result = one(AggregationMembershipProvenance(), project_with(runs, make_family(), [record]))
    assert result.status is RuleStatus.PASS
    assert result.measurements["members"] == 2


def test_firewall_excluded_runs_never_make_membership_provenance_fail() -> None:
    """A project may drop runs; the question is whether the kept set is traceable."""
    kept = [included_run("F/f/run_0"), included_run("F/f/run_1")]
    dropped = excluded_run("F/f/run_9", attested("diverged before 3000 iters", "notes.md"))
    record = membership_record(
        member_run_ids=[run.run_id for run in kept],
        excluded_run_ids=[dropped.run_id],
    )
    project = project_with([*kept, dropped], make_family(), [record])
    result = one(AggregationMembershipProvenance(), project)
    assert result.status is RuleStatus.PASS
    assert "1 excluded run(s) enumerated separately" in result.summary
    for label in FORBIDDEN_LABELS:
        assert label not in texts(result)


def test_firewall_an_unexplained_exclusion_is_recorded_as_an_evidence_gap() -> None:
    """A ``.csv.bad`` rename is a fact about artifacts, not a claim about a researcher."""
    kept = [included_run("F/f/run_0"), included_run("F/f/run_1")]
    dropped = excluded_run("F/f/run_9.csv.bad")
    record = membership_record(
        member_run_ids=[run.run_id for run in kept],
        excluded_run_ids=[dropped.run_id],
    )
    result = one(
        AggregationMembershipProvenance(),
        project_with([*kept, dropped], make_family(), [record]),
    )
    assert result.status is RuleStatus.PASS
    assert any("evidence gap about the reason" in item for item in result.limitations)


def test_ed006_is_inconclusive_when_membership_is_not_recorded() -> None:
    runs = [make_run("F/f/run_0"), make_run("F/f/run_1")]
    record = membership_record(member_run_ids=[run.run_id for run in runs])
    result = one(AggregationMembershipProvenance(), project_with(runs, make_family(), [record]))
    assert result.status is RuleStatus.INCONCLUSIVE


def test_ed006_is_inconclusive_when_the_rule_itself_has_no_citation() -> None:
    runs = [included_run("F/f/run_0"), included_run("F/f/run_1")]
    record = membership_record(
        member_run_ids=[run.run_id for run in runs],
        membership_rule=ProvenanceField.unknown(note="never stated"),
    )
    result = one(AggregationMembershipProvenance(), project_with(runs, make_family(), [record]))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert "rule that selected the member runs is not evidenced" in result.summary


def test_ed006_is_inconclusive_when_a_member_id_resolves_to_nothing() -> None:
    record = membership_record(member_run_ids=["F/f/run_0", "F/f/ghost"])
    result = one(
        AggregationMembershipProvenance(),
        project_with([included_run("F/f/run_0")], make_family(), [record]),
    )
    assert result.status is RuleStatus.INCONCLUSIVE
    assert "do not resolve to any discovered run" in result.summary


def test_ed006_fails_when_the_published_set_contains_a_run_the_project_excluded() -> None:
    kept = [included_run("F/f/run_0"), excluded_run("F/f/run_1", attested("oom", "log.txt"))]
    record = membership_record(member_run_ids=[run.run_id for run in kept])
    result = one(AggregationMembershipProvenance(), project_with(kept, make_family(), [record]))
    assert result.status is RuleStatus.FAIL
    assert result.severity is Severity.HIGH


def test_ed006_accepts_excluded_members_inside_a_labelled_alternative_record() -> None:
    kept = [included_run("F/f/run_0"), excluded_run("F/f/run_1", attested("oom", "log.txt"))]
    record = membership_record(
        aggregation_id="F/f/-elbo@all_completed",
        member_run_ids=[run.run_id for run in kept],
    )
    result = one(AggregationMembershipProvenance(), project_with(kept, make_family(), [record]))
    assert result.status is RuleStatus.PASS
    assert any("alternative membership" in item for item in result.limitations)


def test_ed006_not_applicable_without_a_published_number() -> None:
    record = make_aggregation(member_run_ids=["F/f/run_0"])
    result = one(
        AggregationMembershipProvenance(),
        project_with([included_run("F/f/run_0")], make_family(), [record]),
    )
    assert result.status is RuleStatus.NOT_APPLICABLE


# --------------------------------------------------------- ED007 aggregation math


def recompute_project(**overrides: object) -> ExperimentProject:
    runs = [
        make_run(f"F/f/run_{i}", metrics=[metric("-elbo", value)])
        for i, value in enumerate((1.0, 2.0, 3.0))
    ]
    fields: dict[str, object] = {
        "member_run_ids": [run.run_id for run in runs],
        "reported_value": 2.0,
        "reported_source": SourceRef(path="table.md", line=4),
    }
    fields.update(overrides)
    return project_with(runs, make_family(), [make_aggregation(**fields)])


def test_ed007_passes_when_the_published_mean_recomputes() -> None:
    result = one(AggregationNumericalConsistency(), recompute_project())
    assert result.status is RuleStatus.PASS
    assert result.measurements["recomputed_value"] == 2.0
    assert result.measurements["n_values_aggregated"] == 3


def test_ed007_fails_when_the_published_mean_does_not_recompute() -> None:
    result = one(AggregationNumericalConsistency(), recompute_project(reported_value=2.5))
    assert result.status is RuleStatus.FAIL
    assert result.severity is Severity.HIGH
    assert "(mean differ)" in result.summary


def test_ed007_fails_when_only_the_published_spread_is_off() -> None:
    project = recompute_project(reported_spread=9.0, spread_tolerance=1e-2)
    result = one(AggregationNumericalConsistency(), project)
    assert result.status is RuleStatus.FAIL
    assert "(spread differ)" in result.summary


def test_ed007_is_inconclusive_for_a_reconstruction_with_nothing_published() -> None:
    result = one(AggregationNumericalConsistency(), recompute_project(reported_value=None))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert "no reported value to compare against" in " ".join(result.limitations)


def test_ed007_is_inconclusive_for_a_statistic_it_does_not_recompute() -> None:
    result = one(
        AggregationNumericalConsistency(),
        recompute_project(statistic="median", reported_value=None),
    )
    assert result.status is RuleStatus.INCONCLUSIVE
    assert "is not recomputed by v0.1" in " ".join(result.limitations)


def test_ed007_tolerance_is_reported_and_never_widened_by_the_rule() -> None:
    result = one(AggregationNumericalConsistency(), recompute_project(reported_value=2.4))
    assert result.measurements["value_tolerance"] == 1e-9
    assert "do not widen the tolerance" in (result.recommendation or "")


# ------------------------------------------------------------- ED008 spread meaning


def spread_project(**overrides: object) -> ExperimentProject:
    fields: dict[str, object] = {
        "metric_name": "-acc",
        "reported_value": 91.3,
        "reported_spread": 0.6,
        "spread_basis": SpreadBasis.STANDARD_DEVIATION,
        "reported_source": SourceRef(path="table.md", line=4),
    }
    fields.update(overrides)
    return project_with([], make_family(), [make_aggregation(**fields)])


def attested_spread(path: str, line: int | None = None) -> ProvenanceField[SpreadSemantics]:
    return attested(SpreadSemantics.STANDARD_DEVIATION, path, line)


def test_ed008_regression_population_std_called_std_passes() -> None:
    """Case A: a population std that the prose calls a standard deviation is consistent."""
    project = spread_project(
        std_ddof=0,
        implemented_spread=attested_spread("average_log.py", 132),
        documented_spread=attested(SpreadSemantics.STANDARD_DEVIATION, "README.md", 58),
    )
    result = one(SpreadSemanticsConsistency(), project)
    assert result.status is RuleStatus.PASS
    assert result.measurements["std_ddof"] == 0


def test_firewall_population_versus_sample_std_alone_is_never_a_failure() -> None:
    """ddof is a convention, not a claim; nothing here contradicts the project."""
    project = spread_project(
        std_ddof=0,
        implemented_spread=attested_spread("average_log.py", 132),
    )
    result = one(SpreadSemanticsConsistency(), project)
    assert result.status is RuleStatus.PASS
    assert result.measurements["documented_semantics"] == "unknown"


def test_ed008_regression_standard_error_claim_over_a_std_fails() -> None:
    """Case B: the TorchSSL shape - prose says standard error, code prints std."""
    project = spread_project(
        implemented_spread=attested_spread("average_log.py", 132),
        documented_spread=attested(SpreadSemantics.STANDARD_ERROR, "README.md", 58),
    )
    result = one(SpreadSemanticsConsistency(), project)
    assert result.status is RuleStatus.FAIL
    assert result.severity is Severity.HIGH
    assert "documents its +/- as standard_error" in result.summary
    assert any("sqrt(N)" in item for item in result.limitations)


def test_ed008_regression_a_bare_spread_with_no_claim_is_inconclusive() -> None:
    """Case C: a printed ``±0.1`` and nothing else cannot be identified."""
    result = one(SpreadSemanticsConsistency(), spread_project(reported_spread=0.1))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.severity is Severity.MEDIUM
    assert "identity is simply not recoverable" in " ".join(result.limitations)


def test_ed008_passes_on_an_implementation_only_scaled_standard_error() -> None:
    project = spread_project(
        spread_basis=SpreadBasis.STANDARD_ERROR,
        display_multiplier=3.0,
        implemented_spread=attested(SpreadSemantics.SCALED_STANDARD_ERROR, "fetch.py", 108),
    )
    result = one(SpreadSemanticsConsistency(), project)
    assert result.status is RuleStatus.PASS
    assert result.measurements["display_multiplier"] == 3.0


def test_ed008_fails_when_the_artifacts_disagree_about_the_same_spread() -> None:
    project = spread_project(
        implemented_spread=ProvenanceField.conflicting(
            [SourceRef(path="a.py", line=1), SourceRef(path="b.py", line=2)]
        ),
    )
    result = one(SpreadSemanticsConsistency(), project)
    assert result.status is RuleStatus.FAIL
    assert "mutually incompatible accounts" in result.summary


def test_ed008_inconclusive_when_only_prose_makes_the_claim() -> None:
    project = spread_project(
        documented_spread=attested(SpreadSemantics.CONFIDENCE_INTERVAL_HALF_WIDTH, "README.md")
    )
    result = one(SpreadSemanticsConsistency(), project)
    assert result.status is RuleStatus.INCONCLUSIVE


def test_ed008_not_applicable_when_no_spread_is_published() -> None:
    result = one(SpreadSemanticsConsistency(), spread_project(reported_spread=None))
    assert result.status is RuleStatus.NOT_APPLICABLE
    assert result.measurements == {"variant": "included"}


def test_ed008_findings_are_independent_of_the_arithmetic_comparison() -> None:
    """A cell whose spread recomputes within its own tolerance can still contradict its prose."""
    project = recompute_project(
        reported_spread=1.0,
        spread_tolerance=0.6,
        implemented_spread=attested_spread("average_log.py", 132),
        documented_spread=attested(SpreadSemantics.STANDARD_ERROR, "README.md", 58),
    )
    arithmetic = one(AggregationNumericalConsistency(), project)
    semantics = one(SpreadSemanticsConsistency(), project)
    assert arithmetic.status is RuleStatus.PASS
    assert semantics.status is RuleStatus.FAIL
    assert semantics.measurements["recomputed_spread"] is not None


# ---------------------------------------------------------------- ED009 termination


def test_ed009_passes_when_the_log_records_the_cap_that_stopped_the_run() -> None:
    run = make_run(
        "F/f/run_0",
        status=RunStatus.COMPLETED_INCLUDED,
        termination_cause=attested(TerminationCause.ITERATION_CAP, "F/f/run_0/log.txt", line=88),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    result = one(TerminationProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.PASS
    assert result.measurements["cause"] == "iteration_cap"


def test_ed009_passes_on_a_recorded_cause_and_notes_the_unrecorded_budget() -> None:
    run = make_run(
        "F/f/run_0",
        status=RunStatus.TRUNCATED_TIME_LIMIT,
        termination_cause=attested(TerminationCause.TIME_LIMIT, "F/f/run_0/log.txt", line=88),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    result = one(TerminationProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.PASS
    assert any("budget it stopped against is not" in item for item in result.limitations)


def test_ed009_inconclusive_when_nothing_states_why_the_run_ended() -> None:
    run = make_run("F/f/run_0", status=RunStatus.TRUNCATED_TIME_LIMIT)
    result = one(TerminationProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.INCONCLUSIVE
    assert any("does not mean the run failed" in item for item in result.limitations)


def test_ed009_fails_when_two_terminal_markers_contradict() -> None:
    run = make_run(
        "F/f/run_0",
        termination_cause=ProvenanceField.conflicting(
            [SourceRef(path="log.txt", line=88), SourceRef(path="err.txt", line=1)]
        ),
    )
    result = one(TerminationProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.FAIL


# --------------------------------------------------------------- ED010 environment


def test_ed010_passes_when_the_run_log_dumps_the_environment_it_loaded() -> None:
    run = make_run(
        "F/f/run_0",
        environment=attested("conda env dump: python 3.9 / torch 1.12", "F/f/run_0/log.txt", 2),
        compute_budget=attested("1x 3090, 6h", "F/f/run_0/log.txt", 9),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    result = one(RuntimeEnvironmentProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.PASS
    assert result.measurements["source_attached_to_run"] is True


def test_firewall_a_repository_environment_file_never_passes_runtime_provenance() -> None:
    run = make_run(
        "F/f/run_0",
        environment=attested("environment.yml", "environment.yml"),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    project = project_with(
        [run], make_family(), artifacts=[artifact("environment.yml", ArtifactType.ENVIRONMENT)]
    )
    result = one(RuntimeEnvironmentProvenance(), project)
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.measurements["declared_environment_files"] == 1
    assert "only established from a declaration outside the run" in result.summary


def test_ed010_inconclusive_when_only_a_declaration_exists() -> None:
    """Case A: an ``environment.yml`` in the repository establishes intent, not execution."""
    project = project_with(
        family_runs(1),
        make_family(),
        artifacts=[artifact("environment.yml", ArtifactType.ENVIRONMENT)],
    )
    result = one(RuntimeEnvironmentProvenance(), project)
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.measurements["declared_environment_files"] == 1
    assert (
        result.measurements["environment_relationship"]
        == EnvironmentRelationship.ONLY_DECLARED.value
    )
    assert result.measurements["runtime_evidence_recorded"] is False


def test_ed010_passes_when_runtime_record_matches_the_declaration() -> None:
    """Case B: a run-local record and the declaration agree on a shared pin."""
    run = make_run(
        "F/f/run_0",
        runtime_environment=RuntimeEnvironment(
            framework_versions=attested({"torch": "2.0"}, "F/f/run_0/log.txt", 3),
            source_artifacts=[SourceRef(path="F/f/run_0/log.txt", line=3)],
        ),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    project = project_with([run], make_family())
    project.declared_environments.append(
        DeclaredEnvironment(
            artifact_id="conda-pin",
            artifact_type=DeclaredEnvironmentType.ENVIRONMENT_YAML,
            source_path="environment.yml",
            declared_dependencies=attested({"torch": "2.0"}, "environment.yml"),
        )
    )
    result = one(RuntimeEnvironmentProvenance(), project)
    assert result.status is RuleStatus.PASS
    assert result.measurements["environment_relationship"] == EnvironmentRelationship.MATCHED.value


def test_ed010_fails_when_runtime_record_contradicts_the_declaration() -> None:
    """Case C: the log says torch 2.0, the declaration pins 1.7 — a checked contradiction."""
    run = make_run(
        "F/f/run_0",
        runtime_environment=RuntimeEnvironment(
            framework_versions=attested({"torch": "2.0"}, "F/f/run_0/log.txt", 3),
        ),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    project = project_with([run], make_family())
    project.declared_environments.append(
        DeclaredEnvironment(
            artifact_id="conda-pin",
            artifact_type=DeclaredEnvironmentType.ENVIRONMENT_YAML,
            source_path="environment.yml",
            declared_dependencies=attested({"torch": "1.7"}, "environment.yml"),
        )
    )
    result = one(RuntimeEnvironmentProvenance(), project)
    assert result.status is RuleStatus.FAIL
    assert (
        result.measurements["environment_relationship"] == EnvironmentRelationship.CONFLICTING.value
    )
    assert "torch" in result.summary


def test_ed010_not_applicable_when_no_environment_evidence_exists() -> None:
    """Case D: nothing records an environment and no declaration exists to check."""
    project = project_with(family_runs(1), make_family())
    result = one(RuntimeEnvironmentProvenance(), project)
    assert result.status is RuleStatus.NOT_APPLICABLE
    assert result.severity is Severity.INFO
    assert result.measurements["environment_relationship"] == EnvironmentRelationship.UNKNOWN.value


def test_firewall_requirements_pins_never_confirm_executed_dependencies() -> None:
    run = make_run(
        "F/f/run_0",
        runtime_environment=RuntimeEnvironment(
            framework_versions=attested(
                {"torch": "1.12"}, "requirements.txt", status=ProvenanceStatus.SUPPORTED
            ),
            source_artifacts=[SourceRef(path="requirements.txt")],
        ),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    project = project_with(
        [run], make_family(), artifacts=[artifact("requirements.txt", ArtifactType.ENVIRONMENT)]
    )
    result = one(RuntimeEnvironmentProvenance(), project)
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.measurements["runtime_evidence_recorded"] is False


def test_firewall_slurm_template_never_proves_actual_hardware() -> None:
    run = make_run(
        "F/f/run_0",
        runtime_environment=RuntimeEnvironment(
            hardware=attested("4x A100", "templates/submit.slurm"),
            source_artifacts=[SourceRef(path="templates/submit.slurm")],
        ),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    project = project_with(
        [run],
        make_family(),
        artifacts=[artifact("templates/submit.slurm", ArtifactType.ENVIRONMENT)],
    )
    result = one(RuntimeEnvironmentProvenance(), project)
    assert result.status is RuleStatus.INCONCLUSIVE
    assert (
        result.measurements["environment_relationship"]
        == EnvironmentRelationship.ONLY_DECLARED.value
    )


def test_firewall_dockerfile_never_proves_the_container_that_ran() -> None:
    run = make_run(
        "F/f/run_0",
        runtime_environment=RuntimeEnvironment(
            os=attested("debian 11", "Dockerfile"),
            python_version=attested("3.9", "Dockerfile"),
            source_artifacts=[SourceRef(path="Dockerfile")],
        ),
        artifacts=[artifact("F/f/run_0/log.txt")],
    )
    project = project_with(
        [run], make_family(), artifacts=[artifact("Dockerfile", ArtifactType.ENVIRONMENT)]
    )
    result = one(RuntimeEnvironmentProvenance(), project)
    assert result.status is RuleStatus.INCONCLUSIVE


def test_firewall_matched_is_never_inferred_from_disjoint_or_missing_versions() -> None:
    slot = RuntimeEnvironment(framework_versions=attested({"torch": "2.0"}, "F/f/run_0/log.txt"))
    disjoint = DeclaredEnvironment(
        artifact_id="pin",
        artifact_type=DeclaredEnvironmentType.REQUIREMENTS,
        source_path="requirements.txt",
        declared_dependencies=attested({"python": "3.7"}, "requirements.txt"),
    )
    unpinned = DeclaredEnvironment(
        artifact_id="tpl",
        artifact_type=DeclaredEnvironmentType.SLURM_TEMPLATE,
        source_path="submit.slurm",
    )
    assert (
        RunEnvironmentBinding.build("F/f/run_0", slot, disjoint).relationship_status
        is EnvironmentRelationship.UNKNOWN
    )
    assert (
        RunEnvironmentBinding.build("F/f/run_0", slot, unpinned).relationship_status
        is EnvironmentRelationship.UNKNOWN
    )
    assert (
        RunEnvironmentBinding.build("F/f/run_0", slot, None).relationship_status
        is EnvironmentRelationship.ONLY_RUNTIME
    )


def test_environment_schema_additions_keep_old_json_readable() -> None:
    """Every refinement field is optional: a pre-refinement scan record still validates."""
    run_payload = make_run("F/f/run_0").model_dump(mode="json")
    del run_payload["runtime_environment"]
    assert ExperimentRun.model_validate(run_payload).runtime_environment is None
    artifact_payload = ArtifactRef(path="x.log").model_dump(mode="json")
    del artifact_payload["artifact_role"]
    assert ArtifactRef.model_validate(artifact_payload).artifact_role is None
    project_payload = ExperimentProject(root="u", project_id="u", adapter="u").model_dump(
        mode="json"
    )
    del project_payload["declared_environments"]
    assert ExperimentProject.model_validate(project_payload).declared_environments == []


def test_environment_artifact_role_counts_as_a_declaration() -> None:
    role_artifact = ArtifactRef(
        path="locks/pip.lock",
        artifact_type=ArtifactType.SUMMARY,
        artifact_role=ArtifactRole.DECLARED_ENVIRONMENT,
    )
    project = project_with(family_runs(1), make_family(), artifacts=[role_artifact])
    result = one(RuntimeEnvironmentProvenance(), project)
    assert result.status is RuleStatus.INCONCLUSIVE
    assert result.measurements["declared_environment_files"] == 1


def test_ed010_fails_on_two_mutually_exclusive_environment_records() -> None:
    run = make_run(
        "F/f/run_0",
        environment=ProvenanceField.conflicting([SourceRef(path="a.txt"), SourceRef(path="b.txt")]),
    )
    result = one(RuntimeEnvironmentProvenance(), project_with([run], make_family()))
    assert result.status is RuleStatus.FAIL


# ------------------------------------------------------------- engine contracts


def test_registry_holds_exactly_ten_general_rules() -> None:
    assert [rule.rule_id for rule in RULES] == [f"ED{n:03d}" for n in range(1, 11)]
    assert {rule.entity_type for rule in RULES} == {"family", "run", "aggregation"}
    assert all(rule.purpose and rule.title for rule in RULES)


def test_run_rules_reports_a_failing_rule_as_not_run_rather_than_losing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Broken(Rule):
        rule_id = "ED099"
        title = "Broken"
        purpose = "test only"
        entity_type = "run"

        def evaluate(self, context: RuleContext) -> list[RuleResult]:
            raise RuntimeError("boom")

    project = project_with(family_runs(1), make_family())
    context, audit = context_of(project)
    monkeypatch.setattr("experiment_doctor.rules.RULES", (Broken(),))
    produced = run_rules(project, audit)
    assert [item.status for item in produced] == [RuleStatus.NOT_RUN]
    assert produced[0].severity is Severity.MEDIUM


def test_no_result_of_the_synthetic_set_names_an_accusation() -> None:
    runs = [
        make_run(
            f"F/f/run_{i}",
            seed=ProvenanceField.unknown(),
            included_in_aggregation=attested(i < 2, "meta.json"),
            resolved_config=attested({"lr": "1e-3"}, "meta.json"),
            method=attested("VAE", "meta.json"),
        )
        for i in range(3)
    ]
    record = membership_record(
        member_run_ids=["F/f/run_0", "F/f/run_1"],
        excluded_run_ids=["F/f/run_2"],
        reported_spread=0.5,
    )
    project = project_with(runs, make_family(), [record])
    for result in run_rules(project, audit_project(project)):
        for label in FORBIDDEN_LABELS:
            assert label not in texts(result), f"{result.rule_id}: {label}"


def test_uncertain_results_are_never_calibrated_as_high_severity() -> None:
    runs = [make_run(f"F/f/run_{i}") for i in range(2)]
    project = project_with(runs, make_family(), [make_aggregation()])
    for result in run_rules(project, audit_project(project)):
        if result.status in (RuleStatus.INCONCLUSIVE, RuleStatus.NOT_RUN):
            assert result.severity is Severity.MEDIUM, result
        elif result.status is RuleStatus.PASS:
            assert result.severity is Severity.INFO, result
        elif result.status is RuleStatus.NOT_APPLICABLE:
            assert result.severity is Severity.INFO, result


def test_status_counts_are_counts_without_a_score() -> None:
    project = project_with(family_runs(2), make_family())
    counts = status_counts(run_rules(project, audit_project(project)))
    assert set(counts) == {rule.rule_id for rule in RULES}
    assert all(set(row) == {status.value for status in RuleStatus} for row in counts.values())
    assert not any(key.startswith(("score", "verdict", "risk")) for key in counts)


def test_each_rule_emits_exactly_one_result_per_entity_of_its_own_kind() -> None:
    """Entity granularity: family rules once per family, run and aggregation rules likewise."""
    runs = [make_run(f"F/f/run_{i}", seed=evidenced_seed(i)) for i in range(2)]
    record = make_aggregation(reported_spread=0.5)
    project = project_with(runs, make_family(), [record])
    context, _ = context_of(project)
    expected = {
        "family": [project.families[0].family_id],
        "run": [run.run_id for run in project.runs],
        "aggregation": [project.aggregations[0].aggregation_id],
    }
    for rule in RULES:
        results = rule.evaluate(context)
        assert {item.rule_id for item in results} == {rule.rule_id}
        assert {item.entity_type for item in results} == {rule.entity_type}
        assert sorted(item.entity_id for item in results) == sorted(expected[rule.entity_type])


def test_audit_and_rules_agree_on_what_a_published_cell_claims() -> None:
    """The rules read the records the audit produced, not a second copy of the project."""
    project = recompute_project(
        reported_spread=1.0,
        spread_tolerance=0.6,
        implemented_spread=attested_spread("average_log.py", 132),
        documented_spread=attested(SpreadSemantics.STANDARD_ERROR, "README.md", 58),
    )
    context, audit = context_of(project)
    record = project.aggregations[0]
    assert audit.recomputation[0].comparison_status is ComparisonStatus.MATCH
    assert AggregationNumericalConsistency().evaluate(context)[0].status is RuleStatus.PASS
    assert SpreadSemanticsConsistency().evaluate(context)[0].status is RuleStatus.FAIL
    assert record.recomputed_spread is not None
