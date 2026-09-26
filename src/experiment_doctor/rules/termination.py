"""ED009 - does an artifact say why this run stopped?"""

from __future__ import annotations

from typing import Any, ClassVar

from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.rules.base import Rule, RuleContext, RuleResult, RuleStatus
from experiment_doctor.schema import RunStatus, Severity, TerminationCause

#: A cause read out of a log line is evidence; a cause inferred from the shape of a
#: history is not, and stays inconclusive.
_RECORDED = (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED)


class TerminationProvenance(Rule):
    rule_id: ClassVar[str] = "ED009"
    title: ClassVar[str] = "Termination Provenance"
    purpose: ClassVar[str] = "Is the reason a run ended recorded in its artifacts?"
    entity_type: ClassVar[str] = "run"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        return [self._one(run) for run in context.project.runs]

    def _one(self, run: Any) -> RuleResult:
        cause = run.termination_cause
        value = cause.value.value if cause.value is not None else None
        measurements = {
            "termination_status": cause.status.value,
            "cause": value,
            "run_status": run.status.value,
            "budget_status": run.compute_budget.status.value,
        }
        evidence = [
            f"termination_cause: {value if value is not None else '-'} ({cause.status.value})"
            + (f" at {cause.source.describe()}" if cause.source else ""),
        ]
        if cause.confidence_note:
            evidence.append(str(cause.confidence_note))

        if cause.status is ProvenanceStatus.CONFLICTING:
            return self.result(
                run.run_id,
                RuleStatus.FAIL,
                "the artifacts state mutually exclusive reasons for this run ending",
                evidence=evidence,
                measurements=measurements,
                recommendation="keep one terminal marker per run that matches how it actually stopped",
            )

        if cause.status in _RECORDED and cause.value not in (None, TerminationCause.UNKNOWN):
            limitations = []
            if run.status is RunStatus.TRUNCATED_TIME_LIMIT:
                limitations.append(
                    "the run is marked truncated by a time limit: its final value is a measurement "
                    "of an unfinished schedule, which this rule records without judging it"
                )
            if run.compute_budget.status not in _RECORDED:
                limitations.append(
                    "the cause of the stop is recorded, but the budget it stopped against is not"
                )
            return self.result(
                run.run_id,
                RuleStatus.PASS,
                f"the run's artifacts record why it stopped: {value}",
                evidence=evidence,
                measurements=measurements,
                limitations=limitations,
            )

        limitations = [
            "UNKNOWN here means no artifact states why the run ended; it does not mean the run "
            "failed, was stopped early or was abandoned"
        ]
        if run.status is RunStatus.TRUNCATED_TIME_LIMIT:
            limitations.append(
                "this run carries a time-limit status marker, which is a label on the result slot "
                "rather than a record of the process that ended"
            )
        return self.result(
            run.run_id,
            RuleStatus.INCONCLUSIVE,
            "no artifact records why this run ended",
            evidence=evidence + [f"run status: {run.status.value}"],
            measurements=measurements,
            limitations=limitations,
            recommendation="write the exit condition (cap reached, deadline, crash, manual stop) "
            "into the run's own log at the moment it happens",
        )
