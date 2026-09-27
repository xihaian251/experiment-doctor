# Changelog

## v1.0.0 — 2026-09-27

Additive: the v0.1 audit path, its rules, schema and acceptance adapters are
byte-for-byte unchanged, and its four commands behave as before. Release
decision recorded here; the distribution is not published yet.

- `experiment-doctor init` writes `experiment.lock.json`: code revision and
  working-tree state, interpreter / installed packages / platform, fingerprints
  of declared config and dataset paths, and explicitly declared seed and command.
- `experiment-doctor run -- COMMAND` wraps a command and writes
  `experiment.run.json` plus `stdout.log`/`stderr.log` into
  `experiment-evidence/`: observed argv, cwd, pid, start/end time, exit status
  from `wait()`, created/modified file digests, timeout state, and a
  `termination_status` that claims only a process outcome.
- `experiment-doctor verify` re-derives both seals and the run → lock hash chain
  and checks bundle presence, artifact digests and path boundaries (V001–V006).
- `captured` adapter maps an evidence bundle onto the existing provenance model,
  so ED001–ED010 evaluate against recorded observation instead of inference.
- Validation: 94 new tests (21 lock / 22 run / 19 verify / 32 audit
  integration), plus `scripts/run_v1_full_pipeline_check.py`, an end-to-end
  driver over four trees that must reproduce identical ED001–ED010 status
  vectors. Design and phase records: [docs/v1/](docs/v1/).
- Deliberately absent: metric extraction from stdout, training-outcome claims,
  budget capture, third-party tracker integration, compression/upload/signing,
  and any composite or confidence score.

## v0.1.0 — 2026-09-27

First release. Read-only provenance and aggregation auditor for ML experiment
artifacts.

- Project / family / run / metric / aggregation provenance model with
  per-field evidence grades (`CONFIRMED`, `SUPPORTED`, `INFERRED`, `UNKNOWN`,
  `CONFLICTING`) and `path:line/key` sources.
- Formal rules ED001–ED010 with five statuses (`PASS`, `FAIL`,
  `INCONCLUSIVE`, `NOT_APPLICABLE`, `NOT_RUN`); no composite verdict or score.
- Aggregation reconstruction: member-set binding, mean ± spread recompute
  against published cells, membership provenance including excluded runs.
- Spread semantics resolution (`standard_deviation` vs `standard_error`,
  ddof, display multiplier) with documented-vs-implemented contradiction
  detection.
- Runtime-environment vs declared-environment distinction (a requirements
  file is a declaration, never a runtime record).
- Adapters: generic fallback, `gmmvi-exp3`, `torchssl`, `crda`.
- CLI: `scan`, `audit` (JSON + Markdown report to a user directory),
  `rules`, `adapters`.
- Validated on three real research projects (GMMVI, TorchSSL, CRDA) via
  external acceptance suites.
