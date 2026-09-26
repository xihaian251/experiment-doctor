# ED009 — Termination Provenance

## Purpose
Does an artifact say why this run stopped, or is the reason only something a reader could
guess from the shape of the history?

## Applies To
`run`. One result per discovered run.

## Inputs
`ExperimentRun.termination_cause` (a `TerminationCause` field with grade and citation),
`.status`, `.compute_budget`.

## Causes in scope
`iteration_cap`, `time_limit`, `crash`, `oom`, `converged`, `unknown` — a final metric
reached at an iteration cap, at a wall-clock deadline and at convergence are not the same
quantity, which is why the cause is a field rather than an inference.

## PASS
The cause is `CONFIRMED`/`SUPPORTED` and is not `UNKNOWN` — a terminal marker written in the
run's own output. A run marked `TRUNCATED_TIME_LIMIT` whose cause is recorded still PASSes,
with a limitation noting that its final value measures an unfinished schedule: recorded
without judging it.

## FAIL
The artifacts state mutually exclusive reasons for the same run ending.

## INCONCLUSIVE
No artifact records why the run ended. The limitation is the firewall statement: UNKNOWN here
means no artifact states the reason; **it does not mean the run failed, was stopped early or
was abandoned.** A history that simply stops is not a record of why it stopped.

## NOT_APPLICABLE
Not produced — every run ended, and the question of whether that is recorded applies to all
of them.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, PASS → INFO.

## Evidence
`termination_cause` value with grade and citation, the field's own confidence note when
present, and the run's status label.

## Limitations
- A status marker on the result slot is a label, not a record of the process that ended; it
  is reported as such and never promoted to a cause.
- When the cause is recorded but the budget it stopped against is not, PASS carries that
  gap explicitly.

## Examples
- GMMVI: 3483/3483 runs INCONCLUSIVE — the archived training history has no terminal marker.
- TorchSSL: 6/6 runs PASS with cause `iteration_cap`, read from each log's final evaluation
  iteration and carried with a confidence note that cites the break condition in the shipped
  code (`it > num_train_iter=1048576` at `models/fixmatch/fixmatch.py:123`; last logged
  evaluation 1048000). `compute_budget` is `SUPPORTED`, so no budget limitation is added.
- Synthetic: a run whose log contains "Terminated: reached maximum iteration" → PASS; one
  with both "killed by scheduler" and "converged" in different artifacts → FAIL/HIGH.
