# ED001 — Run Identity Consistency

## Purpose
Do the runs a project grouped into one family actually share one experiment identity,
or do they differ on something besides randomness?

## Applies To
`family`. One result per family in the scanned project. A family with fewer than two
discovered runs is not compared against itself.

## Inputs
`ExperimentRun.method`, `.task`, `.dataset`, `.dataset_version`, `.resolved_config`,
`.seed`, `.run_id`, `.tracker_run_id`, `.repetition_index`, `.result_slot_index`,
`.config_source`; `ExperimentFamily.kind`; the audit's `check_run_identity` record.

## PASS
- Identity-bearing fields agree across the family and every config key that differs is
  explained by a dimension a repetition legitimately carries (its own seed, ids, slot,
  or the config path it was launched with).
- The family is labelled `HYPERPARAMETER_SEARCH` and its configs differ, which is what a
  search family is for.

## FAIL
Two runs of one family carry different evidenced values for `method`, `task`, `dataset`
or `dataset_version`. The severity is HIGH: two runs with different identities were
grouped together.

## INCONCLUSIVE
- Config keys differ and no recorded dimension explains the difference. v0.1 has no
  artifact stating which dimensions a family *intends* to vary, so an unexplained
  difference is not called unintended.
- Neither method nor resolved configuration is evidenced at all
  (`IdentityStatus.UNKNOWN`), so there is nothing to compare.

## NOT_APPLICABLE
Fewer than two runs were discovered for the family.

## NOT_RUN
Never produced by this rule; the engine emits it if evaluation raises.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, PASS/NOT_APPLICABLE → INFO.

## Evidence
The conflicting field names with their distinct values, the run count compared, the
config keys that differ, the keys explained by seed/slot identity, and the identity
check's own status string.

## Limitations
- The family is the project's own grouping; this rule cannot detect a run that was put
  into the wrong family only when its identity fields happen to match.
- A config key whose value differs is attributed to the varying dimension only when the
  value equals one of that run's own identifiers.

## Examples
- GMMVI (Experiment 3): 205/205 families PASS — repetition families vary on seed/slot
  only, and search families are excused by their `kind`.
- TorchSSL: `fixmatch/cifar10_250` and `flexmatch/cifar10_250` PASS (3 runs each, one
  method, one task, one config).
- Synthetic: two runs of one family with `method` = `vae` and `beta_vae` → FAIL/HIGH.
