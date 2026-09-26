# ED004 — Resolved Configuration Provenance

## Purpose
Is the configuration a run actually executed under recoverable from that run's own
artifacts, or only reconstructed from a file that declares what *could* be run?

## Applies To
`run`. One result per discovered run.

## Inputs
`ExperimentRun.resolved_config`, `.config_source`, `.unrecorded_effective_parameters`,
`.artifacts`.

## PASS
`resolved_config` carries a value **and** its source is one of this run's own artifacts.
The summary names the artifact type and the number of keys recovered.

## FAIL
The artifacts disagree about which configuration this run resolved (`CONFLICTING`).

## INCONCLUSIVE
- Nothing was recovered for the run.
- A configuration was recovered, but from a declaration outside the run's artifact set —
  a repository YAML, a template, a launcher default. This branch states the limitation
  that runtime overrides applied after the declaration was read cannot be ruled out from
  a repository file. **A repo-side file never produces PASS.**

## NOT_APPLICABLE
Not produced — every run has an effective configuration question.

## NOT_RUN
Never produced by this rule; the engine emits it if evaluation raises.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, PASS → INFO.

## Evidence
Key count with citation and grade, `config_source` value and grade, whether the source is
attached to the run, count of `unrecorded_effective_parameters`.

## Limitations
- Effective parameters the run never recorded are listed on the run object and counted
  here; their absence is an evidence gap, not a wrong value.
- v0.1 compares the resolved mapping as a whole; it does not know which keys a project
  considers meaningful.

## Examples
- GMMVI: 3483/3483 runs PASS — the project's fetch script archived a resolved config per
  run inside that run's own result folder, and the adapter cites that run-local file.
  Four effective parameters the run never recorded (`seed`, `start_seed`, wall-clock
  budget, iterations actually run) are listed as limitations rather than hidden.
- TorchSSL: 6/6 runs PASS — each `log.txt` dumps the effective `Namespace` after
  `over_write_args_from_file()` and the in-code mutations, and the adapter cites that
  run-local log, so the source qualifies as the run's own artifact.
- Synthetic: only `configs/base.yml` in the repository, no run-local copy → INCONCLUSIVE
  with the runtime-overrides limitation attached.
