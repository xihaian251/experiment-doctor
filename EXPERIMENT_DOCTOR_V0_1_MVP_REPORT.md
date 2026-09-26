# Experiment Doctor v0.1 — MVP Report

Date: 2026-09-26. Code: `F:\MLResearch\experiment-doctor\v0.1`. Verification target:
`F:\MLResearch\experiment-doctor\phase0-gmmvi` (gmmvi_reproducibility, Experiment 3),
treated strictly read-only throughout.

---

## 1. Scope

v0.1 is a read-only command-line tool, `experiment-doctor`, that answers two questions about
the artifacts a research project already ships:

1. **Provenance** — which run produced which number, and how much of that binding is actually
   evidenced by an artifact?
2. **Aggregation membership** — which runs entered a published `mean ± spread` cell, on what
   rule, and does the cell recompute from the surviving run files?

Three commands, two output formats (JSON + Markdown), one real-project adapter plus a generic
fallback. Nothing writes into the audited project, nothing fills a gap by guessing, and every
reconstructed field carries an explicit evidence grade. `UNKNOWN` is a result, not a failure.

Out of scope by design (§4 of the baseline): SAFE/INVALID/RISKY verdicts, significance tests,
p-values, bootstrap, multiple-comparison correction, cherry-picking or misconduct judgements,
re-executing training, checkpoint tensor analysis, W&B mutation, LLM analysis, GUI/web service,
databases, plugin systems, PyPI publication.

## 2. Architecture

```
src/experiment_doctor/
  schema.py        7 core Pydantic objects + enums + Finding      (frozen vocabulary)
  provenance.py    ProvenanceField[T] / SourceRef / EvidenceCounts (runtime invariants)
  scanner.py       directory walk, artifact classification, adapter protocol + registry
  adapters/
    __init__.py    lazy installation, scored auto-selection, build(name, root)
    generic.py     always-available fallback: inventory + explicit gaps
    gmmvi.py       gmmvi Experiment 3 semantics (fetch declarations, .csv.bad slots, cw2, README prose)
  audit.py         the five checks + AuditResult/Finding assembly
  report.py        report.json payload + report.md renderer
  cli.py           Typer app: scan | audit | adapters
```

Dependency direction is one-way: `cli → report → audit → scanner/adapters → schema/provenance`.
Project-specific meaning lives only in adapters, never in the schema and never in `audit.py`.
Runtime dependencies are `pydantic`, `typer`, `PyYAML`; statistics use stdlib `math` only.

## 3. Core Schemas

`ExperimentProject` (root, project_id, adapter, code_repository, families, runs, aggregations,
artifacts, notes) → `ExperimentFamily` (family_id, name, kind, result_dir, declared_repetitions,
membership_rule, primary_metric, secondary_metrics, run_ids, seed_derivation, code_repository …)
→ `ExperimentRun` (run_id, family_id, result_slot_index, method, task, dataset, seed,
repetition_index, config_source, resolved_config, entrypoint, command, start/end_time,
termination_cause, compute_budget, runtime_seconds, history_rows, included_in_aggregation,
exclusion_category/reason/evidence, status, metrics, artifacts) → `MetricRecord` (name, value,
direction, source) → `AggregationRecord` (aggregation_id, family_id, metric_name, statistic,
transform, member_run_ids, excluded_run_ids, values, n, mean, std, std_ddof, display_multiplier,
reported_value, recomputed_value, reported_spread, recomputed_spread, tolerance, spread_tolerance,
comparison_status, membership_rule, reported_source) → `ArtifactRef` (path, artifact_type, size,
mtime, sha256) and `ProvenanceField[T]`. Findings are `Finding(category, title, severity,
entity_type, entity_id, evidence[], recommendation)`.

Frozen identities (§Phase 0 constraint A): `run_id ≠ seed ≠ repetition_index ≠ family_id`.
Enumerations are closed vocabularies so the report stays machine-comparable across versions:
`FamilyKind`, `RunStatus`, `TerminationCause`, `ExclusionCategory`, `MetricDirection`,
`ArtifactType`, `ComparisonStatus`, `IdentityStatus`, `FindingCategory`, `Severity`
(`schema.py`) and `ProvenanceStatus` (`provenance.py`). The per-family seed verdict
(`ALL_SEEDS_UNKNOWN`, `CONFLICTING_SEEDS`, `DUPLICATE_SEEDS`,
`SEED_COUNT_DIFFERS_FROM_DECLARED`, `CONSISTENT`) and the membership/reason status strings are
fixed by the audit module, which is the only place that derives them.

## 4. Provenance Model

Every suspicious value is a `ProvenanceField`: `value`, `status ∈ {CONFIRMED, SUPPORTED,
INFERRED, UNKNOWN, CONFLICTING}`, `source: SourceRef`, `confidence_note`. Invariants are enforced
by a model validator, not by convention:

* `UNKNOWN` may not carry a value;
* `CONFIRMED` / `SUPPORTED` must cite a source;
* `INFERRED` is the ceiling for anything heuristic (e.g. a metric direction read off its name);
* `ProvenanceField.conflicting(sources)` yields `value=None` with the competing citations joined
  in the note — disagreement is reported, never averaged away.

`EvidenceCounts` tallies the five grades per field, and `AuditResult.coverage` is that table:
25 fields × 3483 runs in the verification project. There is deliberately **no composite trust
score**; a single number would hide exactly the asymmetry the model exists to expose.

## 5. Generic Scanner

`iter_files()` walks the tree skipping VCS/environment noise dirs under a hard artifact cap
(`MAX_ARTIFACTS = 200_000`); `classify()` maps a path to an `ArtifactType` from the suffix alone
(CONFIG/METRIC/LOG/CHECKPOINT/SCRIPT/ENVIRONMENT/TABLE/UNKNOWN); `make_artifact_ref()` records
path, type, size and mtime (hashes are opt-in, because hashing 12k files is not what an audit
budget should spend). The generic adapter groups files by directory, promotes directories that
contain metric-shaped files to run candidates, binds a config to a run **only** by file-stem
equality and grades that `INFERRED`, and emits families with `kind=UNKNOWN` and
`membership_rule=UNKNOWN`. It never promotes an unlabelled CSV column to a metric of record —
`ExperimentRun.metrics` stays empty, so an anonymous project yields an inventory and explicit
gaps, not invented semantics (unit-tested in `test_scanner.py`).

## 6. GMMVI Adapter

`gmmvi-exp3` recovers Experiment 3 semantics from four artifact families, all parsed at runtime:

* **`evaluations/fetch_exp3.py`** — the fetch declarations give the family→group mapping, the
  secondary metric of each call, the per-branch `larger_is_better` chain (so `-elbo`/`MMD:` are
  MINIMIZE because the code says so, and `num_detected_modes` MAXIMIZE), the primary metric via
  `latex_format(..., larger_is_better=False)`, and the commented-out `bad_run_ids=[...]` lists
  whose trailing per-line comments name the family those ids were dropped for.
* **`results/<GROUP>_EVAL/run_{i}.csv`** — `_step`/`num_samples`/`_runtime`/metric columns; the
  last logged row is the aggregated value; the row count and final `_runtime` become
  `history_rows` / `runtime_seconds`.
* **`.csv.bad`** — the only machine-readable membership marker in the project: a bad slot is a
  completed run the authors excluded.
* **cw2 configs** (`evaluations/configs/exp3 (eval)` vs `exp3 (hyperopt)`) — multi-document YAML
  where the `DEFAULT` doc supplies `algorithm_id/repetitions/iterations` and each environment doc
  supplies `experiment_id` and `wandb.group`. Both protocols share group names, so the adapter
  keys declarations by `kind:group` and takes the repetitions of the protocol that matches the
  family, not whichever file it read first.
* **`README.rst` exclusion prose** — the five bullets under "bad seeds" are the *only* record of
  why runs were dropped, including one misspelling ("SEPRUX"). Bullets are bound to families by
  normalised alias with a Levenshtein-≤2 fallback that refuses a match when the bullet names
  another alias that really exists, or when the nearest alias is ambiguous unless the excluded
  slot count breaks the tie. Every binding is graded `SUPPORTED` and cites both the README line
  and the fetch declaration.

Layout is resolved, not assumed: repo root is probed at `repo/`, `gmmvi_reproducibility/`,
`<parent>/repo/` and upward; results at `extracted/evaluations/results`, `evaluations/results`,
`results`, then the root itself. `code_repository` is `SUPPORTED` from the README's repository
reference with the note "the repository that ships the artifacts; not proven to be the code that
ran"; `code_commit` stays `UNKNOWN` even though a `.git` directory exists next to it, because a
clone made during forensics does not evidence the code that produced archived runs.

## 7. Run Discovery

A run is one result slot. 3483 runs are discovered in the verification project: 1090 evaluation
runs (`*_EVAL` groups) and 2393 hyperparameter-search runs. Each carries `run_id`
(`<family_id>#<slot stem>`), `result_slot_index`, and its own `ArtifactRef`s. Statuses:
3461 `COMPLETED_INCLUDED` + 22 `COMPLETED_EXCLUDED`. `runs_with_metrics = 3483`,
`runs_with_config = 3483`, `runs_missing_primary_value = 0`. Nothing is skipped silently: an
excluded run is discovered, labelled and counted, never deleted from the inventory (§30).

## 8. Family Reconstruction

205 families: 107 `EVALUATION` and 98 `HYPERPARAMETER_SEARCH`. A family's `declared_repetitions`
comes from the cw2 `DEFAULT` document of the protocol that actually owns the group (the eval
protocol says 10 for `samtrux_planar_4`, the identically named hyperopt protocol says something
else — picking the wrong one is the classic off-by-protocol error the fixture test pins down).
`primary_metric` is `-elbo` for 169 families and `elbo_fb:` for 36 (whose logged value is a loss
and must be negated before it can match the reported ELBO); secondary metrics are `MMD:`,
`entropy`, `bi_accuracy:`, `bi_test_loss`, `num_detected_modes`. `membership_rule` is `CONFIRMED`
for the 107 evaluation families (derived from `.csv.bad` presence) and `UNKNOWN` for the 98
search families, which is honest: no artifact states how grid results were aggregated.

## 9. Seed Integrity

All 205 families report `ALL_SEEDS_UNKNOWN`. No seed value appears in any run artifact: a
case-insensitive search for "seed" over all 10450 archived files in the artifact tree returns
zero matches — not in the CSVs, not in the cw2 config dumps stored next to each run, not in
`fetch_exp3.py`, and the tracker run ids that would have carried it were not archived.
Consequently `seed`, `seed_derivation` and `repetition_index` are `UNKNOWN` for 3483/3483 runs,
`DUPLICATE_SEEDS` and `CONFLICTING_SEEDS`
are structurally reachable but never fire here, and the identity of "10 seeds" cannot be
confirmed — only the count of 10 slots can. The adapter refuses to upgrade a slot index into a
seed; that refusal is the point (§Phase 0 constraint A).

What the launcher code *does* evidence is recorded in `seed_derivation`'s `UNKNOWN` note, and it
differs by family kind. For evaluation runs `evaluations/clusterwork.py:17` sets
`gmmvi_cfg["seed"] = gmmvi_cfg["start_seed"] + rep`, so the ten repetitions are meant to be ten
consecutive seeds — but `start_seed` comes from `gmmvi.configs.get_default_config()`, i.e. from
the installed library, and no archived artifact records its value, so the rule cannot be
instantiated. For the 2393 search runs `hyperopt/wandb_sweep.py:34` does
`config.update({"seed": 1})`: a sweep worker runs with one fixed seed, so a search "repetition" is
a hyperparameter draw, not a new seed. Both statements stay notes on an `UNKNOWN` field rather
than values on `seed`, because writing `start_seed + index` or `1` into `run.seed` would generate
metadata the project never recorded (§30). This is v0.2 item 3.

## 10. Metric Provenance

4573 `MetricRecord`s across 3483 runs; direction is `CONFIRMED` for all of them, each cited to a
line of `fetch_exp3.py` (per-branch `larger_is_better`, or the `latex_format` default for the
primary). 205/205 families have an evidenced primary metric and no run is missing its primary
value. This is the check where the tool is most strict about the sign convention: a metric whose
direction would flip a selection verdict has to be evidenced by code, never inferred from the
metric's name — Phase 0 found ~25 selection verdicts flip on sign conventions, so name-based
inference is capped at `INFERRED` and reported as such (the generic scanner produces no direction
at all).

## 11. Aggregation Membership

Membership is a first-class field per run, not an inference from the table. 1068 runs are
`included_in_aggregation=True`, 22 `False`, and 2393 search runs carry `UNKNOWN` (no rule exists
to grade). All 22 exclusions are `CONFIRMED` by the `.csv.bad` marker; 22/22 also carry an
`exclusion_reason` and `exclusion_evidence` at grade `SUPPORTED`, attributed to README bullets for
5 families (`sepyfux_planar_4`, `sepyrux_planar_4`, `zamtrux_planar_4`, `sepyfux_talos`,
`sepyrux_talos`). `excluded_without_evidence = 0` and `absent_slots = 0` across all families —
no slot in a declared-10 protocol is missing its file. The 200 families with no exclusion prose
report `reason_status=NONE`, which is the correct answer, not a gap: they dropped nothing.

## 12. Aggregation Recalculation

219 `AggregationRecord`s: one per (family, metric) for evaluation results, in two variants —
`@included` (surviving runs) and `@all_completed` (the counterfactual that includes the dropped
runs, graded `INFERRED` because no artifact declares that anyone computed it). v0.1 recomputes
only `statistic="mean"`, with the project's own convention read from the artifacts rather than
assumed: `std_ddof=0` and `recomputed_spread = display_multiplier · std / √N` with multiplier 3,
i.e. the published "± 3 sigma" is three standard errors, not three standard deviations.

Against the 36 published cells transcribed from Table 8 of arXiv:2209.11533v2 (supplied as an
*input* file, `examples/gmmvi_reported_table.json`), all 36 are `MATCH`, 0 `MISMATCH`, and the
remaining 183 records are `UNKNOWN` because nothing is published for them. Comparison is numeric
(`close_enough`), never string formatting; the default tolerance is the printed rounding
half-width with `1+1e-9` relative slack so a value sitting exactly on a rounding boundary is not
reported as a mismatch, and `value_tolerance`/`spread_tolerance` can override per cell.

The load-bearing example: `Planar4_EVAL/sepyfux_planar_4/-elbo@included` recomputes to
`17.262873 ± 2.129447` over N=5 against the published `17.26 ± 2.13` — the paper's number,
recovered from five CSVs. The `@all_completed` counterfactual over all 10 completed slots gives
`29.240750 ± 35.532846`: the five dropped seeds move the mean by +11.98 and multiply the displayed
spread by 16.7. That difference is a fact about the artifacts, and the report states it without
issuing a verdict about it.

## 13. Findings

326 findings, none of them a judgement: 217 `PROVENANCE_GAP` (205 per-family "seed is not
recoverable from any artifact" + 12 project-level "field X is UNKNOWN for every discovered run"
covering seed, code_commit, code_dirty, tracker_run_id, entrypoint, command, start/end_time,
repetition_index, termination_cause, compute_budget, dataset_version), 98 `RUN_IDENTITY` (one per
search family: `MIXED_CONFIG`, with the recommendation to confirm grid-vs-leak), and 11
`AGGREGATION_MEMBERSHIP` (5 `HIGH` "aggregation contains runs the project marked as excluded" for
the `@all_completed` counterfactuals, 5 `MEDIUM` "aggregation excludes runs", 1 `MEDIUM`
"discovered run count differs from the declared protocol" for `STM300_EVAL/samyrux_stm300`).
Severity distribution: 8 `HIGH`, 318 `MEDIUM`. Each carries entity, evidence lines and a
recommendation addressed to a human — the tool reports, it does not decide.

## 14. CLI

```
experiment-doctor scan   PATH [--json FILE] [--adapter NAME]
experiment-doctor audit  PATH  [-o DIR]     [--adapter NAME] [--reported-table FILE]
experiment-doctor adapters
```

`scan` prints the JSON summary (families, runs by status, artifact inventory by type, provenance
coverage); `audit` runs the five checks and writes `DIR/report.json` + `DIR/report.md`; `adapters`
lists what each adapter understands and its options. `--reported-table` requires `--adapter` and is
rejected with a `BadParameter` if the adapter takes no such option. Auto-selection is never forced:
`select_adapter()` scores the verification project at 1.0 for `gmmvi-exp3` in under a second, and
the generic fallback catches everything else. A full `audit` of the verification project (11971
artifacts, 3483 runs, 219 aggregations) takes about 30 seconds including the directory walk. The
CLI is exactly these three commands — no serve/watch/fix/sync/upload.

## 15. Unit Tests

16 tests, all passing in ~1s, no network, no GPU, no dependence on the real project:

| module | tests |
| --- | --- |
| `test_provenance.py` | `test_provenance_status`, `test_conflicting_provenance` |
| `test_scanner.py` | `test_generic_scanner`, `test_classify_does_not_invent_semantics` |
| `test_audit_checks.py` | `test_run_identity`, `test_unknown_seed_not_inferred`, `test_duplicate_seed`, `test_metric_direction`, `test_membership_exclusion`, `test_membership_unknown_without_a_rule` |
| `test_aggregation.py` | `test_aggregation_population_std`, `test_aggregation_sample_std`, `test_aggregation_mismatch`, `test_negated_metric_transform` |
| `test_gmmvi_adapter.py` | `test_gmmvi_small_fixture`, `test_gmmvi_exclusion_prose_binding` |

`tests/fixtures/mini_gmmvi/` is a miniature project: fetch declarations, 9 result slots of which
2 carry the `.csv.bad` marker, cw2 configs whose eval and hyperopt protocols disagree on
`repetitions` (3 vs 1) under the same group name, a `num_detected_modes` secondary that must come
out MAXIMIZE while `-elbo`/`MMD:` come out MINIMIZE, and one README exclusion bullet naming the
family that dropped two seeds. Every expected number in the fixture tests is hand-computable:
means 11.0 / 1.5 / 6.0 / 9.0, spreads `3·std/√N` with population std, and the `@all_completed`
counterfactual mean 75.75 over 4 slots against 1.5 over the 2 surviving ones. Two paths are not
reachable in that fixture and are covered elsewhere: the negated `*-fb:` transform
(`test_negated_metric_transform`, synthetic project) and the misspelled-bullet tie-break
(`readme_claim_coverage` in the golden acceptance — the real README writes "SEPRUX" for
`sepyrux_planar_4`). The fixture is regenerated by `scripts/make_mini_fixture.py` so it can never
drift from its generator.

## 16. GMMVI Golden Acceptance

`scripts/run_gmmvi_acceptance.py --repo <path> --data-root <path> [--reported-table <json>] -o
acceptance.json` — no baked-in absolute paths, not part of `pytest`, runs only when invoked
explicitly. It rebuilds the project through the adapter, audits it, and checks 21 named
expectations against the Phase 0 forensic oracle. Current result: **21/21 passed**, exit 0
(`tmp/acceptance.json`):

```
total_runs 3483 · total_families 205 · family_split [eval 107, search 98] · evaluation_runs 1090
membership_counts [included 1068, excluded 22] · excluded_status_vocabulary ['COMPLETED_EXCLUDED']
aggregation_records 219 · normal_family [10 runs, 10 included, declared 10]
excluded_family_reconstruction [10 slots, 5 included, 5 excluded]
both_memberships_recomputed [included N=5, all_completed N=10, counterfactual 29.24 ± 35.53, rule INFERRED]
readme_claim_coverage = the 5 families Phase 0 listed · metric_direction_evidenced
reported_vs_recomputed {match 36, mismatch 0, other 0}
+ 7 unknown_stays_unknown checks (seed, code_commit, tracker_run_id, parent_run_id,
  start_time, end_time, repetition_index)
```

## 17. Phase 0 Comparison

Every Phase 0 headline number is reproduced by v0.1 from the artifacts themselves — 3483 runs,
205 families (107/98), 1090 evaluation runs, 1068 included / 22 excluded, 219 aggregation records,
the 10=5+5 reconstruction of `sepyfux_planar_4`, the same five families carrying README exclusion
claims, and all 36 published Table 8 cells matching to printed precision. Seeds remain
unrecoverable in both; `termination_cause`, `code_commit`, tracker ids and timings remain
`UNKNOWN` in both. No disagreement was found: Phase 0's forensic reconstruction held up under
independent recomputation, including the `SEPRUX` mispelling binding and the eval-vs-hyperopt
`repetitions` conflict, both of which v0.1 re-derives from source.

Per the baseline, Phase 0 numbers appear only as *expectations* inside the acceptance script and
as test oracle; `src/` contains no project constants, no `if project == "gmmvi"`, and the tool
never reads `EXPERIMENT_DOCTOR_PHASE0_REPORT.md`. The published values it compares against are an
external input file whose `source.capture` sha256 pins the PDF transcription it came from.

## 18. Known Limitations

1. **`COMPLETED_INCLUDED` doubles as the status of search runs.** The `RunStatus` vocabulary is
   Phase 0-frozen and has no member for "completed, membership undefined", so 2393 search runs
   carry `COMPLETED_INCLUDED` while their `included_in_aggregation` is `UNKNOWN`. The per-field
   grade is the authoritative signal; the enum is a compromise and is documented as such.
2. **Tolerances are derived from printed precision.** A published cell rounded to 2 decimals
   gives ±0.005 (×1+1e-9). `MATCH` therefore means "consistent with the printed digits", not
   "bit-identical", and a genuinely wrong value inside that half-width would pass.
3. **Only `statistic="mean"` is recomputed.** Any median/best-of aggregation would come out
   `UNKNOWN` by construction (and GMMVI publishes means, so v0.1 covers its target).
4. **Rerun lineage is unrecoverable.** When a slot holds a rerun, the older attempt leaves no
   trace once overwritten, so `parent_run_id` is `UNKNOWN` for every run and slot counts cannot
   distinguish "10 seeds" from "8 seeds + 2 retries".
5. **Membership for search families has no rule to grade**, so 2393 runs sit at `UNKNOWN`
   membership; v0.1 reports the gap rather than assuming grid results are independent runs.
6. **Folder collisions are noted, not resolved.** Four `*_EVAL` result folders (`BC_EVAL`,
   `BCMB_EVAL`, `GC_EVAL`, `GCMB_EVAL`) are written by fetch declarations from two different
   tracker projects; the surviving CSV columns say which fetch produced them, and the adapter
   records that as a discovery note instead of guessing.
7. **`.bad` is the only membership marker v0.1 knows.** A project that excluded runs by some
   other convention yields `UNKNOWN` membership until an adapter is written for it.
8. **One adapter.** v0.1 has been validated against exactly one real project. The generic
   scanner is project-agnostic but semantically mute, so "ready for a second project" means
   "the adapter protocol holds", not "it will already work".

## 19. What Was Deliberately Not Built

No verdict vocabulary (SAFE/INVALID/RISKY), no statistical tests of any kind (significance,
p-values, bootstrap, multiple-comparison correction), no cherry-picking or misconduct judgement,
no re-execution of training, no checkpoint/tensor inspection, no W&B or other online mutation, no
config synthesis or metadata back-filling, no renaming of runs, no HTML/dashboard/GUI, no web
service, no database, no cloud sync, no plugin system, no DAG engine, no LLM analysis, no
multi-agent orchestration, no Paper/Result Doctor, no PyPI publication, and no second real
project. The dependency list stayed at three runtime packages; no numpy/scipy/pandas were needed
because `math` covers the arithmetic actually required.

## 20. Recommended v0.2

1. **A second real project, chosen adversarially** — something with a tracker-exported run index
   (MLflow/W&B export) rather than `.csv.bad` filenames, to test whether the adapter protocol and
   the membership model generalise. This is the single highest-value item; everything else is
   refinement.
2. **Rerun/attempt lineage**: an `attempts[]` list per slot and a documented way to record that a
   slot was overwritten, so slot counts stop pretending to be seed counts.
3. **Split `seed_derivation` into a graded rule plus an operand status**, instead of the note on an
   `UNKNOWN` field it is now: `rule = "start_seed + rep"` is code-CONFIRMED for GMMVI while
   `operand = start_seed` is unrecoverable. Reported separately, "ten consecutive seeds by
   construction, value unknown" stops being conflated with "nothing is known about the seeds", and
   the search-side fixed-seed case (`seed = 1`) becomes a first-class
   `DUPLICATE_SEEDS`-adjacent finding instead of prose.
4. **More statistics**: `median`, `best`, `last` in the recomputation check, each with its own
   declared convention, plus a `statistic` inferred-from-code path.
5. **Evidence-grade diffing between runs of the tool**: a stable `--baseline report.json` so a
   second audit shows what changed in the *provenance* of a project, not just its numbers.
6. **Adapter ergonomics**: keep adapters declarative as long as possible (gmmvi's semantics are
   mostly "these files mean these things"), and record name-collision/`--adapter` override
   behaviour in one doc rather than in code comments.

Explicitly still out of scope for v0.2: verdicts, significance testing, and any write path.
