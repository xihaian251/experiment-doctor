"""ED003 - can a run be bound to the code revision that actually executed?"""

from __future__ import annotations

from typing import Any, ClassVar

from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.rules.base import Rule, RuleContext, RuleResult, RuleStatus, attached_to_run
from experiment_doctor.schema import Severity

#: Absence of a revision is a documentation gap about the past, not an experimental error,
#: so the inconclusive branch is capped at MEDIUM.
_REVISION_SOURCES = (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED)


class HistoricalCodeProvenance(Rule):
    rule_id: ClassVar[str] = "ED003"
    title: ClassVar[str] = "Historical Code Provenance"
    purpose: ClassVar[str] = "Does an artifact identify the code revision this run executed?"
    entity_type: ClassVar[str] = "run"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        return [self._one(run) for run in context.project.runs]

    def _one(self, run: Any) -> RuleResult:
        commit = run.code_commit
        measurements = {
            "commit_status": commit.status.value,
            "has_revision": commit.has_value,
            "dirty_status": run.code_dirty.status.value,
        }
        limitations = [
            "a repository's present checkout describes the code available today, not the code that "
            "ran, and this rule never substitutes one for the other"
        ]
        if run.code_dirty.status is ProvenanceStatus.UNKNOWN:
            limitations.append(
                "the working-tree state of the training machine is not recorded anywhere either"
            )

        if commit.status is ProvenanceStatus.CONFLICTING:
            return self.result(
                run.run_id,
                RuleStatus.FAIL,
                "the artifacts give mutually exclusive code revisions for this run",
                evidence=[
                    f"conflicting revision records: "
                    f"{commit.source.describe() if commit.source else '-'}",
                ],
                measurements=measurements,
                recommendation="keep one revision identifier per run, written by the runner itself",
            )

        if commit.status not in _REVISION_SOURCES or commit.value is None:
            note = f"; {commit.confidence_note}" if commit.confidence_note else ""
            return self.result(
                run.run_id,
                RuleStatus.INCONCLUSIVE,
                "historical code identity cannot be established from available artifacts",
                evidence=[
                    f"code_commit: {commit.status.value}{note}",
                    f"code_repository: {run.code_repository.value or '-'} "
                    f"({run.code_repository.status.value})",
                ],
                measurements=measurements,
                limitations=limitations,
                recommendation=(
                    "record the commit sha (and the dirty flag) inside the run's own artifact at "
                    "launch time"
                ),
            )

        attached = attached_to_run(run, commit.source)
        if attached is None:
            return self.result(
                run.run_id,
                RuleStatus.INCONCLUSIVE,
                "a revision is named, but not by anything this run produced",
                evidence=[
                    f"code_commit: {commit.value} ({commit.status.value}) at "
                    f"{commit.source.describe() if commit.source else '-'}",
                    "no artifact attached to this run carries that revision",
                ],
                measurements={**measurements, "source_kind": None},
                limitations=limitations,
                recommendation="write the revision into the run's own log or metadata file",
            )

        return self.result(
            run.run_id,
            RuleStatus.PASS,
            f"the run's own artifact records revision {commit.value}",
            evidence=[
                f"code_commit: {commit.value} ({commit.status.value}) at "
                f"{commit.source.describe() if commit.source else '-'}",
                f"code_dirty: {run.code_dirty.value} ({run.code_dirty.status.value})",
            ],
            measurements={**measurements, "source_kind": attached},
        )
