# ED007 — Aggregation Numerical Consistency

## Purpose
Does the published aggregate come back out of the member runs' own numbers, within the
precision the project actually printed?

## Applies To
`aggregation`. One result per aggregation record.

## Inputs
`AggregationRecord.reported_value`, `.reported_spread`, `.values`, `.n`, `.statistic`,
`.std_ddof`, `.display_multiplier`, `.spread_basis`, `.tolerance`,
`.spread_tolerance`, and the audit-populated `.recomputed_value`, `.recomputed_spread`,
`.comparison_status`.

## Arithmetic only
This rule consumes the audit's recomputation and compares floats against explicit
tolerances. No status here depends on a string match, on how a value is formatted, or on
what the project says the number means (that is ED008's question). PASS here and FAIL
there are a normal combination, and a test pins it.

## PASS
`comparison_status == MATCH`: the mean is within `tolerance` of the reported value and,
when a spread is published, the displayed spread is within `spread_tolerance` of the
recomputed one.

## FAIL
`comparison_status == MISMATCH`. The summary names which side differs — `mean`, `spread`,
or both — so a reader knows whether the central number or its dispersion is at issue.

## INCONCLUSIVE
One of the four inputs the comparison needs is missing:
- no reported value (a reconstruction the project never published a number for);
- no reported spread;
- no member metric values recovered;
- a statistic v0.1 does not recompute (only `mean` is recomputed);
- spread undefined for that N and ddof.

The published number is then neither confirmed nor refuted, and the limitation lists which
inputs are absent.

## NOT_APPLICABLE
Not produced — an unelectable comparison is INCONCLUSIVE, which keeps the report's counts
honest about what was actually checked.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, PASS → INFO.

## Evidence
N members and values recovered, reported value ± spread with citation, recomputed value ±
spread with the statistic/ddof/multiplier/basis used, and both tolerances.

## Limitations
- The tolerance comes from the digits the project printed; it is never widened to force
  agreement, and the recommendation for a mismatch says so explicitly.
- v0.1 recomputes the mean only. A published median produces INCONCLUSIVE, not a FAIL.

## Examples
- GMMVI: 36 published cells PASS. `Planar4_EVAL/samtron_planar_4/-elbo` publishes 11.47 ±
  0.04 over 10 members; the recomputation gives 11.466954 ± 0.040358 at tolerance 0.005 for
  both sides. The other 183 records are reconstructions and land in INCONCLUSIVE with "no
  reported value to compare against".
- TorchSSL: both `@best` cells PASS — 95.14 ± 0.05 and 95.02 ± 0.09 recompute from three
  logged accuracies each; the `@last` records are INCONCLUSIVE because nothing is published.
- Synthetic: members `1.0, 2.0, 3.0` (mean 2.0) published as `2.5` → FAIL/HIGH whose
  summary ends in "(mean differ)"; the same members with `reported_spread=9.0` and a tight
  spread tolerance fail with "(spread differ)" instead.
