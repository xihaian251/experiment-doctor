# Changelog

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
