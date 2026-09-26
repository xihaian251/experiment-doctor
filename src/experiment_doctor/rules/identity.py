"""ED001 - runs grouped as one experiment family must share one experiment identity."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from experiment_doctor.rules.base import Rule, RuleContext, RuleResult, RuleStatus
from experiment_doctor.schema import FamilyKind, IdentityStatus, Severity

#: Seed and slot identity are the dimensions a repetition is *allowed* to vary on
#: (v0.1 keeps them in dedicated fields, never inside the identity comparison).
#: A config key is explained when its value is the run's own seed, id, slot number,
#: repetition index, tracking id or the config path the run was launched with.
_VARYING_SOURCES = (
    "seed",
    "tracker_run_id",
    "repetition_index",
    "result_slot_index",
    "config_source",
    "run_id",
)


class RunIdentityConsistency(Rule):
    rule_id: ClassVar[str] = "ED001"
    title: ClassVar[str] = "Run Identity Consistency"
    purpose: ClassVar[str] = "Do the runs of one family differ on anything but randomness?"
    entity_type: ClassVar[str] = "family"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for family in context.project.families:
            results.append(self._one(family, context.runs_of(family.family_id), context))
        return results

    def _one(self, family: Any, runs: list[Any], context: RuleContext) -> RuleResult:
        family_id = family.family_id
        if len(runs) < 2:
            return self.result(
                family_id,
                RuleStatus.NOT_APPLICABLE,
                "a family with fewer than two runs has no identity to compare",
                measurements={"n_runs": len(runs)},
                recommendation="nothing to record; this check needs a repeated family",
            )

        conflicts = _field_conflicts(runs)
        varied, unexplained = _config_divergence(runs)
        search = family.kind is FamilyKind.HYPERPARAMETER_SEARCH

        if conflicts:
            return self.result(
                family_id,
                RuleStatus.FAIL,
                f"runs of one family disagree on {', '.join(sorted(conflicts))}",
                evidence=[f"{name}: {sorted(values)}" for name, values in sorted(conflicts.items())]
                + [f"runs compared: {len(runs)}"],
                measurements={
                    "n_runs": len(runs),
                    "conflicting_fields": len(conflicts),
                    "varied_config_keys": len(varied),
                },
                limitations=[
                    "the family is the project's own grouping; a conflict here means two runs "
                    "carrying different identity were averaged together"
                ],
                recommendation=(
                    "check which run entered the wrong group before quoting the family's aggregate"
                ),
            )

        measurements = {
            "n_runs": len(runs),
            "kind": family.kind.value,
            "varied_config_keys": len(varied),
            "unexplained_config_keys": len(unexplained),
        }
        if unexplained and not search:
            return self.result(
                family_id,
                RuleStatus.INCONCLUSIVE,
                "method and task agree, but the runs do not share one configuration and no "
                "recorded dimension explains the difference",
                evidence=[
                    f"config keys that differ between runs: {sorted(unexplained)}",
                    f"config keys explained by seed/slot identity: {sorted(varied) or '-'}",
                    f"identity check status: {status_of(context, family_id)}",
                ],
                measurements=measurements,
                limitations=[
                    "v0.1 has no artifact that states which configuration dimensions a family "
                    "intends to vary, so an unexplained difference cannot be called unintended"
                ],
                recommendation=(
                    "record the varying dimension per family (for example the key a search iterates "
                    "over), so identity comparisons can subtract it"
                ),
            )
        if unexplained and search:
            return self.result(
                family_id,
                RuleStatus.PASS,
                "method and task agree; the configurations differ, which is what a "
                "hyperparameter-search family is for",
                evidence=[
                    f"the project labels this family kind {family.kind.value}",
                    f"config keys that differ between runs: {sorted(unexplained)}",
                ],
                measurements=measurements,
                limitations=[
                    "the runs of a search family are not replicates; no aggregate over them is a "
                    "repeated-measurement mean"
                ],
            )

        identity = context.identity(family_id)
        if identity is not None and identity.status is IdentityStatus.UNKNOWN:
            return self.result(
                family_id,
                RuleStatus.INCONCLUSIVE,
                "neither method nor resolved configuration is evidenced, so identity cannot be "
                "compared",
                evidence=[f"runs compared: {len(runs)}"],
                measurements={
                    "n_runs": len(runs),
                    "varied_config_keys": 0,
                    "unexplained_config_keys": 0,
                },
                limitations=["identity fields carry no artifact evidence"],
                recommendation="record method, task and the effective configuration per run",
            )

        return self.result(
            family_id,
            RuleStatus.PASS,
            "all runs of the family share one evidenced method, task and configuration; the "
            "dimensions allowed to vary are seed and slot identity only",
            evidence=[
                f"runs compared: {len(runs)}",
                f"config keys explained by seed/slot identity: {sorted(varied) or '-'}",
            ],
            measurements=measurements,
        )


def status_of(context: RuleContext, family_id: str) -> str:
    identity = context.identity(family_id)
    return str(identity.status.value) if identity is not None else "NOT_RUN"


def _field_conflicts(runs: list[Any]) -> dict[str, set[str]]:
    """Identity-bearing fields whose evidenced values disagree across the family."""
    conflicts: dict[str, set[str]] = {}
    for name in ("method", "task", "dataset", "dataset_version"):
        values = {
            str(getattr(run, name).value) for run in runs if getattr(run, name).value is not None
        }
        if len(values) > 1:
            conflicts[name] = values
    return conflicts


def _config_divergence(runs: list[Any]) -> tuple[set[str], set[str]]:
    """Split differing config keys into explained-by-varying-dimension and not."""
    pairs = [
        (run, run.resolved_config.value)
        for run in runs
        if isinstance(run.resolved_config.value, Mapping)
    ]
    if len(pairs) < 2:
        return set(), set()
    keys = {key for _, config in pairs for key in config}
    varied = {
        key for key in keys if len({str(config.get(key, "<absent>")) for _, config in pairs}) > 1
    }
    explained: set[str] = set()
    for key in sorted(varied):
        values = [str(config.get(key, "<absent>")) for _, config in pairs]
        if all(value in _varying_values(run) for value, (run, _) in zip(values, pairs)):
            explained.add(key)
    return varied, varied - explained


def _varying_values(run: Any) -> set[str]:
    """The values a repetition may legitimately carry: its own seed, ids and slot."""
    values: set[str] = {run.run_id}
    for name in _VARYING_SOURCES:
        field = getattr(run, name, None)
        value = getattr(field, "value", field)
        if value is not None:
            values.add(str(value))
    return values
