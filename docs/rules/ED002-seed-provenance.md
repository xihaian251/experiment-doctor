# ED002 — Seed Provenance Integrity

## Purpose
Are the runs a project calls independent repetitions backed by distinct seeds that an
artifact actually records?

## Applies To
`family`. One result per family.

## Inputs
`ExperimentRun.seed` (value, provenance status, source), `.included_in_aggregation`;
`ExperimentFamily.kind`, `.declared_repetitions`.

## PASS
Every run of the family has a seed recovered from a run artifact and all recovered
values are distinct.

## FAIL
- Some run's own artifacts disagree about the seed that run used (`CONFLICTING`).
- The evidenced seeds contain the same value twice: those runs are not independent
  repetitions of one configuration.

## INCONCLUSIVE
Seed evidence is missing or partial. The summary states that seed provenance cannot be
established, and it always carries the note that the run count is not evidence of
distinct seeds — a project may rerun one seed, and a slot index is not a seed.
**UNKNOWN never becomes FAIL.** A family of ten runs with no recorded seed is an
evidence gap about the past, not a duplication finding.

## NOT_APPLICABLE
- The family is a `HYPERPARAMETER_SEARCH`: its runs are not independent random
  repetitions, so seed distinctness is not its integrity condition.
- No runs were discovered for the family at all.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, PASS/NOT_APPLICABLE → INFO.

## Evidence
Per-run `seed=<value> (<grade>) at <source>` for up to five runs, run count, seeds
recovered, declared repetitions with their provenance grade, duplicated values.

## Limitations
- A seed written only in prose is documentation about intent and is never counted as
  evidence; it appears as a limitation instead.
- `declared_repetitions` may itself be unevidenced; that is reported, not inferred.

## Examples
- GMMVI: 107 repetition families INCONCLUSIVE with `runs_with_seed_evidence = 0`, plus
  98 search families NOT_APPLICABLE. No family FAILs and none PASSes.
- TorchSSL: both families PASS — 3 of 3 runs per family carry a seed read from their own
  `log.txt` (`Arguments.seed`, L4), and the values 0, 1, 2 are distinct. The PASS still
  states its limitation: `declared_repetitions` is not asserted, because the README's prose
  and the shipped `config_generator.py` disagree about how many seeds are generated.
- Synthetic: three runs seeded `7, 7, 8` → FAIL/HIGH naming the duplicated value.
