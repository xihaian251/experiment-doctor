# Environment Provenance: Declared ≠ Runtime

The schema refinement responding to the two P1 limitations registered in the v0.1
ruleset report (§22, items 1 and 2).  It changes no rule identity, no adapter, and no
existing field; it gives the two environment concepts separate homes so that
"declared environment exists / runtime environment unknown" is expressible instead of
collapsed into one string.

## The problem the two accepted projects proved

* **P1-a.** `ExperimentRun.environment` is one scalar with two candidate meanings.
  GMMVI fills it with the *task* environment (`breast_cancer`, cited to a config
  `experiment_id`); TorchSSL fills it with *declared* conda pins (`environment.yml`).
  ED010 asks about neither: it asks what the run itself recorded about the software
  and machine it executed on.
* **P1-b.** Repository dependency declarations (`requirements.txt`,
  `environment.yml`, conda lockfiles, SLURM templates) were only plain files.  With
  no role vocabulary there was no way to say "this artifact declares dependencies, is
  bound to no run, and is unverified by runtime evidence".

## The two concepts

### `RuntimeEnvironment` — what the run's own artifacts recorded

| Field | Grade carrier |
| --- | --- |
| `python_version` | `ProvenanceField[str]` |
| `framework_versions` | `ProvenanceField[dict[str, str]]` |
| `cuda_version` | `ProvenanceField[str]` |
| `hardware` | `ProvenanceField[str]` |
| `os` | `ProvenanceField[str]` |
| `source_artifacts` | run-local artifacts that state these values |

Every aspect carries its own evidence grade: `CONFIRMED` when a run-local artifact
prints it (a log line with the interpreter and library versions), never higher from a
declaration.  The slot lives on `ExperimentRun.runtime_environment` and defaults to
`None`, which is what every pre-refinement scan record means.

### `DeclaredEnvironment` — what the repository says was intended

`artifact_id`, `artifact_type` (`requirements` / `environment_yaml` / `conda_yaml` /
`dockerfile` / `slurm_template` / `unknown`), `source_path`, `declared_dependencies`
(a `ProvenanceField[dict[str, str]]`, `UNKNOWN` when the file parses to no pins), and
`provenance`.  It hangs off `ExperimentProject.declared_environments`.

**A declaration is never promoted into a runtime record.**  Registration of the two
accepted projects' files into these models is adapter work and is deliberately not
done here (adapters are frozen this round); until then the lists are empty and ED010
reads the artifact inventory as before.

### `ArtifactRef.artifact_role`

A closed enum (`SOURCE_CODE`, `CONFIG`, `LOG`, `CHECKPOINT`, `DATASET`,
`DECLARED_ENVIRONMENT`, `RESULT`, `REPORT`), nullable, never a free string.  A
`DECLARED_ENVIRONMENT` role counts toward ED010's `declared_environment_files` even if
the scanner typed the file otherwise, and no role ever counts as runtime evidence.

## `RunEnvironmentBinding` and its one hard rule

The light relation between one run and the environment evidence around it:
`run_id`, optional `runtime_environment`, optional `declared_environment`, and a
`relationship_status` of `MATCHED / CONFLICTING / ONLY_DECLARED / ONLY_RUNTIME /
UNKNOWN`.  ED010 builds one per evaluated run and reports its status as the
`environment_relationship` measurement.

`MATCHED` is asserted **only** when both sides state a version for the same package
and those versions agree.  Disjoint facts, a declaration that names no pins, or a
scalar runtime string that cannot be version-compared all stay `UNKNOWN`; a missing
pin contradicts nothing either, so `CONFLICTING` requires a shared package with
different values.  Agreement and disagreement are never inferred from absence.

## Compatibility

All additions are optional fields with inert defaults; pre-refinement JSON validates
unchanged (see `test_environment_schema_additions_keep_old_json_readable`), and the
legacy `environment` scalar is untouched — a project may keep using it for the task
environment.  The refinement changes what the schema can express, not what any older
record asserts.
