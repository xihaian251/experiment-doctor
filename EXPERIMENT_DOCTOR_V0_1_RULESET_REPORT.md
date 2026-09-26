# Experiment Doctor v0.1 Formal Rule Set

## 1. Scope

This round converts the problems that two real projects already evidenced into the first
formal rule set of Experiment Doctor v0.1: exactly ten rules, `ED001`–`ED010`, built on the
frozen unified schema and evaluated read-only over a scanned project.

| item | value |
| --- | --- |
| working directory | `F:\MLResearch\experiment-doctor\v0.1` |
| baseline commit (MVP) | `10c66f91efa2abb4e2178aa020f27180c444890f` |
| acceptance-1 commit (TorchSSL adapter) | `c58a6b18e83e3dfcdaedb5623c444dc71b520b83` |
| remotes / tags | 0 / 0 (no remote, no push, no tag, no PyPI, no release) |
| projects used | gmmvi (Experiment 3, Phase 0 forensics) and TorchSSL (acceptance 1) |
| new code | `src/experiment_doctor/rules/` (1,637 lines incl. `base.py`), `adapters/aggregation_claims.py` (285), `scripts/run_rule_acceptance.py` (562), `tests/test_rules.py` (900), `docs/rules/` (10 contracts) |

Explicitly out of scope, and not done: a third project, more adapters, an `ED011`,
GUI/Web/LLM/Agent, any statistical significance machinery, and any change to the model
training or to the upstream repositories (both were opened read-only).

## 2. Rule Semantics

A rule answers one question about one entity: *is this experimental claim supported by the
artifacts that exist?* It never answers whether the experiment was well designed.

Four invariants hold across all ten rules:

1. **Evidence grade is not status.** `ProvenanceStatus` (`CONFIRMED`/`SUPPORTED`/`INFERRED`
   /`UNKNOWN`/`CONFLICTING`) describes how well a value is attested; `RuleStatus` describes
   what the check concluded. Absence of evidence produces `INCONCLUSIVE`, never `FAIL`.
2. **Measurements never feed a status.** `best_minus_last`, `family_excluded_runs`,
   `declared_repetitions` and the tolerances are reported so a reader can see what the check
   looked at; none of them is compared against a hidden threshold.
3. **Recommendations never feed a status.** They say what to record or check next. The tool
   stays read-only.
4. **No motive, no accusation.** The rule text never uses `cherry-pick`, `misconduct`,
   `fraud`, `malicious`, `dishonest` or `suspicious`; a test sweeps every result of every
   rule against that vocabulary.

## 3. Status Model

`RuleStatus` is frozen at five values, and nothing else exists:

| status | meaning |
| --- | --- |
| `PASS` | checked, and the artifacts agree with the claim |
| `FAIL` | checked, and the artifacts contradict the claim |
| `INCONCLUSIVE` | the claim could not be checked with the evidence available |
| `NOT_APPLICABLE` | the claim does not exist for this entity, so there is nothing to check |
| `NOT_RUN` | the tool could not execute the check |

`NOT_APPLICABLE` is produced by `ED002` (hyperparameter-search family; family with no runs),
`ED005`/`ED006` (record the project never published a number for), `ED001` (fewer than two
runs) and `ED008` (no `±` published). `ED003`, `ED004`, `ED007`, `ED009` and `ED010`
deliberately have no `NOT_APPLICABLE` branch: an unelectable comparison stays
`INCONCLUSIVE` so the counts report honestly what was actually checked. `NOT_RUN` is emitted
only by the engine when a rule raises, so a broken check remains visible instead of
disappearing.

## 4. Severity Model

`Severity` (`INFO`, `LOW`, `MEDIUM`, `HIGH`) was already in the schema and is unchanged. It
is assigned per status, independently of the evidence:

- `FAIL` → `HIGH` (every rule),
- `INCONCLUSIVE` and `NOT_RUN` → `MEDIUM` (never `HIGH`: nothing has been contradicted),
- `NOT_APPLICABLE` → `INFO`,
- `PASS` → `INFO`.

`LOW` is in the vocabulary but no rule currently emits it; that is reported rather than
padded with a calibration that has no evidence behind it. Two tests pin the model: no
uncertain status may carry `HIGH`, and severity is derived, never hand-set per project.

There is no overall verdict, no total score, and no confidence number. `status_counts()`
returns per-rule counts and the markdown report states that no combined score exists.

## 5. Rule Engine

```
scan → adapter reconstruction → schema objects → audit (5 checks) → rules (10) → report
```

- `Rule` (`rules/base.py`) is an ABC with `rule_id`, `title`, `purpose`, `entity_type`, three
  severity defaults and one method, `evaluate(context) -> list[RuleResult]`. There is no
  scheduler, no dependency graph, no plugin discovery and no entry-point loading: ten rules
  do not need any of that.
- `RuleContext` gives a rule the scanned project plus the five audit outputs
  (`identity`, `seeds`, `membership`, and the per-record audit mutations), and helpers:
  `runs_of`, `family`, `run`, `attached_to_run`, `claim_comparison`, `sources_of`.
  `attached_to_run` is what separates runtime evidence from a declaration: a field qualifies
  only when its source path is one of that run's own artifacts.
- `RULES` is a plain tuple in `ED001`–`ED010` order; `run_rules()` evaluates them in
  sequence and turns a raised exception into a visible `NOT_RUN` result.
- `rule_catalog()` is the machine-readable registry, exposed by
  `experiment-doctor rules` and `experiment-doctor rules --json` — the only new command this
  round, and it only reads the registry.
- `report.md` gains a `Rule Results` section: a per-rule summary table first, then
  contradictions (`FAIL`) with entity ids, then open questions (`INCONCLUSIVE`) with their
  limitations, then `PASS`/`NOT_APPLICABLE` aggregated per rule. `report.json` keeps every
  `RuleResult` in full plus the counts.
- `RuleResult` fields: `rule_id`, `title`, `entity_type`, `entity_id`, `status`, `severity`,
  `summary`, `evidence`, `measurements`, `limitations`, `recommendation`.

CLI commands `scan`, `audit`, `adapters` keep their behaviour; `audit` now also runs the ten
rules and prints `rules=N rule_fail=… rule_inconclusive=…`.

## 6. ED001 Run Identity Consistency

*Do the runs of one family differ on anything but randomness?* Entity: `family`.

| status | condition |
| --- | --- |
| PASS | identity fields agree and every differing config key is one a repetition legitimately carries (seed, ids, slot, config path); or the family is a labelled search family |
| FAIL | two runs of one family carry different evidenced `method`/`task`/`dataset`/`dataset_version` |
| INCONCLUSIVE | configs differ and no recorded dimension explains it; or nothing about identity is evidenced |
| NOT_APPLICABLE | fewer than two runs discovered |

The unexplained-difference branch cannot be closed in v0.1: no artifact states which
dimensions a family *intends* to vary, so the rule says so and asks for that to be recorded.

## 7. ED002 Seed Provenance Integrity

*Are independent repetitions backed by distinct, recorded seeds?* Entity: `family`.

`FAIL` requires evidence: `CONFLICTING` per-run artifacts, or a duplicated value among
evidenced seeds. Zero evidenced seeds is `INCONCLUSIVE` whose evidence line always carries
"the run count is not evidence of distinct seeds: a project may rerun the same seed, and a
slot index is not a seed". A `HYPERPARAMETER_SEARCH` family is `NOT_APPLICABLE` — its runs
are not replicates, whatever their N. Prose seed lists are never counted as evidence.

## 8. ED003 Historical Code Provenance

*Does an artifact identify the code revision this run executed?* Entity: `run`.

A revision qualifies only when it is evidenced **and** cited to one of the run's own
artifacts. A value named by a repository file gives `INCONCLUSIVE` ("a revision is named, but
not by anything this run produced"), and total absence gives the canonical sentence
`historical code identity cannot be established from available artifacts`. The current
checkout is never substituted for history in any branch. There is no `NOT_APPLICABLE`.

## 9. ED004 Resolved Configuration Provenance

*Does a run-local artifact hold the effective configuration?* Entity: `run`.

PASS requires the config's source to be one of the run's artifacts. A repository YAML,
template or launcher default yields `INCONCLUSIVE` with the limitation that runtime overrides
applied after the declaration was read cannot be ruled out from it. `CONFLICTING` artifacts
`FAIL`. Parameters the run never recorded are counted and listed, not silently completed.

## 10. ED005 Metric Selection Provenance

*Which observation of a run does the reported metric stand for?* Entity: `aggregation`.

`claim_comparison(implemented, documented)` classifies the pair; the status follows the
classification. `contradiction` (prose says last, code consumes best) and
`conflicting-evidence` → `FAIL`; `consistent` and `implementation-only` → `PASS`;
`documentation-only` and `undetermined` → `INCONCLUSIVE` as an explicit evidence gap; a
record with no published number → `NOT_APPLICABLE`.

`best != last` is a measurement, never a defect: when both are available the rule reports
`family_best_mean`, `family_last_mean`, `best_minus_last` and keeps `PASS` with a limitation
stating that the difference is a property of the metric.

## 11. ED006 Aggregation Membership Provenance

*Which runs are inside the published mean, and is that traceable?* Entity: `aggregation`.

The governing distinction: **excluded runs existing is not a finding; untraceable membership
is.** A family that marks six runs excluded and publishes the rest with an evidenced
membership rule PASSes, and its summary enumerates them. `FAIL` is reserved for the case
where the published (`included`) set contains runs the project itself marks as excluded.
Unresolved member ids, unevidenced per-run membership, or an unevidenced rule → `INCONCLUSIVE`.
An exclusion reason that lives only in prose (a `run.csv.bad` rename, a README sentence) is
recorded as an evidence gap about the *reason*; no intention is attributed.

## 12. ED007 Aggregation Numerical Consistency

*Does the published aggregate come back out of the member runs' numbers?* Entity:
`aggregation`.

Arithmetic only, against the audit's recomputation and the printed-precision tolerances:
`MATCH` → `PASS`, `MISMATCH` → `FAIL` with the summary naming `mean` and/or `spread`, any
missing input → `INCONCLUSIVE` listing which ones. v0.1 recomputes `mean` only, so a published
median is `INCONCLUSIVE`, never `FAIL`. The recommendation for a mismatch tells the project to
find the differing membership/reduction/sign convention and explicitly not to widen the
tolerance.

## 13. ED008 Spread Semantics Consistency

*What is the quantity after the `±`, and does the project say the same thing twice?* Entity:
`aggregation` (cells that publish a spread).

Six-value vocabulary (`standard_deviation`, `standard_error`, `scaled_standard_error`,
`confidence_interval_half_width`, `custom`, `unknown`), with the implemented side evidenced by
the aggregation line that computes it and the documented side quoted from the project's prose.
`ddof`, `display_multiplier` and `n` are reported but **alone never produce a FAIL** —
population-vs-sample is a convention. Only a documented/implemented mismatch or mutually
incompatible accounts fail; a spread whose identity no artifact fixes is `INCONCLUSIVE`; a
cell with no `±` is `NOT_APPLICABLE`.

This rule found the real contradiction in TorchSSL (section 19). Three regressions in
`tests/test_rules.py` pin the semantics so a future change cannot quietly re-declare every
`±` a standard error: prose-std + population-std code → PASS, prose-SE + population-std code →
FAIL, bare `± 0.1` → INCONCLUSIVE.

## 14. ED009 Termination Provenance

*Does an artifact say why this run stopped?* Entity: `run`.

PASS needs a recorded cause other than `unknown`. Mutually exclusive causes → `FAIL`. No
recorded cause → `INCONCLUSIVE` with the firewall sentence: UNKNOWN "does not mean the run
failed, was stopped early or was abandoned". A `TRUNCATED_TIME_LIMIT` run whose cause is
recorded still PASSes, with a limitation noting its final value measures an unfinished
schedule — recorded, not judged. A status marker on a result slot is never promoted to a cause.

## 15. ED010 Runtime Environment Provenance

*Can the software and hardware a historical run executed on be established?* Entity: `run`.

A dependency declaration in the repository states intent, not what a months-old machine
loaded, so **a declaration never produces PASS** and the standard is not lowered to manufacture
one. PASS requires the environment value cited to one of the run's own artifacts; `compute_budget`
coverage is reported as a limitation when hardware is unrecorded. The rule also reports
`declared_environment_files` so the reader can see that a declaration exists and was still
refused as runtime evidence.

## 16. False-Inference Firewall

Every forbidden inference in the baseline is a test, not a comment. Nine `test_firewall_*`
functions plus three engine-level tests:

| must never happen | test |
| --- | --- |
| UNKNOWN seeds → duplicate-seed FAIL | `test_firewall_unknown_seeds_never_become_a_duplicate_seed_failure` |
| `run_0`/`run_1` (or a slot index) read as seeds | `test_firewall_slot_and_run_index_are_not_counted_as_seeds` |
| UNKNOWN commit → provenance FAIL | `test_firewall_unknown_commit_is_inconclusive_not_failed` |
| repo YAML → historical configuration PASS | `test_firewall_repository_yaml_never_proves_the_historical_configuration` |
| unattributed number → selection defect | `test_firewall_an_unattributed_number_is_an_evidence_gap_not_a_selection_defect` |
| excluded runs existing → membership FAIL | `test_firewall_excluded_runs_never_make_membership_provenance_fail` |
| `.csv.bad` → an interpreted deletion motive | `test_firewall_an_unexplained_exclusion_is_recorded_as_an_evidence_gap` |
| population-vs-sample std alone → spread FAIL | `test_firewall_population_versus_sample_std_alone_is_never_a_failure` |
| repo `environment.yml` → runtime environment PASS | `test_firewall_a_repository_environment_file_never_passes_runtime_provenance` |
| any accusation label in any result | `test_no_result_of_the_synthetic_set_names_an_accusation` |
| uncertain status calibrated as HIGH | `test_uncertain_results_are_never_calibrated_as_high_severity` |
| a rule silently vanishing | `test_run_rules_reports_a_failing_rule_as_not_run_rather_than_losing_it` |

`best != last → FAIL` and `excluded runs → FAIL` are additionally covered positively:
`test_ed005_reports_best_minus_last_as_a_measurement_not_a_defect` asserts `PASS` *while*
`best_minus_last` is non-zero, and the GMMVI acceptance check asserts zero `ED006` FAILs *while*
`family_excluded_runs` reaches 6.

## 17. Unit Tests

```
python -m pytest -q            →  95 passed
  of which tests/test_rules.py →  66 (rule branch semantics + firewall + engine contracts)
```

Coverage follows the baseline's rule: every rule gets at least one positive path and one
uncertainty/failure path, with the emphasis on branch semantics rather than a mechanical
10 × 5 status grid. The tests build synthetic projects from the unified schema only — none of
them opens a fixture directory — so a status can only come from what the rule reads off a
schema object. Additional contracts: the registry holds exactly ten general rules, each rule
emits exactly one result per entity of its own kind, `status_counts` is counts without a
score, and audit and rules agree on what a published cell claims (same record, same
comparison status).

Gates (all green, in the required order): `pytest` 95 passed · `ruff check .` clean ·
`ruff format --check .` clean (53 files) · `mypy src scripts tests` clean (39 files) · hardcode
grep over `src/experiment_doctor/rules/` empty.

`mypy tests` carried 9 pre-existing errors from the acceptance-1 round (unions never narrowed
in `tests/test_torchssl_adapter.py` and `tests/test_aggregation.py`). They are fixed here by
adding the missing `is not None` assertions — behaviour of those tests is unchanged, and the
documented gate line in `README.md` now actually passes.

## 18. GMMVI Rule Results

One scan of the real project: 3,483 runs, 205 families, 219 aggregation records of which 36
carry a published number, 15,218 rule results.

| rule | statuses | reading |
| --- | --- | --- |
| ED001 | PASS 205 | repetition families vary on seed/slot only; search families excused by their own `kind` label |
| ED002 | NOT_APPLICABLE 98, INCONCLUSIVE 107 | 98 search families; 107 repetition families with `runs_with_seed_evidence = 0` — seed provenance cannot be established, and nothing is called duplicated |
| ED003 | INCONCLUSIVE 3483 | every run carries the canonical absent-revision wording; the present checkout was never substituted |
| ED004 | PASS 3483 | the project archived a resolved config per run inside that run's own folder |
| ED005 | NOT_APPLICABLE 183, PASS 36 | published cells are `last` and the code and the README both say `last` (`to_numpy()[-1]` vs "the final performance for every run in csv-files") |
| ED006 | NOT_APPLICABLE 183, PASS 36 | 0 FAIL with up to 6 excluded runs per family, enumerated separately; membership rule evidenced from `fetch_exp3.py` |
| ED007 | INCONCLUSIVE 183, PASS 36 | e.g. 11.47 ± 0.04 published vs 11.466954 ± 0.040358 recomputed at tolerance 0.005; the 183 reconstructions are unelectable, not disagreed with |
| ED008 | NOT_APPLICABLE 183, PASS 36 | `3 x std / sqrt(N)` → `scaled_standard_error`, evidenced by the computing line, with no contrary prose; the prose never names the statistic |
| ED009 | INCONCLUSIVE 3483 | the archived histories have no terminal marker; no cause was invented |
| ED010 | INCONCLUSIVE 3483 | declarations exist (`requirements.txt` + two SLURM templates, `declared_environment_files = 3`) and none of them is runtime evidence |

No GMMVI cell was forced into a PASS to make the table look better: the project's three
biggest gaps (seeds, revisions, termination causes, environments) show as `INCONCLUSIVE`
exactly as forensics described them.

## 19. TorchSSL Rule Results

One scan: 6 runs, 2 families, 4 aggregation records of which 2 carry a published number, 44
rule results.

| rule | statuses | reading |
| --- | --- | --- |
| ED001 | PASS 2 | three runs per family, one evidenced method/task/config |
| ED002 | PASS 2 | seeds 0/1/2 read from each log's own `Arguments.seed`; the PASS still reports that `declared_repetitions` is not asserted because README and `config_generator.py` disagree |
| ED003 | INCONCLUSIVE 6 | the logs record the command, not the revision |
| ED004 | PASS 6 | the log's `Namespace` dump is run-local runtime evidence |
| ED005 | PASS 2, NOT_APPLICABLE 2 | `best` documented and `best` consumed; `best_minus_last` measured at +0.293 and +0.230 points without changing the status |
| ED006 | PASS 2, NOT_APPLICABLE 2 | 3 evidenced members, no exclusions |
| ED007 | PASS 2, INCONCLUSIVE 2 | 95.14 ± 0.05 and 95.02 ± 0.09 recompute from the three logged accuracies |
| ED008 | **FAIL 2**, NOT_APPLICABLE 2 | documented `standard_error` vs implemented `standard_deviation` (`ddof=0`, multiplier 1.0, n=3) |
| ED009 | PASS 6 | cause `iteration_cap`, read from the final evaluation iteration with the shipped break condition cited |
| ED010 | INCONCLUSIVE 6 | the conda pins come from the repository's `environment.yml`, never from the run |

The counts were produced by the entity granularity the schema gives, not by hardcoding these
rows: `ED001`/`ED002` are per family (2), `ED003`/`ED004`/`ED009`/`ED010` per run (6),
`ED005`–`ED008` per aggregation record (4).

## 20. Cross-Project Rule Acceptance

`scripts/run_rule_acceptance.py` takes four project paths plus two reported tables, writes
`rule_acceptance.json`, and was run once: **19/19 checks passed** (~33 s). It checks rule
behaviour only — which statuses a rule may and may not produce for artifacts that look like
this — and repeats none of the 21 or 46 structural assertions that already exist.

- GMMVI (7): `gmmvi_ed002_unknown_seed_stays_inconclusive`,
  `gmmvi_ed006_exclusions_do_not_fail_membership`, `gmmvi_ed007_published_cells_recompute`,
  `gmmvi_ed008_spread_formula_recovered_without_a_fail`,
  `gmmvi_ed009_termination_is_not_invented`, `gmmvi_ed003_no_historical_commit`,
  `gmmvi_ed010_environment_declared_not_recorded`
- TorchSSL (8): `torchssl_ed002_recorded_seeds_pass`,
  `torchssl_ed005_best_selection_documented_and_honoured`,
  `torchssl_ed007_published_cells_recompute`, `torchssl_ed008_finds_the_standard_error_claim`,
  `torchssl_ed009_terminal_marker_is_read`, `torchssl_ed004_runtime_configuration_is_run_local`,
  `torchssl_ed010_environment_is_not_recorded_by_the_run`, `torchssl_ed003_no_historical_commit`
- Cross-project (4): `same_ten_rules_on_both_projects`, `entity_granularity_holds`,
  `rules_contain_no_project_hardcode`, `inconclusive_is_never_calibrated_as_high`

**The six questions the baseline requires answered:**

**A. Can two unrelated projects use the same ten rules without project-specific rules?**
Yes. The registry is identical for both, the per-project rule-id sets are equal
(`same_ten_rules_on_both_projects`), `entity_granularity_holds` shows each rule emits one
result per entity of its own kind in both projects, and the hardcode grep over `rules/` is
empty (`rules_contain_no_project_hardcode`). All project knowledge stayed in `adapters/`.

**B. Which rules really produce PASS/FAIL, and which mainly produce INCONCLUSIVE?**
Rules that compare an artifact against an artifact produce decisive outcomes on both projects:
ED004 (PASS 3,483 + 6), ED007 (PASS 36 + 2), ED006 (PASS 36 + 2), ED005 (PASS 36 + 2), ED001
(PASS 205 + 2), ED002 (PASS 2 on TorchSSL), ED009 (PASS 6 on TorchSSL). ED008 produced the
round's only FAILs (2). Rules that ask about a *historical fact* the projects never recorded
mainly produce INCONCLUSIVE: ED003 (3,489 results, all INCONCLUSIVE), ED010 (3,489, all
INCONCLUSIVE), ED009 on GMMVI (3,483), ED002 on GMMVI (107 + 98 NOT_APPLICABLE).

**C. Is UNKNOWN preserved, with no false inference?**
Yes. Zero FAIL results anywhere in either project except ED008's two, and each of those is
backed by a cited contradiction, not an absence. The seed/commit/environment/exclusion/spread
firewalls are tests (section 16) and acceptance checks (section 20), and GMMVI's 107
seed-gap families carry the explicit "the run count is not evidence of distinct seeds" note.

**D. Was TorchSSL's "standard errors" vs actual population std found independently by ED008?**
Yes, and only by ED008. ED007 PASSes on the same two cells (the central values and the printed
spread recompute), so no arithmetic disagreement was available to hint at it; the finding came
from comparing the README's prose statistic against the line in `scripts/average_log.py` that
computes the spread. `test_ed008_findings_are_independent_of_the_arithmetic_comparison` pins
that independence structurally.

**E. Does ED006 still judge membership provenance correctly on GMMVI, despite exclusions?**
Yes. Exclusions are present (`family_excluded_runs` up to 6) and `ED006` yields 0 FAIL, 36
PASS and 183 NOT_APPLICABLE, with the excluded runs enumerated separately in the PASS summary
and unevidenced reasons recorded as evidence gaps.

**F. Are the rules really built on the unified schema?**
Yes. Every rule consumes `ExperimentProject` / `ExperimentRun` / `ExperimentFamily` /
`AggregationRecord` plus the audit's outputs; none opens a file. The rule tests prove it the
other way round: they construct schema-only synthetic projects without touching a fixture
directory and still reach every branch. The schema grew only by additive, project-neutral
slots (`SpreadSemantics`, `SelectionPolicy`, four evidence-graded fields on
`AggregationRecord`); no existing field, enum or invariant was redesigned or removed, and
`SpreadBasis` from acceptance 1 is untouched.

## 21. Legacy Regression

Both legacy acceptances were run once each, in the required order, and neither was
renumbered or edited:

| script | result | output |
| --- | --- | --- |
| `scripts/run_gmmvi_acceptance.py` | **21/21 checks passed** | `tmp/acceptance_gmmvi_rules_round.json` (`reported_vs_recomputed: match 36, mismatch 0`) |
| `scripts/run_torchssl_acceptance.py` | **46/46 checks passed** | `tmp/acceptance_torchssl_rules_round.json` |

The 67 existing assertions therefore still hold against the rules-era code, including the
adapters' claim extraction (which is what now feeds `implemented_spread` and friends). No
external acceptance was run more than once in this round.

## 22. Known Limitations

1. **One `environment` field, two meanings.** `schema.ExperimentRun.environment` is a single
   string, and the GMMVI adapter fills it with the *task* environment (a config
   `experiment_id` such as `breast_cancer`), while ED010 asks about the *runtime software*
   environment. The status is unaffected — the value is cited to a repository file, so it is
   `INCONCLUSIVE` either way — but the evidence string can name a task where a reader expects
   versions. Registered as a P1 schema question; not fixed this round, because the rules must
   sit on the frozen schema.
2. **`declared_environment_files` undercounts.** It counts `ArtifactType.ENVIRONMENT` entries
   in the project artifact inventory. TorchSSL ships `environment.yml` and the adapter cites
   it, but the scanner never registers it as a project artifact, so the measurement reads 0
   while the declaration exists. The rule's behaviour is still correct (declaration ⇒ never
   PASS); the measurement is just incomplete.
3. **ED005's delta depends on a naming convention.** `best_minus_last` is computed from the
   tool's `@best`/`@last` metric-name suffixes, which the adapters produce; a project whose
   columns are named otherwise yields no delta, and the rule reports nothing extra rather
   than guessing.
4. **ED001 cannot see intended variation.** It can only explain a differing config key when
   the value equals one of that run's own identifiers, so a family that legitimately varies a
   nested dimension lands in `INCONCLUSIVE`. Closing this needs a per-family "varying
   dimension" artifact that v0.1 does not have.
5. **ED007 recomputes the mean only.** Any other statistic is `INCONCLUSIVE` by construction,
   and the rules read the audit's mutated records, so an audit recomputation bug would
   propagate into ED007 unnoticed — mitigated, not eliminated, by the audit/rules agreement
   test.
6. **ED009's TorchSSL PASS rests on an adapter attestation.** It joins the log's final
   evaluation iteration to the break condition in the shipped training code. That is stronger
   than inference from a history's shape, but weaker than an explicit "terminated because"
   marker, and the citation is carried in the evidence so a reader can weigh it.
7. Coverage is branch-semantic, not exhaustive: v0.1 has no per-rule status-matrix test, and
   `LOW` severity is never emitted by a rule today.

## 23. Deliberately Deferred Work

Not started, by decision rather than oversight: a third real project; any further adapter;
`ED011` and beyond; an overall verdict, score, or confidence number; statistical
significance, bootstrap, p-values or multiple-comparison handling; automatic fairness or
representativeness judgement; a cherry-picking detector; Paper Doctor or Result Doctor;
LLM, Agent, GUI, Web or cloud components; a PyPI release, tag, remote or push. The version
stays local v0.1 development.

## 24. Recommended Next Step

Fix the two schema-surface issues that this round's own measurements exposed, without touching
rule logic: split `environment` into a runtime-environment and a task-environment slot (or
stop the GMMVI adapter writing the task id into it), and register repository-level dependency
files as project artifacts so `declared_environment_files` counts what a reader can verify.
Both need one added test each, plus the same three gates. After that, the rule set is stable
enough to be *used* rather than extended: run `ED001`–`ED010` as a routine step at the moment
a result table is transcribed, which is where a documented-vs-computed spread contradiction
like ED008's can still be caught before it is published.
