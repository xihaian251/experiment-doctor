#!/usr/bin/env python3
"""Phase 5 end-to-end golden: init -> run -> verify -> audit on a synthetic project.

Drives the real CLI in subprocesses -- no library shortcut -- over four isolated
copies of ``tests/fixtures/v1_full_project``:

* ``pre``         the fixture as committed: no bundle, no results yet.
* ``trad``        the traditional workflow: plain ``python train.py``, results on
                  disk, nothing versioned, no evidence bundle.
* ``cap``         the same tree audited twice: once with git history and results on
                  disk but **no bundle** ("before capture"), then after
                  ``init``, ``run -- python train.py`` and ``verify`` ("after
                  capture").  The only difference between the two audits is the
                  bundle, so every status change is attributable to evidence, not
                  to the directory or the script having changed.
* ``noseed``      same chain but ``init`` is given no ``--seed`` while the command
                  string contains ``--seed 123``: the pipeline-level firewall.

Nothing here manufactures a PASS: statuses are read out of the reports the CLI wrote.

    python scripts/run_v1_full_pipeline_check.py --work tmp/p5 --repeat 2 -o tmp/p5/golden.json

Exit code is 0 when every repeat produced the same status vectors.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "v1_full_project"
RULE_IDS = [f"ED{i:03d}" for i in range(1, 11)]


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(REPO / "src")
    return env


def _cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run ``python -m experiment_doctor <args>`` with the repo's own src on the path."""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "experiment_doctor", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(),
    )
    return proc


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=p5@p5", "-c", "user.name=p5", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def _runtime_evidence(report: dict[str, Any]) -> dict[str, str]:
    """Per-field status of the runtime_environment, read from the project dump.

    v0.1's frozen COVERAGE_FIELDS omits these subfields even though ED010 is driven
    by them, so the driver reads them straight off ``project.runs[].runtime_environment``.
    """
    out: dict[str, str] = {}
    for run in report.get("project", {}).get("runs", []):
        env = run.get("runtime_environment") or {}
        for name in ("python_version", "framework_versions", "os", "cuda_version", "hardware"):
            slot = env.get(name) or {}
            out[name] = slot.get("status", "MISSING")
    return out


def _audit(project: Path, out_dir: Path) -> dict[str, Any]:
    """Run ``audit`` and return {adapter, statuses, rule_ids, runs} from its report."""
    proc = _cli(["audit", str(project), "-o", str(out_dir)], REPO)
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    rules: list[dict[str, Any]] = report.get("rules", [])
    audit_payload: dict[str, Any] = report.get("audit", {})
    metrics = [sorted(entry.get("metric_names", [])) for entry in audit_payload.get("metrics", [])]
    return {
        "adapter": report["scan"]["adapter"],
        "runs": report["scan"]["runs"]["total"],
        "families": report["scan"]["families"]["total"],
        "metrics_of_record": metrics,
        "runtime_evidence": _runtime_evidence(report),
        "field_evidence": {
            name: {
                "unknown": counts["unknown"],
                "evidenced": counts["confirmed"] + counts["supported"],
                "inferred": counts["inferred"],
                "conflicting": counts["conflicting"],
            }
            for name, counts in report["scan"]["provenance_coverage"].items()
        },
        "statuses": {rule["rule_id"]: rule["status"] for rule in rules},
        "rule_ids": [rule["rule_id"] for rule in rules],
        "cli_exit": proc.returncode,
    }


def _status_vector(audit: dict[str, Any]) -> dict[str, str]:
    """Statuses for ED001-ED010, with ABSENT for a rule that emitted no result."""
    return {rule_id: audit["statuses"].get(rule_id, "ABSENT") for rule_id in RULE_IDS}


def _rmtree(root: Path) -> None:
    """Delete a tree, tolerating Windows' read-only loose git objects."""
    try:
        shutil.rmtree(root)
    except PermissionError:
        for path in [root, *root.rglob("*")]:
            os.chmod(path, 0o700)
        shutil.rmtree(root)


def _fresh(work: Path, name: str) -> Path:
    root = work / name
    if root.exists():
        _rmtree(root)
    shutil.copytree(FIXTURE, root)
    return root


def _run_plain(project: Path) -> int:
    """The traditional way: execute the script directly, with no wrapper at all."""
    return subprocess.run(
        [sys.executable, "train.py", "--seed", "123"],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(),
    ).returncode


def _verify(project: Path) -> tuple[dict[str, str], int]:
    proc = _cli(["verify", str(project)], REPO)
    bundle = project / "experiment-evidence" / "verify.json"
    report = json.loads(bundle.read_text(encoding="utf-8"))
    checks = {check["check_id"]: check["status"] for check in report["checks"]}
    return checks, proc.returncode


def _attempt(work: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}

    pre = _fresh(work, "pre")
    out["pre"] = _audit(pre, work / "reports" / "pre")

    trad = _fresh(work, "trad")
    out["traditional_exit"] = _run_plain(trad)
    out["traditional_results"] = sorted(
        p.relative_to(trad).as_posix() for p in (trad / "results").glob("*")
    )
    out["trad"] = _audit(trad, work / "reports" / "trad")

    cap = _fresh(work, "cap")
    out["cap_plain_exit"] = _run_plain(cap)
    _git(cap, "init", "-q")
    _git(cap, "add", ".")
    _git(cap, "commit", "-q", "-m", "init")
    out["cap_before"] = _audit(cap, work / "reports" / "cap_before")
    init = _cli(
        [
            "init",
            str(cap),
            "--seed",
            "123",
            "--config",
            "config.yaml",
            "--command",
            "python train.py --seed 123",
        ],
        REPO,
    )
    run = _cli(["run", "--path", str(cap), "--", sys.executable, "train.py", "--seed", "123"], REPO)
    checks, verify_exit = _verify(cap)
    out["cap"] = _audit(cap, work / "reports" / "cap")
    out["capture"] = {
        "init_exit": init.returncode,
        "run_exit": run.returncode,
        "verify_exit": verify_exit,
        "verify_checks": checks,
        "bundle_files": sorted(
            p.name for p in (cap / "experiment-evidence").glob("*") if p.is_file()
        ),
    }

    ns = _fresh(work, "noseed")
    _git(ns, "init", "-q")
    _git(ns, "add", ".")
    _git(ns, "commit", "-q", "-m", "init")
    _cli(["init", str(ns), "--config", "config.yaml"], REPO)
    _cli(["run", "--path", str(ns), "--", sys.executable, "train.py", "--seed", "123"], REPO)
    ns_checks, ns_verify_exit = _verify(ns)
    out["noseed"] = _audit(ns, work / "reports" / "noseed")
    out["noseed_verify"] = {"checks": ns_checks, "exit": ns_verify_exit}
    record = json.loads((ns / "experiment-evidence" / "experiment.run.json").read_text("utf-8"))
    lock = json.loads((ns / "experiment-evidence" / "experiment.lock.json").read_text("utf-8"))
    out["noseed_firewall"] = {
        "seed_in_command": "--seed" in json.dumps(record["execution"]["command"]),
        "lock_seed_status": lock["randomness"]["seed"]["status"],
        "metric_text_in_stdout": "accuracy=99.0"
        in (ns / "experiment-evidence" / "stdout.log").read_text("utf-8"),
        "metrics_csv_on_disk": (ns / "results" / "metrics.csv").is_file(),
        "status_vector": _status_vector(out["noseed"]),
    }
    return out


def _vectors(attempt: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        key: _status_vector(attempt[key]) for key in ("pre", "trad", "cap_before", "cap", "noseed")
    }


def _field_shift(attempt: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Per-field evidence counts before vs after capture: status counts only, no score."""
    before: dict[str, dict[str, int]] = attempt["cap_before"]["field_evidence"]
    after = attempt["cap"]["field_evidence"]
    shift: dict[str, dict[str, int]] = {}
    for name in sorted(set(before) | set(after)):
        row = {
            "unknown_before": before.get(name, {}).get("unknown", 0),
            "unknown_after": after.get(name, {}).get("unknown", 0),
            "evidenced_before": before.get(name, {}).get("evidenced", 0),
            "evidenced_after": after.get(name, {}).get("evidenced", 0),
        }
        shift[name] = row
    return shift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path("tmp/p5"))
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("-o", "--out", type=Path, default=Path("tmp/p5/golden.json"))
    args = parser.parse_args()

    args.work.mkdir(parents=True, exist_ok=True)
    attempts = [_attempt(args.work / f"attempt-{i}") for i in range(1, args.repeat + 1)]
    vectors = [_vectors(a) for a in attempts]
    stable = all(v == vectors[0] for v in vectors)

    summary = {
        "fixture": FIXTURE.relative_to(REPO).as_posix(),
        "repeats": args.repeat,
        "status_vectors_stable": stable,
        "rule_ids": RULE_IDS,
        "adapters": {
            "pre": attempts[0]["pre"]["adapter"],
            "traditional": attempts[0]["trad"]["adapter"],
            "captured": attempts[0]["cap"]["adapter"],
        },
        "capture": attempts[0]["capture"],
        "field_evidence_shift": _field_shift(attempts[0]),
        "noseed_verify": attempts[0]["noseed_verify"],
        "noseed_firewall": attempts[0]["noseed_firewall"],
        "attempts": attempts,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")

    for key, label in (
        ("pre", "pre (fixture only)"),
        ("trad", "traditional (results, no bundle, no git)"),
    ):
        node = attempts[0][key]
        print(f"\n{label}: adapter={node['adapter']} runs={node['runs']}")
        for rule_id in RULE_IDS:
            print(f"  {rule_id} {vectors[0][key][rule_id]}")
    print(f"\nverify: {json.dumps(attempts[0]['capture']['verify_checks'])}")
    before, after = vectors[0]["cap_before"], vectors[0]["cap"]
    print(
        "\nsame tree, before vs after capture: "
        f"adapter {attempts[0]['cap_before']['adapter']} -> {attempts[0]['cap']['adapter']}, "
        f"runs {attempts[0]['cap_before']['runs']} -> {attempts[0]['cap']['runs']}"
    )
    for rule_id in RULE_IDS:
        arrow = "same" if before[rule_id] == after[rule_id] else "->"
        print(f"  {rule_id} {before[rule_id]:>15} {arrow} {after[rule_id]}")
    shift = _field_shift(attempts[0])
    changed = {k: v for k, v in shift.items() if v["unknown_before"] != v["unknown_after"]}
    held = {k: v for k, v in shift.items() if v["unknown_before"] == v["unknown_after"]}
    print("\nfield evidence shift (unknown_before -> unknown_after):")
    print("  CHANGED (UNKNOWN -> evidenced):")
    for name, row in changed.items():
        print(f"    {name}: {row['unknown_before']} -> {row['unknown_after']}")
    print(f"  HELD UNKNOWN ({len(held)} fields): {', '.join(sorted(held))}")
    rt_before = attempts[0]["cap_before"]["runtime_evidence"]
    rt_after = attempts[0]["cap"]["runtime_evidence"]
    print("  runtime_environment (outside v0.1's frozen COVERAGE_FIELDS, drives ED010):")
    for name in sorted(set(rt_before) | set(rt_after)):
        print(f"    {name}: {rt_before.get(name, '-')} -> {rt_after.get(name, '-')}")
    print(f"\nnoseed firewall vector: {json.dumps(vectors[0]['noseed'], indent=1)}")
    print(
        "noseed verify (this tree did not pre-run, so artifacts are declared): "
        f"{json.dumps(attempts[0]['noseed_verify'])}"
    )
    print(
        "\nmetrics of record -- traditional: "
        f"{json.dumps(attempts[0]['trad']['metrics_of_record'])} captured: "
        f"{json.dumps(attempts[0]['cap']['metrics_of_record'])}"
    )
    print(f"\nstatus vectors identical across {args.repeat} repeats: {stable}")
    print(f"golden written: {args.out}")
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
