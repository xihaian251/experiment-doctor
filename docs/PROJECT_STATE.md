# Project State

- Status: **published 0.1.0** (2026-09-27).
  - Release commit / tag: `v0.1.0` -> `7c9e5506efecb7f0b96b038bd431783329d0c895`
  - GitHub: <https://github.com/xihaian251/experiment-doctor> (public),
    Release <https://github.com/xihaian251/experiment-doctor/releases/tag/v0.1.0>
  - PyPI: <https://pypi.org/project/experiment-doctor/0.1.0/>
    (wheel + sdist, not yanked, uploaded via GitHub Actions Trusted Publishing)
- Version source: `src/experiment_doctor/__init__.py:__version__`, consumed
  dynamically by `pyproject.toml`.
- Architecture: validated (frozen this round; no schema/rule/adapter-core
  changes during hardening).
- Real-world projects validated: **3** (GMMVI, TorchSSL, CRDA).
  Acceptance evidence lives outside this repository
  (`F:\MLResearch\experiment-doctor\` acceptance directories).
- Formal rules: **10** (ED001–ED010).
- Adapters: **4** (generic, gmmvi-exp3, torchssl, crda).
- Known P0: **0**. Known P1: **0**.
- Known limitations:
  - Aggregation recompute supports the `mean` statistic and std/SE spread
    bases only; medians, CIs, and other estimators stay `UNKNOWN`.
  - `implemented_*` semantics assume the checked-out code is the producing
    code; for archived artifacts with unrecoverable history the honest grade
    is `CONFLICTING` (registered as CRDA-OBS-1, P2).
  - No first-class vocabulary for diagnostic quantities (e.g. gate p-values);
    they are modeled as non-aggregated, `UNKNOWN`-direction metrics
    (CRDA-OBS-2, P3).
  - `SourceRef.describe()` renders `<no source>` when only a `note` is set
    (CRDA-OBS-3, P3, cosmetic).
  - Read-only by design: no re-execution, no verdict, no composite score.
  - The 0.1.0 PyPI upload used Trusted Publishing (OIDC) but carries no SLSA
    provenance attestation (the publish workflow does not request
    `attestations: write`).
