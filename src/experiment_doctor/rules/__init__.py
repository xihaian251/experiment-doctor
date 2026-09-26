"""The v0.1 formal rule set: ten rules, one registry, no scheduler.

Order is by rule id.  Rules are plain objects evaluated in sequence over one
scanned project; there is no dependency graph, no plugin discovery and no dynamic
entry point, because ten rules do not need any of that.
"""

from __future__ import annotations

from collections import Counter

from experiment_doctor.audit import AuditResult
from experiment_doctor.rules.aggregation_consistency import AggregationNumericalConsistency
from experiment_doctor.rules.base import Rule, RuleContext, RuleResult, RuleStatus
from experiment_doctor.rules.code_provenance import HistoricalCodeProvenance
from experiment_doctor.rules.config_provenance import ResolvedConfigurationProvenance
from experiment_doctor.rules.environment import RuntimeEnvironmentProvenance
from experiment_doctor.rules.identity import RunIdentityConsistency
from experiment_doctor.rules.membership import AggregationMembershipProvenance
from experiment_doctor.rules.metric_selection import MetricSelectionProvenance
from experiment_doctor.rules.seeds import SeedProvenanceIntegrity
from experiment_doctor.rules.spread_semantics import SpreadSemanticsConsistency
from experiment_doctor.rules.termination import TerminationProvenance
from experiment_doctor.schema import ExperimentProject

RULES: tuple[Rule, ...] = (
    RunIdentityConsistency(),
    SeedProvenanceIntegrity(),
    HistoricalCodeProvenance(),
    ResolvedConfigurationProvenance(),
    MetricSelectionProvenance(),
    AggregationMembershipProvenance(),
    AggregationNumericalConsistency(),
    SpreadSemanticsConsistency(),
    TerminationProvenance(),
    RuntimeEnvironmentProvenance(),
)


#: Rules evaluated per project; a rule that raises is reported as NOT_RUN rather than
#: silently disappearing from the output.
def run_rules(project: ExperimentProject, audit: AuditResult) -> list[RuleResult]:
    context = RuleContext(project=project, audit=audit)
    results: list[RuleResult] = []
    for rule in RULES:
        try:
            results.extend(rule.evaluate(context))
        except Exception as exc:
            results.append(
                rule.result(
                    project.project_id,
                    RuleStatus.NOT_RUN,
                    f"the rule could not be evaluated on this project ({type(exc).__name__})",
                    evidence=[str(exc)],
                )
            )
    return results


def rule_catalog() -> list[dict[str, str]]:
    return [rule.describe() for rule in RULES]


def status_counts(results: list[RuleResult]) -> dict[str, dict[str, int]]:
    """Per-rule counts of each status.  Deliberately counts only: no weighted score."""
    per_rule: dict[str, dict[str, int]] = {}
    for rule in RULES:
        counts = Counter(
            result.status.value for result in results if result.rule_id == rule.rule_id
        )
        per_rule[rule.rule_id] = {
            status.value: counts.get(status.value, 0) for status in RuleStatus
        }
    return per_rule


__all__ = [
    "RULES",
    "Rule",
    "RuleContext",
    "RuleResult",
    "RuleStatus",
    "rule_catalog",
    "run_rules",
    "status_counts",
]
