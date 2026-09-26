# ED005 — Metric Selection Provenance

## Purpose
Which observation of each member run does a published metric stand for — its best value,
its last value, or something else — and does the project say the same thing twice?

## Applies To
`aggregation`. One result per aggregation record, published or reconstructed.

## Inputs
`AggregationRecord.reported_value`, `.reported_source`, `.implemented_selection`,
`.documented_selection`, `.metric_name`, `.variant`, `.member_run_ids`; each member
run's `@best` / `@last` metrics.

## The shared shape
`implemented_selection` is what the aggregation code demonstrably consumes;
`documented_selection` is what the project's prose claims. `claim_comparison` classifies
the pair into `consistent | contradiction | conflicting-evidence | implementation-only |
documentation-only | undetermined`, and the status follows that classification only.

## PASS
- Both are evidenced and equal: the published number is the documented value of each
  member run.
- Only the implementation is evidenced: the code fixes the policy and the project states
  nothing in prose, so there is nothing to contradict.

## FAIL
- The prose documents `LAST` while the aggregation code consumes `BEST` (or the reverse).
- The artifacts give mutually exclusive selection records for the same cell.

## INCONCLUSIVE
A single number is published and nothing shows which observation of each run it came from.
The limitation says plainly that this is an evidence gap: nothing suggests the wrong value
was taken.

## NOT_APPLICABLE
The record is a reconstruction: the project published no number for it, so there is no
selection claim to hold against the code.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, PASS/NOT_APPLICABLE → INFO.

## Evidence
Reported value with citation, what the aggregation code selects (grade + source), what the
project prose claims (grade + source).

## Measurements — best ≠ last is data, not a finding
When the members carry both `@best` and `@last`, the rule reports
`family_best_mean`, `family_last_mean` and `best_minus_last`. These never enter the status
computation: a large gap on a cell whose prose and code agree is still PASS, with a
limitation noting the two quantities differ for these runs.

## Examples
- GMMVI: 36 published cells PASS because both sides say the same thing — `last`. The
  aggregation takes the last row of each history (`fetch_exp3.py` L39,
  `this_elbo = dataframes[i][metric].to_numpy()[-1]`) and the project's own README states
  "the final performance for every run in csv-files" (`README.rst` L94), so the published
  11.47 is documented as a final value and computed as one. 183 reconstructions
  NOT_APPLICABLE.
- TorchSSL: both `@best` cells PASS with documented = implemented = `best`; `best_minus_last`
  is measured at +0.29 and +0.23 percentage points and changes nothing. The `@last` cells are
  NOT_APPLICABLE because the project publishes no number for them.
- Synthetic: prose says "last checkpoint" while the code reads the tracked maximum →
  FAIL/HIGH.
