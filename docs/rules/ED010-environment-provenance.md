# ED010 — Runtime Environment Provenance

## Purpose
Can the software and hardware a historical run executed on be established from what that run
itself left behind?  ED010 checks **runtime** provenance: a repository declaration is a
different fact, carried by a different type, and never satisfies this rule alone.

## Applies To
`run`. One result per discovered run.

## Inputs
`ExperimentRun.environment` (legacy scalar), `ExperimentRun.runtime_environment` (the
structured runtime slot), `.compute_budget`, `.artifacts`;
`ExperimentProject.artifacts` counted as declarations when `ArtifactType.ENVIRONMENT` or
`ArtifactRole.DECLARED_ENVIRONMENT` (the repository-level dependency declarations, counted
as `declared_environment_files`); `ExperimentProject.declared_environments` (typed pins for
the declared-versus-runtime comparison).  See `docs/schema/environment-provenance.md`.

## The rule this encodes
A dependency file in the repository states what the author intended to install. It cannot
show what was installed on the machine that ran the job months ago. Therefore **a declaration
never produces PASS here** — only a value read out of the run's own artifact does, and the
standard is not lowered to manufacture a PASS.  Equally, the absence of versions never
manufactures a FAIL: a declared environment that names no pins contradicts nothing, and
`MATCHED` is never inferred from two sides that simply do not overlap.

## PASS
Runtime environment evidence exists and is run-local: `environment` is
`CONFIRMED`/`SUPPORTED` **and** its source is one of this run's own artifacts, or
`runtime_environment` states at least one evidenced aspect cited to a run artifact.
If no artifact records the hardware or the compute budget, PASS says so as a limitation
instead of hiding it.

## FAIL
Either the artifacts state mutually exclusive runtime environments for the same run
(`CONFLICTING` scalar or slot aspect), **or** the run's recorded runtime contradicts the
project's declared environment on a shared package version (e.g. the log prints
`torch 2.0` while `environment.yml` pins `1.7`).

## INCONCLUSIVE
- No run-local record exists, but declared evidence does: a repository dependency
  declaration, or an environment value cited only to a file outside the run's artifact
  set — the summary distinguishes this case ("only established from a declaration outside
  the run's own artifacts") and still refuses PASS.
- A structured runtime slot exists but every citation points at repository files
  (`requirements.txt` pins, a SLURM template's hardware stanza, a Dockerfile): that is
  declaration evidence, never execution evidence.

## NOT_APPLICABLE
Produced exactly when no environment evidence of either kind exists anywhere — no run
record, no slot, no repository declaration — so there is no environment claim this
project could have supported or contradicted.  It is not a pass: it says the question
cannot arise, not that the environment was recorded or sound.

## Severity
FAIL → HIGH, INCONCLUSIVE → MEDIUM, NOT_APPLICABLE → INFO, PASS → INFO.

## Evidence
`environment` value with grade and citation, or the run-local runtime citation; the
repository-level declarations that were found (paths, up to five) or the statement that
none was found.  Measurements carry `environment_relationship`
(`MATCHED / CONFLICTING / ONLY_DECLARED / ONLY_RUNTIME / UNKNOWN`) and
`runtime_evidence_recorded` alongside the original four keys.

## Limitations
- Intended versions cannot show which versions a historical run actually loaded.
- UNKNOWN means the run recorded nothing about its environment — not that the environment was
  wrong or unreproducible.
- The legacy `environment` scalar may carry the *task* environment rather than the software
  one; the grade is what this rule reads, so a value cited only to a repository file stays
  INCONCLUSIVE whichever meaning it carries.  The structured slots fix the vocabulary for
  future recording; no v0.1 adapter fills them yet.
- Declared-versus-runtime comparison needs typed pins in `declared_environments`; adapters
  freeze means on the two accepted projects the `CONFLICTING` version branch is reachable
  only in synthetic tests until registration lands.

## Examples
- GMMVI: 3483/3483 runs INCONCLUSIVE, `source_attached_to_run = false`,
  `declared_environment_files = 3` (`requirements.txt` plus two SLURM templates),
  `environment_relationship = ONLY_DECLARED`.  The adapter's `environment` value is the
  task the loader selects on (for example `breast_cancer`, cited to a config's
  `experiment_id`), which is a *task* environment, not a software one — and since nothing
  run-local exists, the status is INCONCLUSIVE either way.
- TorchSSL: 6/6 runs INCONCLUSIVE. The value is the conda pins the project's own
  `environment.yml` declares (`python==3.7.10`, `pytorch==1.7.1`, `cudatoolkit==10.2.89`),
  `SUPPORTED` at a repository path that is not one of the run's artifacts, so a declaration
  is refused as runtime evidence. The hardware side is better documented here —
  `compute_budget` is `SUPPORTED` — which is exactly the split this rule reports: a
  citable budget is not a citable environment.
- Synthetic: a run whose own `log.txt` prints python/torch/CUDA versions → PASS with
  `source_attached_to_run = true`; that log agreeing with `environment.yml` on a shared pin
  → `MATCHED`, disagreeing → FAIL; a project with no environment file and no run record →
  NOT_APPLICABLE.
