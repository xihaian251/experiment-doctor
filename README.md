# Experiment Doctor v0.1

Read-only audit of the **provenance** and **aggregation membership** of ML experiment
artifacts. It answers two questions about a project's result tables:

1. Which run produced which number, and how much of that binding is actually evidenced?
2. Does a published `mean ± spread` cell recompute from the run artifacts it claims to
   aggregate — including the runs that were dropped?

It never judges science, never writes into the audited project, and never fills a gap by
guessing. An unknown stays `UNKNOWN`.

## Install

```bash
cd v0.1
pip install -e ".[dev]"        # python >= 3.11, pydantic + typer + PyYAML only
experiment-doctor --help
```

## Use

```bash
# What is in there? (families, run candidates, artifacts, provenance coverage)
experiment-doctor scan /path/to/project

# The five checks -> report.json + report.md
experiment-doctor audit /path/to/project -o experiment-doctor-report

# Which adapters exist and what each one understands
experiment-doctor adapters
```

`--adapter NAME` forces a specific adapter instead of auto-detection (confidence-scored
`detect()`; the `generic` fallback always applies).

`--reported-table FILE --adapter NAME` adds the reported-vs-recomputed comparison. The
file is a transcription of the *published* cells and is an explicit external input;
without it every comparison is `UNKNOWN` even though the recomputation still runs. Schema:
[docs/reported_summary_schema.md](docs/reported_summary_schema.md); worked example:
[examples/gmmvi_reported_table.json](examples/gmmvi_reported_table.json).

## The five checks

| check | question | vocabulary |
| --- | --- | --- |
| run identity | do the runs of a family share one evidenced method/task/config? | `CONSISTENT`, `MIXED_CONFIG`, `UNKNOWN` |
| seed integrity | are the repetitions actually distinct seeds, and as many as declared? | `CONSISTENT`, `DUPLICATE_SEEDS`, `CONFLICTING_SEEDS`, `SEED_COUNT_DIFFERS_FROM_DECLARED`, `ALL_SEEDS_UNKNOWN` |
| metric provenance | is each metric's direction evidenced by code, inferred, or silent? | per-field evidence grades |
| aggregation membership | which runs entered the published mean, and on what rule? | per-run membership + reason evidence |
| aggregation recompute | does `mean ± spread` land on the published cell? | `MATCH`, `MISMATCH`, `UNKNOWN` |

Every field carries an evidence grade — `CONFIRMED`, `SUPPORTED`, `INFERRED`, `UNKNOWN`,
`CONFLICTING` — plus its source (`path:key:line`). There is deliberately no composite
trust score.

## Adapters

`generic` walks the directory tree, classifies artifacts by extension, and emits explicit
provenance gaps. It promotes no column to a metric of record.

`gmmvi-exp3` reconstructs GMMVI Experiment 3 from its own artifacts: the
`fetch_exp3.py` declarations (metric names, `larger_is_better` per branch, secondary
metrics, excluded run ids), `run_{i}.csv` / `run_{i}.csv.bad` slot histories, cw2
multi-document configs (`DEFAULT` + per-environment docs, eval vs hyperopt protocols that
share a group name), and the `README.rst` exclusion prose, which is the only record of
*why* a run was dropped. Options: `repo_root`, `results_root`, `reported_table`. When the
code and the artifacts are split across directories, point `audit` at the directory that
contains both (the adapter probes `repo/`, `extracted/evaluations/results/`, and upward).

## Development

```bash
python -m pytest -q                              # 16 tests, incl. tests/fixtures/mini_gmmvi
python -m ruff check src tests scripts && python -m ruff format --check src tests scripts
python -m mypy src scripts tests
```

The golden acceptance against the real project is **not** part of the test run — it needs
the artifacts and takes about half a minute:

```bash
python scripts/run_gmmvi_acceptance.py --repo /path/to/repo \
    --data-root /path/to/evaluations/results \
    --reported-table examples/gmmvi_reported_table.json -o acceptance.json
```

Its expected numbers are Phase 0 forensic findings used as a test oracle; nothing under
`src/` knows them.

## Not built

No verdict of SAFE/INVALID/RISKY, no significance tests or p-values, no re-execution of
training, no checkpoint tensor analysis, no cherry-picking or misconduct judgement, no
LLM analysis, no GUI/web service/database/plugin system, no write operations of any kind.
