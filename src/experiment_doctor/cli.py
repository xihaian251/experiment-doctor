"""Typer CLI: ``experiment-doctor --help | scan | audit | rules | adapters``.

v0.1 ships exactly these four commands.  ``rules`` only reads the registry.
There is no serve/watch/fix/sync/upload: the tool is read-only and does not
mutate a project.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from experiment_doctor.adapters import available_adapters, build
from experiment_doctor.audit import audit_project
from experiment_doctor.report import render_markdown, scan_summary, write_report
from experiment_doctor.rules import RULES, rule_catalog, run_rules
from experiment_doctor.scanner import ExperimentAdapter, scan_project

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "Experiment Doctor v0.1: audit the provenance and aggregation membership of ML "
        "experiment artifacts (read-only)."
    ),
)


@app.command()
def scan(
    path: Path = typer.Argument(..., exists=True, help="Project directory to scan."),
    json_out: Optional[Path] = typer.Option(
        None, "--json", help="Write the scan summary to this JSON file."
    ),
    adapter: Optional[str] = typer.Option(
        None, "--adapter", help="Force a specific adapter instead of auto-selection."
    ),
) -> None:
    """Discover families, run candidates, artifact sources and provenance coverage."""
    instance = build(adapter, path) if adapter else None
    project = scan_project(path, adapter=instance)
    summary = scan_summary(project)
    typer.echo(json.dumps(summary, indent=1, ensure_ascii=False))
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
        typer.echo(f"scan summary written to {json_out}", err=True)


@app.command()
def audit(
    path: Path = typer.Argument(..., exists=True, help="Project directory to audit."),
    output: Path = typer.Option(
        Path("experiment-doctor-report"), "-o", help="Directory for report.json and report.md."
    ),
    adapter: Optional[str] = typer.Option(
        None, "--adapter", help="Force a specific adapter instead of auto-selection."
    ),
    reported_table: Optional[Path] = typer.Option(
        None,
        "--reported-table",
        help=(
            "Optional JSON of published aggregation cells (see "
            "docs/reported_summary_schema.md).  Without it, reported-vs-recomputed "
            "comparison stays UNKNOWN."
        ),
    ),
) -> None:
    """Run the v0.1 checks and formal rules, then write report.json plus report.md."""
    if reported_table is not None and adapter is None:
        raise typer.BadParameter("--reported-table requires --adapter")
    instance: ExperimentAdapter | None = None
    if adapter is not None:
        built = build(adapter, path)
        if reported_table is not None:
            if not hasattr(built, "reported_table"):
                raise typer.BadParameter(f"adapter '{adapter}' takes no --reported-table")
            built.reported_table = Path(reported_table)
        instance = built
    project = scan_project(path, adapter=instance)
    result = audit_project(project)
    rules = run_rules(project, result)
    json_path, markdown_path = write_report(
        output, project, result, render_markdown(project, result, rules), rules
    )
    counts = result.counts
    rule_fail = sum(1 for r in rules if r.status.value == "FAIL")
    rule_inconclusive = sum(1 for r in rules if r.status.value == "INCONCLUSIVE")
    typer.echo(
        f"adapter={project.adapter} families={counts['families']} runs={counts['runs']} "
        f"aggregations={counts['aggregations']} "
        f"match={counts['matched']} mismatch={counts['mismatched']} "
        f"unknown={counts['comparison_unknown']} findings={counts['findings']} "
        f"rules={len(rules)} rule_fail={rule_fail} rule_inconclusive={rule_inconclusive}"
    )
    typer.echo(f"report written: {json_path}")
    typer.echo(f"report written: {markdown_path}")


@app.command()
def rules(
    as_json: bool = typer.Option(
        False, "--json", help="Print the registry as JSON instead of aligned text."
    ),
) -> None:
    """List the formal v0.1 rules and the entity each one is evaluated against."""
    if as_json:
        typer.echo(json.dumps(rule_catalog(), indent=2, ensure_ascii=False))
        return
    for rule in RULES:
        typer.echo(f"{rule.rule_id}  [{rule.entity_type}]  {rule.title}")
        typer.echo(f"  {rule.purpose}")


@app.command()
def adapters() -> None:
    """List the adapters v0.1 ships and what each one understands."""
    for spec in available_adapters():
        typer.echo(f"{spec.name}\n  {spec.description}")
        if spec.options:
            typer.echo(f"  options: {', '.join(spec.options)}")


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
