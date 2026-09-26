"""ED008 - what is the quantity after the ``±``, and does the project say the same thing twice?

This is the rule a published table can violate without any number in it being wrong:
the central value may recompute perfectly while the spread is a standard deviation
described in prose as a standard error.  Population versus sample standard deviation
is *not* by itself a defect; only a mismatch between what a project says the ``±`` is
and what its code computes counts as one.
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


class SpreadSemanticsConsistency(Rule):
    rule_id: ClassVar[str] = "ED008"
    title: ClassVar[str] = "Spread Semantics Consistency"
    purpose: ClassVar[str] = "Does the published +/- mean what the project's prose says it means?"
    entity_type: ClassVar[str] = "aggregation"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        return [self._one(record) for record in context.project.aggregations]

    def _one(self, record: Any) -> RuleResult:
        if record.reported_spread is None:
            return self.result(
                record.aggregation_id,
                RuleStatus.NOT_APPLICABLE,
                "no +/- accompanies this number, so there is no spread claim to check",
                measurements={"variant": record.variant},
            )

        implemented = record.implemented_spread
        documented = record.documented_spread
        kind = claim_comparison(implemented, documented)
        measurements: dict[str, MEASUREMENT] = {
            "reported_spread": record.reported_spread,
            "recomputed_spread": record.recomputed_spread,
            "implemented_semantics": _name(implemented.value),
            "documented_semantics": _name(documented.value),
            "std_ddof": record.std_ddof,
            "display_multiplier": record.display_multiplier,
            "n": record.n,
            "spread_basis": record.spread_basis.value,
        }
        evidence = [
            f"the +/- published here is {record.reported_spread}",
            f"aggregation code computes: {_name(implemented.value)} ({implemented.status.value})"
            + (f" at {implemented.source.describe()}" if implemented.source else ""),
            f"project prose states: {_name(documented.value)} ({documented.status.value})"
            + (f" at {documented.source.describe()}" if documented.source else ""),
            f"declared recomputation basis: {record.spread_basis.value} with multiplier "
            f"{record.display_multiplier} over N={record.n}",
        ]

        if kind == "conflicting-evidence":
            return self.result(
                record.aggregation_id,
                RuleStatus.FAIL,
                "the artifacts give mutually incompatible accounts of what the +/- is",
                evidence=evidence,
                measurements=measurements,
                recommendation="keep one definition of the spread, in the code that prints it",
            )
        if kind == "contradiction":
            return self.result(
                record.aggregation_id,
                RuleStatus.FAIL,
                f"the project documents its +/- as {documented.value.value} while the aggregation "
                f"code computes {implemented.value.value}",
                evidence=evidence,
                measurements=measurements,
                limitations=[
                    "the central value of this cell is not in question; only the meaning of the "
                    "spread is, and the two readings differ by a factor of sqrt(N)"
                ],
                recommendation="either relabel the published spread or divide it by sqrt(N) in "
                "the aggregation, so the prose and the printed number describe the same quantity",
            )
        if kind in ("undetermined", "documentation-only"):
            return self.result(
                record.aggregation_id,
                RuleStatus.INCONCLUSIVE,
                "a spread is published but neither the code that produced it nor any statement "
                "fixes what it measures",
                evidence=evidence,
                measurements=measurements,
                limitations=[
                    "INCONCLUSIVE is not a criticism of the spread's size: its identity is simply "
                    "not recoverable from these artifacts"
                ],
                recommendation="state the spread's definition (standard deviation, standard error, "
                "interval half-width) wherever the +/- is printed",
            )
        if kind == "implementation-only":
            return self.result(
                record.aggregation_id,
                RuleStatus.PASS,
                f"the +/- is {implemented.value.value} per the code that printed it, and the "
                "project makes no contrary statement about it",
                evidence=evidence,
                measurements=measurements,
                limitations=[
                    "the meaning of the spread is established only by the aggregation code"
                ],
            )
        return self.result(
            record.aggregation_id,
            RuleStatus.PASS,
            f"the published +/- is what the project says it is: {implemented.value.value}",
            evidence=evidence,
            measurements=measurements,
        )


def _name(value: Any) -> str:
    return str(getattr(value, "value", value if value is not None else "unknown"))
