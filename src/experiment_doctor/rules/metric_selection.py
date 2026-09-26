"""ED005 - is the published metric's selection policy recoverable and honoured?

A run's best value and its last value are different quantities, and a project may
publish either.  This rule therefore treats ``best != last`` as a measurement to be
reported, never as a defect: it only fails when the claim about which one was
published contradicts the code that produced the number.
"""

from __future__ import annotations

from typing import Any, ClassVar

from experiment_doctor.rules.base import (
    MEASUREMENT,
    Rule,
    RuleContext,
    RuleResult,
    RuleStatus,
    claim_comparison,
)
from experiment_doctor.schema import Severity

BEST_SUFFIX = "@best"
LAST_SUFFIX = "@last"


class MetricSelectionProvenance(Rule):
    rule_id: ClassVar[str] = "ED005"
    title: ClassVar[str] = "Metric Selection Provenance"
    purpose: ClassVar[str] = "Which observation of a run does the reported metric stand for?"
    entity_type: ClassVar[str] = "aggregation"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        return [self._one(record, context) for record in context.project.aggregations]

    def _one(self, record: Any, context: RuleContext) -> RuleResult:
        if record.reported_value is None:
            return self.result(
                record.aggregation_id,
                RuleStatus.NOT_APPLICABLE,
                "this record is a reconstruction; the project published no number for it",
                measurements={"metric": record.metric_name, "variant": record.variant},
                limitations=[
                    "with nothing reported there is no selection claim to hold against the code"
                ],
            )

        implemented = record.implemented_selection
        documented = record.documented_selection
        kind = claim_comparison(implemented, documented)
        measurements: dict[str, MEASUREMENT] = {
            "metric": record.metric_name,
            "variant": record.variant,
            "reported_value": record.reported_value,
            "implemented_selection": _name(implemented.value),
            "documented_selection": _name(documented.value),
        }
        measurements.update(_selection_deltas(context, record))
        evidence = [
            f"reported: {record.reported_value} at "
            f"{record.reported_source.describe() if record.reported_source else '-'}",
            f"aggregation code selects: {_name(implemented.value)} "
            f"({implemented.status.value})"
            + (f" at {implemented.source.describe()}" if implemented.source else ""),
            f"project prose claims: {_name(documented.value)} ({documented.status.value})"
            + (f" at {documented.source.describe()}" if documented.source else ""),
        ]

        if kind == "conflicting-evidence":
            return self.result(
                record.aggregation_id,
                RuleStatus.FAIL,
                "the artifacts disagree about which observation of each run was published",
                evidence=evidence,
                measurements=measurements,
                recommendation="state the selection rule next to the number it produced",
            )
        if kind == "contradiction":
            return self.result(
                record.aggregation_id,
                RuleStatus.FAIL,
                f"the project documents {documented.value.value} values but its aggregation "
                f"code consumes {implemented.value.value} values",
                evidence=evidence,
                measurements=measurements,
                limitations=[
                    "the two quantities differ per run wherever the metric is tracked to an "
                    "extremum; the size of the difference is reported as a measurement"
                ],
                recommendation="align the prose with the aggregation code, or publish both quantities",
            )
        if kind in ("undetermined", "documentation-only"):
            return self.result(
                record.aggregation_id,
                RuleStatus.INCONCLUSIVE,
                "a single number is published and the artifacts do not show which observation of "
                "each run it came from",
                evidence=evidence,
                measurements=measurements,
                limitations=[
                    "INCONCLUSIVE here is an evidence gap: nothing suggests the wrong value was taken"
                ],
                recommendation="label each reported cell with the policy that produced it "
                "(best, last, or the step it was read at)",
            )
        if kind == "implementation-only":
            return self.result(
                record.aggregation_id,
                RuleStatus.PASS,
                f"the aggregation code fixes the policy as {implemented.value.value}; "
                "the project never states one in prose, so there is nothing to contradict",
                evidence=evidence,
                measurements=measurements,
                limitations=["the policy is known only from the code that produced the number"],
            )
        limitations = []
        if isinstance(measurements.get("best_minus_last"), float):
            limitations.append(
                "best and last are not equal for these runs; the difference is a property of the "
                "metric, not of this claim"
            )
        return self.result(
            record.aggregation_id,
            RuleStatus.PASS,
            f"the published number is the {implemented.value.value} value of each member run, "
            "as the project documents",
            evidence=evidence,
            measurements=measurements,
            limitations=limitations,
        )


def _name(value: Any) -> str:
    return str(getattr(value, "value", value if value is not None else "unknown"))


def _selection_deltas(context: RuleContext, record: Any) -> dict[str, MEASUREMENT]:
    """Mean of the best-selected and last values over the same members, when both exist.

    A measurement only: it never enters the status computation.
    """
    best_name = f"{record.metric_name.split('@')[0]}{BEST_SUFFIX}"
    last_name = f"{record.metric_name.split('@')[0]}{LAST_SUFFIX}"
    best: list[float] = []
    last: list[float] = []
    for run_id in record.member_run_ids:
        run = context.run(run_id)
        if run is None:
            continue
        for name, bucket in ((best_name, best), (last_name, last)):
            metric = run.metric(name)
            value = metric.value.value if metric is not None else None
            if value is not None:
                bucket.append(float(value))
    if len(best) < 2 or len(last) < 2 or len(best) != len(last):
        return {}
    delta = round(sum(best) / len(best) - sum(last) / len(last), 6)
    return {
        "family_best_mean": round(sum(best) / len(best), 6),
        "family_last_mean": round(sum(last) / len(last), 6),
        "best_minus_last": delta,
    }
