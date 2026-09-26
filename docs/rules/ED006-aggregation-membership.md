# ED006 — Aggregation Membership Provenance

## Purpose
Which runs are inside a published aggregate, and can that set be traced from the
artifacts — including the runs that were left out?

## Applies To
`aggregation`. One result per aggregation record.

## Inputs
`AggregationRecord.member_run_ids`, `.excluded_run_ids`, `.membership_rule`, `.n`,
`.reported_value`, `.variant`; each member run's `.included_in_aggregation`,
`.exclusion_reason`; `ExperimentFamily.declared_repetitions`.

## The governing distinction
Dropping runs is the project's free choice. **Excluded runs existing is not a finding.**
What this rule checks is whether the kept set is traceable. A family that marks six runs
excluded and publishes an aggregate over the rest, with the membership rule evidenced,
PASSes and enumerates the exclusions in its summary.

## PASS
Every member run resolves to a discovered run, every one of them is evidenced as
included, and the membership rule itself is evidenced by an artifact.

## FAIL
Member runs of an `included` record carry the project's own exclusion marker — the
published set claims to be the included runs and contains runs the project says were
excluded. An alternative record that is *labelled* as containing excluded members (a
variant other than `included`) is not a conflict; for those, the excluded members are the
point of the record.

## INCONCLUSIVE
- A member id does not resolve to any discovered run (bookkeeping gap).
- Some member carries no evidence about whether it was included.
- The membership rule is not evidenced by an artifact.

## NOT_APPLICABLE
The project publishes no number for this record, so no membership is claimed.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, PASS/NOT_APPLICABLE → INFO.

## Evidence
Membership rule with grade and citation, member count and how many carry an exclusion
marker, exclusions enumerated on the record, and each excluded member's own reason.

## Limitations
- When an excluded run's reason lives outside the machine-readable artifacts — prose in a
  readme, a `*.csv.bad` rename — the rule records that as *an evidence gap about the
  reason*. It never attributes an intention to the project.
- When the record's member count differs from the declared repetitions and no exclusion
  explains the difference, that mismatch is reported as a limitation.

## Examples
- GMMVI: 36 published cells PASS with up to 6 excluded runs per family enumerated
  separately (`family_excluded_runs` max = 6), and 183 reconstructions NOT_APPLICABLE.
  Zero FAILs — the exclusions never became an accusation.
- TorchSSL: both `@best` cells PASS with 3 evidenced members and no exclusions; the two
  `@last` reconstructions are NOT_APPLICABLE.
- Synthetic: a run renamed `result.csv.bad` with no recorded reason → PASS on membership
  plus the evidence-gap limitation, not a FAIL.
