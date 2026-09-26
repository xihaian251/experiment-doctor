"""ED006 - can the member runs of a published aggregation be reconstructed?

Runs being *excluded* is not the finding; membership that cannot be traced is.  A
project is free to drop runs from a mean, and the reason for a drop may live only in
prose - that is recorded as a limitation, never promoted to a contradiction.
"""

from __future__ import annotations

from typing import Any, ClassVar

from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.rules.base import MEASUREMENT, Rule, RuleContext, RuleResult, RuleStatus
from experiment_doctor.schema import Severity

_PUBLISHED_MEMBERSHIP = "included"


class AggregationMembershipProvenance(Rule):
    rule_id: ClassVar[str] = "ED006"
    title: ClassVar[str] = "Aggregation Membership Provenance"
    purpose: ClassVar[str] = "Which runs are inside the published mean, and is that traceable?"
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
                "the project publishes no number for this record, so no membership is claimed",
                measurements={"variant": record.variant, "members": len(record.member_run_ids)},
            )

        members = [context.run(run_id) for run_id in record.member_run_ids]
        unresolved = [run_id for run_id, run in zip(record.member_run_ids, members) if run is None]
        present = [run for run in members if run is not None]
        marked_excluded = [run for run in present if run.included_in_aggregation.value is False]
        unevidenced = [
            run
            for run in present
            if run.included_in_aggregation.status
            not in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED)
        ]
        family = context.family(record.family_id)
        family_excluded = [
            run
            for run in context.runs_of(record.family_id)
            if run.included_in_aggregation.value is False
        ]
        declared = family.declared_repetitions.value if family is not None else None
        measurements: dict[str, MEASUREMENT] = {
            "members": len(record.member_run_ids),
            "values_aggregated": record.n,
            "excluded_enumerated": len(record.excluded_run_ids),
            "family_excluded_runs": len(family_excluded),
            "declared_repetitions": declared,
            "variant": record.variant,
        }
        evidence = [
            f"membership rule: {record.membership_rule.value or '-'} "
            f"({record.membership_rule.status.value})"
            + (
                f" at {record.membership_rule.source.describe()}"
                if record.membership_rule.source
                else ""
            ),
            f"members: {len(record.member_run_ids)}, of which {len(marked_excluded)} carry an "
            f"exclusion marker",
            f"excluded runs enumerated on the record: {len(record.excluded_run_ids)}",
        ]

        if marked_excluded and record.variant == _PUBLISHED_MEMBERSHIP:
            return self.result(
                record.aggregation_id,
                RuleStatus.FAIL,
                f"{len(marked_excluded)} member run(s) are marked as excluded by the project itself",
                evidence=evidence
                + [
                    f"{run.run_id}: {run.exclusion_reason.value or '-'}"
                    for run in marked_excluded[:5]
                ],
                measurements=measurements,
                recommendation="reconcile the exclusion markers with the set actually averaged",
            )
        if unresolved:
            return self.result(
                record.aggregation_id,
                RuleStatus.INCONCLUSIVE,
                f"{len(unresolved)} member id(s) do not resolve to any discovered run",
                evidence=evidence + [f"unresolved: {', '.join(unresolved[:5])}"],
                measurements=measurements,
                limitations=["the member list names slots this scan did not discover"],
                recommendation="publish the member run identifiers alongside the aggregate",
            )
        if unevidenced:
            return self.result(
                record.aggregation_id,
                RuleStatus.INCONCLUSIVE,
                f"{len(unevidenced)} member run(s) carry no evidence about whether they were included",
                evidence=evidence,
                measurements=measurements,
                limitations=[
                    "INCONCLUSIVE here is a bookkeeping gap: some runs may have been included and "
                    "some not, and the artifacts do not say which"
                ],
                recommendation="record per-run membership in a machine-readable artifact",
            )
        if record.membership_rule.status not in (
            ProvenanceStatus.CONFIRMED,
            ProvenanceStatus.SUPPORTED,
        ):
            return self.result(
                record.aggregation_id,
                RuleStatus.INCONCLUSIVE,
                "the rule that selected the member runs is not evidenced by an artifact",
                evidence=evidence,
                measurements=measurements,
                recommendation="keep the selection rule of the aggregation beside its inputs",
            )

        limitations = []
        if marked_excluded:
            limitations.append(
                "this record is an explicitly labelled alternative membership, so the excluded "
                "members inside it are the point of the record rather than a conflict"
            )
        if family_excluded and len(record.excluded_run_ids) != len(family_excluded):
            limitations.append(
                f"the family marks {len(family_excluded)} run(s) excluded while this record "
                f"enumerates {len(record.excluded_run_ids)}"
            )
        unexplained = [
            run.run_id
            for run in family_excluded
            if run.exclusion_reason.status
            not in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED)
        ]
        if unexplained:
            limitations.append(
                f"{len(unexplained)} excluded run(s) have a reason recorded only outside the machine-"
                "readable artifacts; that is an evidence gap about the reason, not about membership"
            )
        if declared is not None and measurements["members"] != declared and not family_excluded:
            limitations.append(
                f"the aggregation averages {measurements['members']} run(s) against "
                f"{declared} declared repetitions, and no exclusion explains the difference"
            )
        return self.result(
            record.aggregation_id,
            RuleStatus.PASS,
            f"the {measurements['members']} member runs of this published aggregate are identified "
            f"and every one of them is evidenced as included"
            + (
                f", with {len(family_excluded)} excluded run(s) enumerated separately"
                if family_excluded
                else ""
            ),
            evidence=evidence,
            measurements=measurements,
            limitations=limitations,
        )
