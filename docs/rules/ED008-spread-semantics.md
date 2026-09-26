# ED008 — Spread Semantics Consistency

## Purpose
What is the quantity after the `±` in a published cell, and does the project say one
thing about it while its code computes another?

## Applies To
`aggregation`, but only cells that publish a spread. One result per record.

## Inputs
`AggregationRecord.reported_spread`, `.implemented_spread`, `.documented_spread`
(both `SpreadSemantics` fields, each with its own evidence grade), `.std_ddof`,
`.display_multiplier`, `.n`, `.spread_basis`, `.recomputed_spread`, `.variant`.

## The taxonomy
`SpreadSemantics` is the six-value vocabulary both sides are recorded in:
`standard_deviation`, `standard_error`, `scaled_standard_error`,
`confidence_interval_half_width`, `custom`, `unknown`. The implemented side is what the
aggregation code demonstrably produces; the documented side is what the project's prose
states. `SpreadBasis` (`standard_error` | `standard_deviation`) stays a separate field: it
tells the recomputation how to divide, not what the number means.

## What is *not* a defect here
Population versus sample standard deviation, and a multiplier on the spread, are conventions.
`std_ddof`, `display_multiplier` and `n` are reported as measurements and **alone they never
produce a FAIL**. Only a mismatch between the documented meaning and the computed one counts
as one. This is the guard against the tool deciding, on its own, that every `±` must be a
standard error.

## PASS
- Both sides evidenced and equal: the published `±` is what the project says it is.
- Only the implementation is evidenced (`implementation-only`): the code that printed the
  number fixes the meaning and no statement contradicts it.

## FAIL
- The documented and implemented semantics differ (`contradiction`) — the summary quotes
  both, e.g. "the project documents its +/- as standard_error while the aggregation code
  computes standard_deviation".
- The artifacts give mutually incompatible accounts of the same `±` (`conflicting-evidence`).

## INCONCLUSIVE
A spread is published, but neither the producing code nor any statement fixes what it
measures — a bare `± 0.1`, or prose with no readable aggregation code. The limitation
states that this is about the spread's *identity*, not its size.

## NOT_APPLICABLE
No `±` accompanies the number, so there is no spread claim to check.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, PASS/NOT_APPLICABLE → INFO.

## Evidence
The published spread, what the code computes (grade + source), what the prose states
(grade + source), and the declared recomputation basis with its multiplier over N.

## Limitations
- Where the two readings differ, they differ by a factor of `sqrt(N)`; the rule says so and
  leaves the size of the effect to the reader.
- A PASS reached through `implementation-only` establishes the meaning only from the code.

## Examples
- TorchSSL: **both published cells FAIL/HIGH** — the README's table says the `±` is the
  standard error while `average_log.py` computes the standard deviation across the three
  runs (`std_ddof=0`, `display_multiplier=1.0`, `n=3`). The central values recompute
  perfectly (ED007 PASSes on the same cells), so the finding is purely about meaning.
- GMMVI: 36 published cells PASS on `implementation-only` — its aggregation multiplies by
  3 and divides by `sqrt(N)`, i.e. `scaled_standard_error`, and its prose makes no contrary
  statement; 183 records with no published spread are NOT_APPLICABLE.
- The three pinned regressions: prose `standard_deviation` + population-std code → PASS;
  prose `standard_error` + population-std code → FAIL; a bare `± 0.1` with no claim at all
  → INCONCLUSIVE.
