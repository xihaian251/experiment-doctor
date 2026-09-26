"""ED007 - does the reported aggregate come back out of the member runs' numbers?

The comparison is arithmetic only.  Values are floats compared against an explicit
tolerance derived from how many digits the project printed; no status in this rule
depends on a string match.
"""

from __future__ import annotations

from typing import Any, ClassVar

from experiment_doctor.rules.base import MEASUREMENT, Rule, RuleContext, RuleResult, RuleStatus
from experiment_doctor.schema import ComparisonStatus, Severity


class AggregationNumericalConsistency(Rule):
    rule_id: ClassVar[str] = "ED007"
    title: ClassVar[str] = "Aggregation Numerical Consistency"
    purpose: ClassVar[str] = "Can the published mean and spread be recomputed from the runs?"
    entity_type: ClassVar[str] = "aggregation"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        return [self._one(record) for record in context.project.aggregations]

    def _one(self, record: Any) -> RuleResult:
        measurements: dict[str, MEASUREMENT] = {
            "n_members": len(record.member_run_ids),
            "n_values_aggregated": record.n,
            "statistic": record.statistic,
            "std_ddof": record.std_ddof,
            "display_multiplier": record.display_multiplier,
            "reported_value": record.reported_value,
            "recomputed_value": record.recomputed_value,
            "reported_spread": record.reported_spread,
            "recomputed_spread": record.recomputed_spread,
            "value_tolerance": record.tolerance,
            "spread_tolerance": record.spread_tolerance,
        }
        evidence = [
            f"N: {len(record.member_run_ids)} members, {record.n} metric values recovered",
            f"reported: {record.reported_value} +/- {record.reported_spread} at "
            f"{record.reported_source.describe() if record.reported_source else '-'}",
            f"recomputed: {record.recomputed_value} +/- {record.recomputed_spread} "
            f"(statistic={record.statistic}, ddof={record.std_ddof}, "
            f"multiplier={record.display_multiplier}, basis={record.spread_basis.value})",
            f"tolerance: value {record.tolerance:g}, spread {record.spread_tolerance:g}",
        ]
        status = record.comparison_status

        if status is ComparisonStatus.MATCH:
            return self.result(
                record.aggregation_id,
                RuleStatus.PASS,
                f"the published {record.statistic} and its spread recompute from the "
                f"{record.n} member values inside the printed precision",
                evidence=evidence,
                measurements=measurements,
            )
        if status is ComparisonStatus.MISMATCH:
            which = []
            if record.reported_value is not None and record.recomputed_value is not None:
                if abs(record.reported_value - record.recomputed_value) > record.tolerance:
                    which.append("mean")
            if record.reported_spread is not None and record.recomputed_spread is not None:
                if abs(record.reported_spread - record.recomputed_spread) > record.spread_tolerance:
                    which.append("spread")
            return self.result(
                record.aggregation_id,
                RuleStatus.FAIL,
                "the reported aggregation does not match the value recomputed from its member runs"
                + (f" ({', '.join(which)} differ)" if which else ""),
                evidence=evidence,
                measurements=measurements,
                recommendation="identify which membership, reduction or sign convention differs; "
                "do not widen the tolerance to force agreement",
            )
        return self.result(
            record.aggregation_id,
            RuleStatus.INCONCLUSIVE,
            "one of the four inputs this comparison needs is missing, so the published number "
            "can be neither confirmed nor refuted",
            evidence=evidence,
            measurements=measurements,
            limitations=[
                _missing_inputs(record),
            ],
            recommendation="publish the member values or the aggregate's inputs alongside the "
            "rounded result",
        )


def _missing_inputs(record: Any) -> str:
    missing: list[str] = []
    if not record.has_reported:
        missing.append("no reported value to compare against")
    if record.reported_spread is None:
        missing.append("no reported spread")
    if not record.values:
        missing.append("no member metric values recovered")
    if record.statistic != "mean":
        missing.append(f"statistic '{record.statistic}' is not recomputed by v0.1")
    if record.recomputed_spread is None and record.n > 0:
        missing.append("spread undefined for this N and ddof")
    return "; ".join(missing) or "the recomputation produced no comparable quantity"
