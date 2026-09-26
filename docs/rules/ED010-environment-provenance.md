# ED010 — Runtime Environment Provenance

## Purpose
Can the software and hardware a historical run executed on be established from what that run
itself left behind?

## Applies To
`run`. One result per discovered run.

## Inputs
`ExperimentRun.environment`, `.compute_budget`, `.artifacts`;
`ExperimentProject.artifacts` filtered to `ArtifactType.ENVIRONMENT` (the repository-level
dependency declarations, counted as `declared_environment_files`).

## The rule this encodes
A dependency file in the repository states what the author intended to install. It cannot
show what was installed on the machine that ran the job months ago. Therefore **a declaration
never produces PASS here** — only a value read out of the run's own artifact does, and the
standard is not lowered to manufacture a PASS.

## PASS
`environment` is `CONFIRMED`/`SUPPORTED` **and** its source is one of this run's own
artifacts. If no artifact records the hardware or compute budget, PASS says so as a
limitation instead of hiding it.

## FAIL
The artifacts state mutually exclusive runtime environments for the same run.

## INCONCLUSIVE
- No artifact records the environment this run executed in.
- An environment value exists but only from a declaration outside the run's artifact set —
  the summary distinguishes this case ("only established from a declaration outside the
  run's own artifacts") and still refuses PASS.

## NOT_APPLICABLE
Not produced.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, PASS → INFO.

## Evidence
`environment` value with grade and citation, and the repository-level declarations that were
found (paths, up to five) or the statement that none was found anywhere.

## Limitations
- Intended versions cannot show which versions a historical run actually loaded.
- UNKNOWN means the run recorded nothing about its environment — not that the environment was
  wrong or unreproducible.
- The schema has one `environment` field, and a project may fill it with the *task*
  environment rather than the software one. The grade is what this rule reads: a value
  cited only to a repository file stays INCONCLUSIVE whichever meaning it carries. The
  meaning of the cited string is shown in the evidence so a reader can tell.

## Examples
- GMMVI: 3483/3483 runs INCONCLUSIVE, `source_attached_to_run = false`,
  `declared_environment_files = 3` (`requirements.txt` plus two SLURM templates). The
  adapter's `environment` value is the task the loader selects on (for example
  `breast_cancer`, cited to a config's `experiment_id`), which is a *task* environment, not
  a software one — and since nothing run-local exists, the status is INCONCLUSIVE either
  way.
- TorchSSL: 6/6 runs INCONCLUSIVE. The value is the conda pins the project's own
  `environment.yml` declares (`python==3.7.10`, `pytorch==1.7.1`, `cudatoolkit==10.2.89`),
  `SUPPORTED` at a repository path that is not one of the run's artifacts, so a declaration
  is refused as runtime evidence. The hardware side is better documented here —
  `compute_budget` is `SUPPORTED` — which is exactly the split this rule reports: a
  citable budget is not a citable environment.
- Synthetic: a run whose own `log.txt` prints python/torch/CUDA versions → PASS with
  `source_attached_to_run = true`.
