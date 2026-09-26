"""ED010 - can the software and hardware a historical run executed on be established?

A dependency file in the repository states what the author intended to install.  It
cannot show what was installed on the machine that ran the job months ago, so a
declaration never produces PASS here; only a value read out of the run's own artifact
does.
"""

from __future__ import annotations

from typing import Any, ClassVar

from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.rules.base import Rule, RuleContext, RuleResult, RuleStatus, attached_to_run
from experiment_doctor.schema import ArtifactType, ExperimentProject, Severity

_RECORDED = (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED)


class RuntimeEnvironmentProvenance(Rule):
    rule_id: ClassVar[str] = "ED010"
    title: ClassVar[str] = "Runtime Environment Provenance"
    purpose: ClassVar[str] = "Is the environment the run executed in recorded by the run?"
    entity_type: ClassVar[str] = "run"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        declarations = _declaration_paths(context.project)
        return [self._one(run, declarations) for run in context.project.runs]

    def _one(self, run: Any, declarations: list[str]) -> RuleResult:
        environment = run.environment
        source = environment.source.describe() if environment.source else "-"
        attached = attached_to_run(run, environment.source)
        measurements = {
            "environment_status": environment.status.value,
            "source_attached_to_run": attached is not None,
            "declared_environment_files": len(declarations),
            "compute_budget_status": run.compute_budget.status.value,
        }
        declaration_evidence = (
            [f"repository-level declarations present: {', '.join(declarations[:5])}"]
            if declarations
            else ["no dependency declaration was found anywhere in the repository"]
        )

        if environment.status is ProvenanceStatus.CONFLICTING:
            return self.result(
                run.run_id,
                RuleStatus.FAIL,
                "the artifacts state mutually exclusive runtime environments for this run",
                evidence=[f"environment is CONFLICTING between: {source}"],
                measurements=measurements,
                recommendation="keep one environment record per run, emitted by the process itself",
            )

        if environment.status in _RECORDED and attached is not None:
            hardware = run.compute_budget
            limitations = []
            if hardware.status not in _RECORDED:
                limitations.append("no artifact records the hardware or the compute budget")
            return self.result(
                run.run_id,
                RuleStatus.PASS,
                f"the run's own {attached.lower()} artifact records the environment it ran in",
                evidence=[
                    f"environment: {environment.value} ({environment.status.value}) at {source}"
                ],
                measurements=measurements,
                limitations=limitations,
            )

        limitations = [
            "a dependency file in the repository describes intended versions; it cannot show which "
            "versions a historical run actually loaded",
            "UNKNOWN here means the run recorded nothing about its environment, not that the "
            "environment was wrong or unreproducible",
        ]
        if attached is None and environment.value is not None:
            summary = "the environment is only established from a declaration outside the run's own artifacts"
        else:
            summary = "no artifact records the environment this run executed in"
        return self.result(
            run.run_id,
            RuleStatus.INCONCLUSIVE,
            summary,
            evidence=[
                f"environment: {environment.value or '-'} ({environment.status.value}) at {source}",
                *declaration_evidence,
            ],
            measurements=measurements,
            limitations=limitations,
            recommendation="have the runner print interpreter, library, accelerator and device "
            "identity into the log it writes for that run",
        )


def _declaration_paths(project: ExperimentProject) -> list[str]:
    return sorted(
        {
            artifact.path
            for artifact in project.artifacts
            if artifact.artifact_type is ArtifactType.ENVIRONMENT
        }
    )
