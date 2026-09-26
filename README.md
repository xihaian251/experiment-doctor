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

# The five checks + the ten formal rules -> report.json + report.md
experiment-doctor audit /path/to/project -o experiment-doctor-report

# The formal rule registry (ED001-ED010) and the entity each one is evaluated against
experiment-doctor rules
experiment-doctor rules --json

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

## The ten formal rules

`ED001`-`ED010` are the formal rule set: one question per rule, one result per entity
(`family`, `run` or `aggregation`), and exactly five statuses — `PASS`, `FAIL`,
`INCONCLUSIVE`, `NOT_APPLICABLE`, `NOT_RUN`. Severity (`INFO`/`LOW`/`MEDIUM`/`HIGH`) is
reported independently, there is no combined score, and an absent piece of evidence is
never promoted into a contradiction. Contracts: [docs/rules/](docs/rules/).

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

`torchssl` reads the shared run logs (`<algorithm>_<dataset>_<labels>_<seed>/log.txt`): the
seed and effective configuration from the `Arguments` dump, `best`/`last` accuracy from the
per-evaluation lines, the family key from `main.py`, and the aggregation semantics
(mean ± std, `num_models` repetitions) from `scripts/average_log.py`. Options: `repo_root`,
`logs_root`, `reported_table`.

## Development

```bash
python -m pytest -q                              # 95 tests, incl. the two mini fixtures
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

```bash
# 46 checks against the real TorchSSL logs
python scripts/run_torchssl_acceptance.py --repo /path/to/repo \
    --logs-root /path/to/downloads/logs \
    --reported-table examples/torchssl_reported_table.json -o acceptance.json

# 19 checks: the ten formal rules on both projects, in one pass
python scripts/run_rule_acceptance.py --gmmvi-repo /path/to/gmmvi/repo \
    --gmmvi-data /path/to/gmmvi/extracted/evaluations/results \
    --gmmvi-reported-table examples/gmmvi_reported_table.json \
    --torchssl-repo /path/to/torchssl/repo \
    --torchssl-logs /path/to/torchssl/downloads/logs \
    --torchssl-reported-table examples/torchssl_reported_table.json -o rule_acceptance.json
```

`run_rule_acceptance.py` checks rule behaviour only — which statuses a rule may and may not
produce for a project whose artifacts look like this — and repeats none of the structural
assertions above. [rule_acceptance.json](rule_acceptance.json) is the committed result.

## Not built

No verdict of SAFE/INVALID/RISKY, no significance tests or p-values, no re-execution of
training, no checkpoint tensor analysis, no cherry-picking or misconduct judgement, no
LLM analysis, no GUI/web service/database/plugin system, no write operations of any kind.
