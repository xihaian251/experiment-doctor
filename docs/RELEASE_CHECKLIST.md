# Release Checklist — Experiment Doctor 0.1.0

Run in order at release time (next round). Local hardening already completed
these through "fresh installs"; re-run anything older than the final commit.

1. Quality gates: `pytest -q`, `ruff check .`, `ruff format --check .`,
   `mypy src scripts tests` — all green on the release commit.
2. Working tree clean; HEAD is the intended release commit; version frozen in
   `src/experiment_doctor/__init__.py` matches the tag to be cut.
3. Build: `python -m build --outdir <release-dir>/dist .` → wheel + sdist.
4. Artifact hashes: record filename / size / SHA256 for both artifacts.
5. Inspect contents: no test-data of external projects, no `.git`, no caches,
   no absolute local paths, LICENSE + README + METADATA present and correct.
6. Fresh wheel install in a clean venv (non-editable): `pip check`,
   `import experiment_doctor`, `__version__`, `experiment-doctor --help`,
   `adapters`, `rules`, one small `scan` + `audit`.
7. Fresh sdist install in a second clean venv: same smoke.
8. CLI smoke: all five quick-start commands exit 0 on an unfamiliar directory
   without inventing PASS/FAIL results.
9. Create the GitHub repository, push, cut tag `v0.1.0`, publish GitHub
   Release with the two artifacts.
10. Reserve/claim the PyPI name (verified free on 2026-09-27), configure
    Trusted Publishing, upload via the official GitHub Actions workflow
    (`pypa/gh-action-pypi-publish`).
11. Post-publish: `pip install experiment-doctor` from PyPI in a clean venv
    and repeat step 6.
