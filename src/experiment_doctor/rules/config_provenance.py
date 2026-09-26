"""ED004 - is the configuration a run actually trained under recoverable?"""

from __future__ import annotations

from typing import Any, ClassVar

from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.rules.base import Rule, RuleContext, RuleResult, RuleStatus, attached_to_run
from experiment_doctor.schema import Severity


class ResolvedConfigurationProvenance(Rule):
    rule_id: ClassVar[str] = "ED004"
    title: ClassVar[str] = "Resolved Configuration Provenance"
    purpose: ClassVar[str] = "Does a run-local artifact hold the effective configuration?"
    entity_type: ClassVar[str] = "run"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        return [self._one(run) for run in context.project.runs]

    def _one(self, run: Any) -> RuleResult:
        config = run.resolved_config
        source = config.source.describe() if config.source else "-"
        attached = attached_to_run(run, config.source)
        measurements = {
            "config_status": config.status.value,
            "keys_recovered": len(config.value) if isinstance(config.value, dict) else 0,
            "source_attached_to_run": attached is not None,
            "unrecorded_effective_parameters": len(run.unrecorded_effective_parameters),
        }
        limitations = []
        if run.unrecorded_effective_parameters:
            limitations.append(
                f"{len(run.unrecorded_effective_parameters)} effective parameter(s) the run never "
                "recorded are listed on the run object"
            )

        if config.status is ProvenanceStatus.CONFLICTING:
            return self.result(
                run.run_id,
                RuleStatus.FAIL,
                "the artifacts disagree about which configuration this run resolved",
                evidence=[f"resolved_config is CONFLICTING between: {source}"],
                measurements=measurements,
                limitations=limitations,
                recommendation="keep the effective configuration in one place per run",
            )

        if config.value is None:
            return self.result(
                run.run_id,
                RuleStatus.INCONCLUSIVE,
                "no effective configuration was recovered for this run",
                evidence=[
                    "resolved_config: UNKNOWN"
                    + (f" ({config.confidence_note})" if config.confidence_note else ""),
                    f"config_source: {run.config_source.value or '-'} "
                    f"({run.config_source.status.value})",
                ],
                measurements=measurements,
                limitations=limitations
                + [
                    "a configuration file that exists in the repository says what could be run, "
                    "not what was run"
                ],
                recommendation="dump the merged, post-override configuration into the run directory",
            )

        if attached is not None:
            return self.result(
                run.run_id,
                RuleStatus.PASS,
                f"the run's own {attached.lower()} artifact records the resolved configuration",
                evidence=[
                    f"resolved_config: {measurements['keys_recovered']} key(s) at {source}",
                    f"config_source: {run.config_source.value or '-'}",
                ],
                measurements=measurements,
                limitations=limitations,
            )

        return self.result(
            run.run_id,
            RuleStatus.INCONCLUSIVE,
            "the configuration was reconstructed from a declaration, not read from a run artifact",
            evidence=[
                f"resolved_config: {measurements['keys_recovered']} key(s) at {source} "
                f"({config.status.value})",
                "the source is not one of this run's own artifacts",
            ],
            measurements=measurements,
            limitations=limitations
            + [
                "runtime overrides applied after the declaration was read cannot be ruled out "
                "from a repository file"
            ],
            recommendation="write the configuration the process actually used into the run's output",
        )
