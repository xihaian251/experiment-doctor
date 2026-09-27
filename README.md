# Experiment Doctor

Provenance audit for ML experiment artifacts, plus capture-first evidence
collection. The audit path (`scan`, `audit`, `rules`, `adapters`) is read-only;
the capture path (`init`, `run`, `verify`) records evidence about experiments you
run from now on.

## What it does

Given a research project's *existing* artifacts (result tables, per-run logs,
configs), Experiment Doctor answers:

1. Which run produced which published number, and how much of that binding is
   actually evidenced?
2. Does a published `mean ± spread` cell recompute from the run artifacts it
   claims to aggregate — including the runs that were dropped?

It reports each rule result as `PASS`, `FAIL`, `INCONCLUSIVE`,
`NOT_APPLICABLE`, or `NOT_RUN`, with per-field evidence grades
(`CONFIRMED`/`SUPPORTED`/`INFERRED`/`UNKNOWN`/`CONFLICTING`) and sources
(`path:line/key`). There is deliberately no composite trust score and no
overall verdict.

## Why it exists

Silent failures in experiment bookkeeping — mislabeled spreads, undocumented
exclusions, unrecoverable seeds — survive peer review because nobody
re-derives published aggregates from raw per-run artifacts. This tool does
that derivation mechanically and states honestly when the artifacts simply do
not record a fact.

It is **not**: a training framework, an experiment-tracker replacement, a
paper reviewer, a misconduct detector, or an automatic fairness adjudicator.

## Install

```bash
pip install experiment-doctor        # after PyPI publication; python >= 3.11
experiment-doctor --help
```

From a local checkout: `pip install .` (runtime deps: pydantic, typer,
PyYAML only).

## Quick start

Audit artifacts that already exist:

```bash
experiment-doctor scan ./project                 # what is in there?
experiment-doctor audit ./project -o ./doctor-report   # report.json + report.md
experiment-doctor adapters                       # installed adapters
experiment-doctor rules                          # ED001-ED010 registry
```

Capture evidence while the experiment runs:

```bash
experiment-doctor init --seed 42 --config config.yaml      # -> experiment.lock.json
experiment-doctor run -- python train.py --seed 42         # -> experiment.run.json +
                                                            #    experiment-evidence/
experiment-doctor verify                                    # V001-V006 -> verify.json
experiment-doctor audit ./project -o ./doctor-report        # picks up the bundle
```

`--adapter NAME` forces one adapter instead of confidence-scored
auto-detection (`generic` always applies as fallback).
`--reported-table FILE` supplies a transcription of published cells so the
reported-vs-recomputed comparison can bind; without it comparisons stay
`UNKNOWN` while recomputation still runs
(schema: [docs/reported_summary_schema.md](docs/reported_summary_schema.md)).

## Core model

`project → families → runs → metrics/artifacts`, plus `aggregations` (a
published statistic over a named member set). Every suspicious field is a
`ProvenanceField` carrying a value, an evidence grade, and a source. An
unknown stays `UNKNOWN`; absence of evidence is never promoted into a claim.

## Capture-first pipeline

For experiments you have not run yet, `init`/`run` record the facts that audit
could never recover from an archive afterwards:

```
init  -> experiment.lock.json     code revision, working-tree state, python /
                                   installed packages / platform, declared
                                   config + dataset fingerprints, declared seed
run   -> experiment.run.json      + stdout.log + stderr.log, collected into
                                   experiment-evidence/ (the evidence bundle)
verify-> V001-V006                 lock and run seals, the run -> lock hash
                                   chain, bundle presence, artifact digests,
                                   path boundary
audit -> captured adapter         maps the bundle onto the same provenance model,
                                   so ED001-ED010 run on observed evidence
```

Two rules bound what capture may say:

- **Two doors.** A value enters the record either by direct observation (git,
  the interpreter, the spawned process, file digests) or by your explicit
  declaration (`--seed`, `--command`, `--config`, `--dataset`, `--output-dir`).
  There is no third door: nothing is inferred. If `--seed` is not given, the
  lock keeps `randomness.seed = UNKNOWN` even when the config file contains a
  seed, because "a config mentions a seed" is not "this run used it".
- **No outcome claims.** `SUCCESS` in a run record means only that the process
  exited 0; it says nothing about training quality. stdout and stderr are stored
  as logs — the tool never parses a metric out of them, and there is no
  composite or confidence score anywhere in the output.

`run` executes the command you pass after `--` and mirrors its exit code.
`init` and `run` write only their own evidence files, at the project root.

## Rules ED001–ED010

| id | question | entity |
| --- | --- | --- |
| ED001 | do the runs of a family share one experiment identity? | family |
| ED002 | are the repetitions backed by distinct, recorded seeds? | family |
| ED003 | does an artifact name the code revision that ran? | run |
| ED004 | is the effective configuration recoverable from the run itself? | run |
| ED005 | which observation of a run does the published metric stand for? | aggregation |
| ED006 | which runs are inside the published mean, and is that traceable? | aggregation |
| ED007 | does the published number recompute from the member values? | aggregation |
| ED008 | is the `±` what the project says it is? | aggregation |
| ED009 | does an artifact say why the run stopped? | run |
| ED010 | is the runtime environment recorded by the run? | run |

Contracts: [docs/rules/](docs/rules/).

## Adapters

Project-specific parsing lives entirely in adapters; the core never reads a
project's private formats.

- `generic` — fallback scanner: walks the tree, classifies artifacts, emits
  explicit provenance gaps; promotes no column to a metric of record.
- `gmmvi-exp3` — GMMVI Experiment 3 reproducibility artifacts (fetch
  declarations, `run_{i}.csv`/`.csv.bad` slots, cw2 configs, README exclusion
  prose). Validated on that experiment's archived artifacts, not all GMMVI output.
- `torchssl` — TorchSSL selected shared-log format
  (`<algorithm>_<dataset>_<labels>_<seed>/log.txt`). Validated on that log
  family, not all TorchSSL output.
- `crda` — CRDA main-experiment artifacts
  (`experiments/<dataset>/<baseline>_<timestamp>/` with per-seed interim CSVs
  and `results.csv`). Validated on the committed main-experiment trees, not
  all CRDA output.
- `captured` — reads an `experiment-evidence/` bundle produced by this tool's
  own `init`/`run` and maps it onto the provenance model. Chosen automatically
  when a bundle is present and intact; citations are relocated onto the bundle
  files so rule evidence stays attached to the run it describes.

## Output

`audit` writes `report.json` (machine-readable: scan, audit checks, all rule
results, per-rule status counts) and `report.md` (human-readable) into the
user-specified `-o` directory. The audit path never writes into the audited
project. The capture path does: `init` and `run` write only their own evidence
files (`experiment.lock.json`, `experiment.run.json`, `experiment-evidence/`),
and `verify` only `verify.json`/`verify.md` inside that bundle.

## Rule semantics

- `INCONCLUSIVE` ≠ `FAIL`: it means the artifacts do not record the fact, not
  that the fact is violated.
- `PASS` ≠ mathematical proof of reproducibility: it means the check holds on
  the evidence available, at stated tolerances.
- Severity is reported independently; no weighted score exists.

## Limitations

- Read-only auditor: it never re-runs training and cannot detect fabrication
  that is internally consistent in the artifacts. `run` executes whatever
  command you pass after `--`; the tool never launches training by itself.
- Capture is forward-only. It converts fields that would otherwise be
  permanently `UNKNOWN` into recorded evidence for experiments run through it;
  it cannot retro-fit an archive that was never captured.
- Aggregation recompute covers the `mean` statistic with
  std/standard-error spread bases; other statistics stay `UNKNOWN`.
- Adapter coverage is per validated artifact format, not per research group.
- Historical provenance (producing commit, termination cause, runtime
  environment) is unrecoverable for most archived projects — this is reported
  as `INCONCLUSIVE`, which is the honest answer, not a bug.

## Development / validation

```bash
pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy src scripts tests
```

The tool has been validated end-to-end on three heterogeneous real research
projects (GMMVI, TorchSSL, CRDA) via external acceptance scripts
(`scripts/run_*_acceptance.py`); their expected numbers are forensic findings
kept in the acceptance layer only — nothing under `src/` knows them. The
capture pipeline is validated on synthetic fixtures plus
`scripts/run_v1_full_pipeline_check.py`, which drives `init` → `run` → `verify`
→ `audit` on four throwaway trees and fails unless the ED001–ED010 status
vectors repeat identically. See [CHANGELOG.md](CHANGELOG.md) and
[docs/PROJECT_STATE.md](docs/PROJECT_STATE.md); the v1 design and phase records
are under [docs/v1/](docs/v1/).

## License

Apache-2.0 — see [LICENSE](LICENSE).
