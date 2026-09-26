#!/usr/bin/env python3
"""Cross-project acceptance for the v0.1 formal rule set: one run, both projects.

Read-only, and no path is baked in:

    python scripts/run_rule_acceptance.py \
        --gmmvi-repo F:/MLResearch/experiment-doctor/phase0-gmmvi/repo \
        --gmmvi-data F:/MLResearch/experiment-doctor/phase0-gmmvi/extracted/evaluations/results \
        --gmmvi-reported-table examples/gmmvi_reported_table.json \
        --torchssl-repo F:/MLResearch/experiment-doctor/acceptance1-torchssl/repo \
        --torchssl-logs F:/MLResearch/experiment-doctor/acceptance1-torchssl/downloads/logs \
        --torchssl-reported-table examples/torchssl_reported_table.json \
        -o rule_acceptance.json

What is checked here is *rule behaviour on real artifacts*, and only that.  The
structural facts about each project (run discovery, per-run metric values, the
arithmetic recomputation) already belong to ``run_gmmvi_acceptance.py`` (21 checks)
and ``run_torchssl_acceptance.py`` (46 checks); nothing below repeats them.

Expectations are stated as semantics - which statuses a rule may and may not produce
for a project whose artifacts look like this - rather than as fixed counts, because
the count depends on entity granularity and the subset of cells a project happens to
publish.  A published cell means one whose ``reported_value`` the project itself
supplied through the reported-table input.

Exit code is 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from experiment_doctor.adapters.gmmvi import GMMVIAdapter  # noqa: E402
from experiment_doctor.adapters.torchssl import TorchSSLAdapter  # noqa: E402
from experiment_doctor.audit import audit_project  # noqa: E402
from experiment_doctor.rules import RULES, RuleResult, RuleStatus, run_rules  # noqa: E402
from experiment_doctor.scanner import scan_project  # noqa: E402
from experiment_doctor.schema import (  # noqa: E402
    ExperimentProject,
    FamilyKind,
    SelectionPolicy,
    Severity,
    SpreadSemantics,
)

#: The canonical wording of an absent historical revision (baseline section 3).
MISSING_CODE_SUMMARY = "historical code identity cannot be established from available artifacts"

#: Tokens that would make a rule project-specific (baseline section 29).
HARDCODE_TOKENS = (
    "fixmatch",
    "flexmatch",
    "gmmvi",
    "sepyfux",
    "samtrux",
    "cifar10",
    "torchssl",
    "stl10",
    "svhn",
    "imagenet",
)


def _check(
    name: str, passed: bool, expected: Any, observed: Any, detail: str = ""
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "expected": expected,
        "observed": observed,
        "detail": detail,
    }


class RulesRun:
    """One project's rule results, indexed once so every check reads the same objects."""

    def __init__(self, project: ExperimentProject) -> None:
        self.project = project
        self.audit = audit_project(project)
        self.results = run_rules(project, self.audit)
        self.by_rule: dict[str, list[RuleResult]] = {}
        for result in self.results:
            self.by_rule.setdefault(result.rule_id, []).append(result)
        self.published = {
            record.aggregation_id
            for record in project.aggregations
            if record.reported_value is not None
        }
        self.records = {record.aggregation_id: record for record in project.aggregations}

    def of(self, rule_id: str, published_only: bool = False) -> list[RuleResult]:
        results = self.by_rule.get(rule_id, [])
        if published_only:
            results = [item for item in results if item.entity_id in self.published]
        return results

    def statuses(self, rule_id: str, published_only: bool = False) -> list[str]:
        return sorted({item.status.value for item in self.of(rule_id, published_only)})

    def counts(self, rule_id: str, published_only: bool = False) -> dict[str, int]:
        rows = self.of(rule_id, published_only)
        return dict(Counter(item.status.value for item in rows))

    def measurement(self, rule_id: str, key: str, published_only: bool = False) -> list[Any]:
        return [item.measurements.get(key) for item in self.of(rule_id, published_only)]

    def n_fail(self, rule_id: str) -> int:
        return sum(1 for item in self.by_rule.get(rule_id, []) if item.status is RuleStatus.FAIL)


def _value(field: Any) -> str:
    return str(getattr(field.value, "value", field.value))


def _semantics(run: RulesRun, key: str) -> list[str]:
    """The distinct attested values of one aggregation field over the published cells."""
    return sorted(
        {
            _value(getattr(run.records[entity_id], key))
            for entity_id in run.published
            if entity_id in run.records
        }
    )


# ----------------------------------------------------------- GMMVI expectations


def gmmvi_checks(run: RulesRun) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    seeds = run.of("ED002")
    unexplained = [
        item.entity_id
        for item in seeds
        if item.status is RuleStatus.NOT_APPLICABLE
        and item.measurements.get("kind") != FamilyKind.HYPERPARAMETER_SEARCH.value
        and item.measurements.get("n_runs") != 0
    ]
    gap = [item for item in seeds if item.status is RuleStatus.INCONCLUSIVE]
    checks.append(
        _check(
            "gmmvi_ed002_unknown_seed_stays_inconclusive",
            run.n_fail("ED002") == 0
            and not unexplained
            and len(gap) > 0
            and all(item.measurements.get("runs_with_seed_evidence") == 0 for item in gap)
            and sum(1 for item in seeds if item.status is RuleStatus.PASS) == 0,
            "no FAIL and no PASS; every family that is not a hyperparameter search is "
            "INCONCLUSIVE with zero seed evidence",
            {
                "counts": run.counts("ED002"),
                "unexplained_not_applicable": unexplained,
                "families_with_zero_seed_evidence": sum(
                    1 for item in gap if item.measurements.get("runs_with_seed_evidence") == 0
                ),
            },
            detail="no run artifact records a seed, so the tool reports that seed provenance "
            "cannot be established; it does not call the repetitions duplicated, and it does "
            "not abstain on a family that is a genuine set of repetitions",
        )
    )
    excluded_seen = [
        int(item.measurements.get("family_excluded_runs") or 0) for item in run.of("ED006")
    ]
    checks.append(
        _check(
            "gmmvi_ed006_exclusions_do_not_fail_membership",
            run.n_fail("ED006") == 0 and max(excluded_seen) > 0,
            "FAIL: 0 with excluded runs present",
            {"statuses": run.statuses("ED006"), "max_family_excluded": max(excluded_seen)},
            detail="dropping runs is the project's choice; traceability of the kept set is the "
            "question, and the published cells answer it",
        )
    )
    checks.append(
        _check(
            "gmmvi_ed007_published_cells_recompute",
            run.statuses("ED007", published_only=True) == [RuleStatus.PASS.value],
            ["PASS"],
            {
                "published": run.counts("ED007", published_only=True),
                "reconstructions": run.counts("ED007"),
            },
            detail="the reconstructions this tool built carry no published number, so they are "
            "INCONCLUSIVE rather than agreements",
        )
    )
    checks.append(
        _check(
            "gmmvi_ed008_spread_formula_recovered_without_a_fail",
            run.n_fail("ED008") == 0
            and _semantics(run, "implemented_spread")
            == [SpreadSemantics.SCALED_STANDARD_ERROR.value]
            and run.statuses("ED008", published_only=True) == [RuleStatus.PASS.value],
            ["PASS", "no FAIL", SpreadSemantics.SCALED_STANDARD_ERROR.value],
            {
                "statuses": run.statuses("ED008", published_only=True),
                "implemented": _semantics(run, "implemented_spread"),
                "documented": _semantics(run, "documented_spread"),
            },
            detail="the project's own aggregation line divides by sqrt(N) after multiplying by 3, "
            "and its prose makes no contrary statement, so ED008 PASSes on the code alone",
        )
    )
    checks.append(
        _check(
            "gmmvi_ed009_termination_is_not_invented",
            run.statuses("ED009") == [RuleStatus.INCONCLUSIVE.value],
            ["INCONCLUSIVE"],
            {"statuses": run.statuses("ED009"), "results": len(run.of("ED009"))},
            detail="a history that stops is not a record of why it stopped; the rule emits a real "
            "result per run and leaves the cause unasserted",
        )
    )
    checks.append(
        _check(
            "gmmvi_ed003_no_historical_commit",
            run.statuses("ED003") == [RuleStatus.INCONCLUSIVE.value]
            and {item.summary for item in run.of("ED003")} == {MISSING_CODE_SUMMARY},
            ["INCONCLUSIVE", MISSING_CODE_SUMMARY],
            {
                "statuses": run.statuses("ED003"),
                "summaries": sorted({i.summary for i in run.of("ED003")}),
            },
            detail="the present checkout is never substituted for the code that ran",
        )
    )
    checks.append(
        _check(
            "gmmvi_ed010_environment_declared_not_recorded",
            run.statuses("ED010") == [RuleStatus.INCONCLUSIVE.value],
            ["INCONCLUSIVE"],
            run.statuses("ED010"),
            detail="the repository ships a dependency declaration; no run recorded what it loaded",
        )
    )
    return checks


# ---------------------------------------------------------- TorchSSL expectations


def torchssl_checks(run: RulesRun) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.append(
        _check(
            "torchssl_ed002_recorded_seeds_pass",
            run.statuses("ED002") == [RuleStatus.PASS.value]
            and all(
                item.measurements["runs_with_seed_evidence"] == item.measurements["n_runs"]
                for item in run.of("ED002")
            ),
            ["PASS"],
            {
                "statuses": run.statuses("ED002"),
                "evidence": [
                    [item.measurements["runs_with_seed_evidence"], item.measurements["n_runs"]]
                    for item in run.of("ED002")
                ],
            },
            detail="this project writes its seed into the artifact the run produced, which is the "
            "evidence grade ED002 requires",
        )
    )
    checks.append(
        _check(
            "torchssl_ed005_best_selection_documented_and_honoured",
            run.statuses("ED005", published_only=True) == [RuleStatus.PASS.value]
            and _semantics(run, "implemented_selection") == [SelectionPolicy.BEST.value]
            and _semantics(run, "documented_selection") == [SelectionPolicy.BEST.value],
            ["PASS", SelectionPolicy.BEST.value, SelectionPolicy.BEST.value],
            {
                "statuses": run.statuses("ED005", published_only=True),
                "implemented": _semantics(run, "implemented_selection"),
                "documented": _semantics(run, "documented_selection"),
            },
            detail="the aggregation consumes the log's running best and the README says best; "
            "the @last reconstruction carries no published number and so claims nothing",
        )
    )
    checks.append(
        _check(
            "torchssl_ed007_published_cells_recompute",
            run.statuses("ED007", published_only=True) == [RuleStatus.PASS.value],
            ["PASS"],
            {"published": run.counts("ED007", published_only=True), "all": run.counts("ED007")},
            detail="the arithmetic is already fixed by the 46-check acceptance; here only the "
            "rule's status for those cells is asserted",
        )
    )
    failed = run.of("ED008", published_only=True)
    checks.append(
        _check(
            "torchssl_ed008_finds_the_standard_error_claim",
            run.statuses("ED008", published_only=True) == [RuleStatus.FAIL.value]
            and all(item.severity is Severity.HIGH for item in failed)
            and _semantics(run, "documented_spread") == [SpreadSemantics.STANDARD_ERROR.value]
            and _semantics(run, "implemented_spread") == [SpreadSemantics.STANDARD_DEVIATION.value],
            [
                "FAIL",
                "HIGH",
                SpreadSemantics.STANDARD_ERROR.value,
                SpreadSemantics.STANDARD_DEVIATION.value,
            ],
            {
                "statuses": run.statuses("ED008", published_only=True),
                "documented": _semantics(run, "documented_spread"),
                "implemented": _semantics(run, "implemented_spread"),
                "summaries": sorted({item.summary for item in failed}),
            },
            detail="found from the project's own files: the README calls the +/- a standard error, "
            "the aggregation prints np.std without dividing by sqrt(N).  Every published number "
            "still recomputes, so this FAIL is not an arithmetic disagreement",
        )
    )
    causes = run.measurement("ED009", "cause")
    checks.append(
        _check(
            "torchssl_ed009_terminal_marker_is_read",
            run.statuses("ED009") == [RuleStatus.PASS.value] and all(causes),
            ["PASS", "a named cause"],
            {"statuses": run.statuses("ED009"), "causes": sorted({str(c) for c in causes})},
            detail="the log's own completion marker states why the process ended",
        )
    )
    checks.append(
        _check(
            "torchssl_ed004_runtime_configuration_is_run_local",
            run.statuses("ED004") == [RuleStatus.PASS.value],
            ["PASS"],
            run.statuses("ED004"),
            detail="each run dumps its effective options into the log it writes",
        )
    )
    checks.append(
        _check(
            "torchssl_ed010_environment_is_not_recorded_by_the_run",
            run.statuses("ED010") == [RuleStatus.INCONCLUSIVE.value],
            ["INCONCLUSIVE"],
            run.statuses("ED010"),
            detail="a conda environment named in documentation is not what the run recorded",
        )
    )
    checks.append(
        _check(
            "torchssl_ed003_no_historical_commit",
            run.statuses("ED003") == [RuleStatus.INCONCLUSIVE.value]
            and {item.summary for item in run.of("ED003")} == {MISSING_CODE_SUMMARY},
            ["INCONCLUSIVE", MISSING_CODE_SUMMARY],
            {
                "statuses": run.statuses("ED003"),
                "summaries": sorted({i.summary for i in run.of("ED003")}),
            },
        )
    )
    return checks


# --------------------------------------------------------------- shared behaviour


def cross_project_checks(
    gmmvi: RulesRun, torchssl: RulesRun, rules_dir: Path
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    gmmvi_rules = {rule_id: len(items) for rule_id, items in gmmvi.by_rule.items()}
    torchssl_rules = {rule_id: len(items) for rule_id, items in torchssl.by_rule.items()}
    checks.append(
        _check(
            "same_ten_rules_on_both_projects",
            list(gmmvi.by_rule) == [rule.rule_id for rule in RULES]
            and list(torchssl.by_rule) == [rule.rule_id for rule in RULES],
            [rule.rule_id for rule in RULES],
            {"gmmvi": list(gmmvi.by_rule), "torchssl": list(torchssl.by_rule)},
            detail=f"no rule was skipped, specialised or added: {len(RULES)} rules produced "
            f"{sum(gmmvi_rules.values())} results on GMMVI and {sum(torchssl_rules.values())} on "
            "TorchSSL",
        )
    )
    entities = {rule.rule_id: rule.entity_type for rule in RULES}
    mismatched = {
        rule_id: sorted({item.entity_type for item in run.by_rule.get(rule_id, [])})
        for run in (gmmvi, torchssl)
        for rule_id in run.by_rule
        if {item.entity_type for item in run.by_rule[rule_id]} != {entities[rule_id]}
    }
    checks.append(
        _check(
            "entity_granularity_holds",
            not mismatched,
            "each rule's declared entity type only",
            mismatched,
            detail="family rules once per family, run rules once per run, aggregation rules once "
            "per published or reconstructed cell",
        )
    )
    offending: dict[str, list[str]] = {}
    for path in sorted(rules_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        hits = [token for token in HARDCODE_TOKENS if token in text]
        if hits:
            offending[path.name] = hits
    checks.append(
        _check(
            "rules_contain_no_project_hardcode",
            not offending,
            [],
            offending,
            detail=f"searched {len(list(rules_dir.glob('*.py')))} modules under "
            f"{rules_dir.as_posix()} for the project vocabulary of both accepted projects",
        )
    )
    uncertain_are_medium = [
        f"{item.rule_id}/{item.entity_id}: {item.severity.value}"
        for run in (gmmvi, torchssl)
        for item in run.results
        if item.status in (RuleStatus.INCONCLUSIVE, RuleStatus.NOT_RUN)
        and item.severity is not Severity.MEDIUM
    ]
    checks.append(
        _check(
            "inconclusive_is_never_calibrated_as_high",
            not uncertain_are_medium,
            "MEDIUM for every uncertain result",
            uncertain_are_medium[:10],
            detail="an evidence gap says what cannot be established, so it cannot outrank a "
            "contradiction of a published claim",
        )
    )
    return checks


def _summary(run: RulesRun) -> dict[str, Any]:
    return {
        "project_id": run.project.project_id,
        "adapter": run.project.adapter,
        "runs": len(run.project.runs),
        "families": len(run.project.families),
        "aggregations": len(run.project.aggregations),
        "published_aggregations": len(run.published),
        "results": len(run.results),
        "per_rule": {rule_id: run.counts(rule_id) for rule_id in sorted(run.by_rule)},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gmmvi-repo", type=Path, required=True, help="read-only gmmvi checkout")
    parser.add_argument(
        "--gmmvi-data", type=Path, required=True, help="directory holding the *_EVAL result folders"
    )
    parser.add_argument("--gmmvi-reported-table", type=Path, default=None)
    parser.add_argument(
        "--torchssl-repo", type=Path, required=True, help="read-only TorchSSL clone"
    )
    parser.add_argument(
        "--torchssl-logs", type=Path, required=True, help="directory holding <run>/log.txt"
    )
    parser.add_argument("--torchssl-reported-table", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, default=Path("rule_acceptance.json"))
    args = parser.parse_args(list(argv) if argv is not None else None)

    for label, path in (
        ("--gmmvi-repo", args.gmmvi_repo),
        ("--gmmvi-data", args.gmmvi_data),
        ("--torchssl-repo", args.torchssl_repo),
        ("--torchssl-logs", args.torchssl_logs),
    ):
        if not path.is_dir():
            parser.error(f"{label} must be an existing directory: {path}")
    for label, path in (
        ("--torchssl-reported-table", args.torchssl_reported_table),
        ("--gmmvi-reported-table", args.gmmvi_reported_table),
    ):
        if path is not None and not path.is_file():
            parser.error(f"{label} must be an existing file: {path}")

    gmmvi_repo = args.gmmvi_repo.resolve()
    gmmvi_data = args.gmmvi_data.resolve()
    try:
        gmmvi_root = Path(os.path.commonpath([str(gmmvi_repo), str(gmmvi_data)]))
    except ValueError:  # different drives on Windows: keep the repo as the scan root
        gmmvi_root = gmmvi_repo
    gmmvi = RulesRun(
        scan_project(
            gmmvi_root,
            adapter=GMMVIAdapter(
                gmmvi_root,
                repo_root=gmmvi_repo,
                results_root=gmmvi_data,
                reported_table=args.gmmvi_reported_table,
            ),
        )
    )
    torchssl_logs = args.torchssl_logs.resolve()
    torchssl_root = torchssl_logs.parent if torchssl_logs.parent != torchssl_logs else torchssl_logs
    torchssl = RulesRun(
        scan_project(
            torchssl_root,
            adapter=TorchSSLAdapter(
                torchssl_root,
                repo_root=args.torchssl_repo.resolve(),
                logs_root=torchssl_logs,
                reported_table=args.torchssl_reported_table,
            ),
        )
    )

    checks = (
        gmmvi_checks(gmmvi)
        + torchssl_checks(torchssl)
        + cross_project_checks(gmmvi, torchssl, SRC_ROOT / "experiment_doctor" / "rules")
    )
    passed = sum(1 for check in checks if check["passed"])
    payload = {
        "inputs": {
            "gmmvi_root": str(gmmvi_root),
            "gmmvi_repo": str(gmmvi_repo),
            "gmmvi_data": str(gmmvi_data),
            "gmmvi_reported_table": str(args.gmmvi_reported_table or ""),
            "torchssl_root": str(torchssl_root),
            "torchssl_repo": str(args.torchssl_repo.resolve()),
            "torchssl_logs": str(torchssl_logs),
            "torchssl_reported_table": str(args.torchssl_reported_table),
        },
        "oracle": "the v0.1 rule contract applied to two unrelated real projects (expectations only)",
        "passed": passed,
        "failed": len(checks) - passed,
        "projects": {"gmmvi": _summary(gmmvi), "torchssl": _summary(torchssl)},
        "checks": checks,
    }
    if args.output.parent != Path(""):
        args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    for check in checks:
        print(f"[{'PASS' if check['passed'] else 'FAIL'}] {check['name']}")
        if not check["passed"]:
            print(f"    expected: {check['expected']}\n    observed: {check['observed']}")
    print(f"\n{passed}/{len(checks)} checks passed -> {args.output}")
    return 0 if passed == len(checks) else 1


def _scan(root: Path, adapter: Any) -> ExperimentProject:
    from experiment_doctor.scanner import scan_project

    return scan_project(root, adapter=adapter)


if __name__ == "__main__":
    raise SystemExit(main())
