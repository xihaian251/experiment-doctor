"""ED002 - can the randomness of each run be recovered, and is it actually independent?"""

from __future__ import annotations

from typing import Any, ClassVar

from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.rules.base import Rule, RuleContext, RuleResult, RuleStatus
from experiment_doctor.schema import FamilyKind, Severity

#: A prose seed list is documentation about intent.  It is never runtime evidence,
#: so it appears in this rule only as a limitation to compare against.
_EVIDENCE_GRADES = (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED)


class SeedProvenanceIntegrity(Rule):
    rule_id: ClassVar[str] = "ED002"
    title: ClassVar[str] = "Seed Provenance Integrity"
    purpose: ClassVar[str] = "Are independent repetitions backed by distinct, recorded seeds?"
    entity_type: ClassVar[str] = "family"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        for family in context.project.families:
            results.append(self._one(family, context.runs_of(family.family_id)))
        return results

    def _one(self, family: Any, runs: list[Any]) -> RuleResult:
        family_id = family.family_id
        if not runs:
            return self.result(
                family_id,
                RuleStatus.NOT_APPLICABLE,
                "no runs were discovered for this family",
                measurements={"n_runs": 0},
            )
        if family.kind is FamilyKind.HYPERPARAMETER_SEARCH:
            return self.result(
                family_id,
                RuleStatus.NOT_APPLICABLE,
                "a hyperparameter-search family is not a set of independent random repetitions, "
                "so seed distinctness is not its integrity condition",
                measurements={"n_runs": len(runs), "kind": family.kind.value},
                limitations=[
                    "no aggregation over these runs is a repeated-measurement mean, whatever its N"
                ],
            )

        conflicting = [run for run in runs if run.seed.status is ProvenanceStatus.CONFLICTING]
        evidenced = [run for run in runs if run.seed.status in _EVIDENCE_GRADES]
        values = [int(run.seed.value) for run in evidenced if run.seed.value is not None]
        distinct = sorted(set(values))
        duplicated = sorted({value for value in values if values.count(value) > 1})
        declared = family.declared_repetitions
        measurements: dict[str, Any] = {
            "n_runs": len(runs),
            "runs_with_seed_evidence": len(evidenced),
            "runs_with_unknown_seed": sum(
                1 for run in runs if run.seed.status is ProvenanceStatus.UNKNOWN
            ),
            "runs_with_conflicting_seed": len(conflicting),
            "distinct_seeds": len(distinct),
            "duplicated_seeds": len(duplicated),
            "declared_repetitions": declared.value,
        }

        if conflicting:
            return self.result(
                family_id,
                RuleStatus.FAIL,
                "the artifacts of at least one run disagree about the seed that run used",
                evidence=[
                    f"{run.run_id}: {run.seed.source.describe() if run.seed.source else '-'}"
                    for run in conflicting
                ]
                + [f"runs compared: {len(runs)}"],
                measurements=measurements,
                recommendation="keep one authoritative record of the seed per run, written at run time",
            )

        if duplicated:
            return self.result(
                family_id,
                RuleStatus.FAIL,
                f"{len(evidenced)} evidenced seeds contain {len(duplicated)} value(s) more than once, "
                "so the runs are not independent repetitions of one configuration",
                evidence=[
                    f"duplicated seed values: {duplicated}",
                    f"distinct seeds: {len(distinct)} over {len(runs)} runs",
                ],
                measurements=measurements,
                recommendation="check whether a rerun replaced a fresh seed before quoting N",
            )

        if len(evidenced) == len(runs):
            limitations: list[str] = []
            if declared.status not in _EVIDENCE_GRADES or declared.value is None:
                limitations.append(
                    "the declared repetition count is not evidenced by an artifact"
                    + (f" ({declared.confidence_note})" if declared.confidence_note else "")
                )
            limitations.append(
                "a seed recorded in documentation is not evidence; only the values written into run "
                "artifacts were counted here"
            )
            return self.result(
                family_id,
                RuleStatus.PASS,
                f"every run's seed is recoverable from a run artifact and all {len(distinct)} are distinct",
                evidence=[
                    f"{run.run_id}: seed={run.seed.value} ({run.seed.status.value}) "
                    f"at {run.seed.source.describe() if run.seed.source else '-'}"
                    for run in evidenced[:5]
                ]
                + [f"seeds shown for {min(5, len(evidenced))} of {len(evidenced)} runs"],
                measurements=measurements,
                limitations=limitations,
            )

        note = (
            "the run count is not evidence of distinct seeds: a project may rerun the same seed, "
            "and a slot index is not a seed"
        )
        if evidenced:
            summary = (
                f"{len(evidenced)} of {len(runs)} runs carry seed evidence; the remaining "
                f"{len(runs) - len(evidenced)} cannot be checked"
            )
        else:
            summary = (
                "no artifact records a seed for any run of this family, so seed provenance cannot "
                "be established"
            )
        return self.result(
            family_id,
            RuleStatus.INCONCLUSIVE,
            summary,
            evidence=[
                f"runs: {len(runs)}",
                f"seeds recovered: {len(evidenced)}",
                f"declared repetitions: {declared.value} ({declared.status.value})",
                note,
            ],
            measurements=measurements,
            limitations=[
                "UNKNOWN here means no artifact records the value, not that the runs were "
                "repeated with the same seed"
            ],
            recommendation="record the seed and its derivation inside each run's own artifact at run time",
        )
