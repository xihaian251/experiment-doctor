"""JSON and Markdown rendering for v0.1 (no HTML)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from experiment_doctor.audit import AuditResult
from experiment_doctor.scanner import provenance_coverage_summary
from experiment_doctor.schema import (
    ComparisonStatus,
    ExperimentProject,
    FamilyKind,
    IdentityStatus,
    RunStatus,
)

#: Truncate per-field value dumps: a report must not embed every resolved config.
_MAX_LISTINGS = 25


def scan_summary(project: ExperimentProject) -> dict[str, Any]:
    """What ``scan`` reports: discovered scale plus provenance coverage, no verdicts."""
    kinds = Counter(family.kind.value for family in project.families)
    statuses = Counter(run.status.value for run in project.runs)
    artifact_types = Counter(ref.artifact_type.value for ref in project.artifacts)
    evaluation_runs = sum(
        len(project.runs_of(family.family_id))
        for family in project.families
        if family.kind is FamilyKind.EVALUATION
    )
    return {
        "project_id": project.project_id,
        "root": project.root,
        "adapter": project.adapter,
        "code_repository": _field(project.code_repository.value),
        "families": {
            "total": len(project.families),
            "by_kind": dict(kinds),
        },
        "runs": {
            "total": len(project.runs),
            "evaluation_runs": evaluation_runs,
            "by_status": dict(statuses),
            **provenance_coverage_summary(project.runs),
        },
        "artifacts": {
            "total": len(project.artifacts),
            "by_type": dict(artifact_types),
        },
        "aggregations": {
            "total": len(project.aggregations),
            "with_reported_value": sum(1 for record in project.aggregations if record.has_reported),
        },
        "provenance_coverage": coverage_to_dict(project, audit=None),
        "notes": project.notes,
    }


def report_payload(project: ExperimentProject, audit: AuditResult | None) -> dict[str, Any]:
    """Full ``report.json``: scan summary + audit results + project dump."""
    payload: dict[str, Any] = {"scan": scan_summary(project)}
    if audit is not None:
        payload["audit"] = audit.model_dump(mode="json")
        payload["scan"]["provenance_coverage"] = {
            name: counts.model_dump(mode="json") for name, counts in audit.coverage.items()
        }
    payload["project"] = project.model_dump(mode="json", exclude={"artifacts"})
    payload["project"]["artifact_count"] = len(project.artifacts)
    return payload


def coverage_to_dict(project: ExperimentProject, audit: AuditResult | None) -> dict[str, Any]:
    if audit is not None:
        return {name: counts.model_dump(mode="json") for name, counts in audit.coverage.items()}
    return provenance_coverage_summary(project.runs)


def render_markdown(project: ExperimentProject, audit: AuditResult | None) -> str:
    lines: list[str] = []
    summary = scan_summary(project)
    lines.append(f"# Experiment Doctor report - {project.project_id}")
    lines.append("")
    lines.append(f"- adapter: `{project.adapter}`")
    lines.append(f"- root: `{project.root}`")
    lines.append(f"- runs discovered: {summary['runs']['total']}")
    lines.append(f"- families discovered: {summary['families']['total']}")
    lines.append(f"- artifacts inventoried: {summary['artifacts']['total']}")
    lines.append(
        "- this tool is read-only and emits no verdict; every status below describes evidence, not validity"
    )

    lines.append("")
    lines.append("## Families")
    lines.append("")
    lines.append("| family | kind | runs | declared reps | identity | seed status | membership |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    identity = {item.family_id: item for item in (audit.identity if audit else [])}
    seeds = {item.family_id: item for item in (audit.seeds if audit else [])}
    membership = {item.family_id: item for item in (audit.membership if audit else [])}
    for family in project.families[:_MAX_LISTINGS]:
        runs = project.runs_of(family.family_id)
        ident = identity.get(family.family_id)
        seed = seeds.get(family.family_id)
        member = membership.get(family.family_id)
        lines.append(
            f"| `{family.family_id}` | {family.kind.value} | {len(runs)} | "
            f"{family.declared_repetitions.value} | {ident.status.value if ident else '-'} | "
            f"{seed.status if seed else '-'} | "
            f"{f'{member.included}+/{member.excluded}-' if member else '-'} |"
        )
    if len(project.families) > _MAX_LISTINGS:
        lines.append(
            f"| ... | | | | | | _{len(project.families) - _MAX_LISTINGS} more families in report.json_ |"
        )
    if audit:
        identity_counts = Counter(item.status.value for item in audit.identity)
        seed_counts = Counter(item.status for item in audit.seeds)
        lines.append("")
        lines.append(f"- identity statuses: {_format_counter(identity_counts)}")
        lines.append(f"- seed statuses: {_format_counter(seed_counts)}")

    lines.append("")
    lines.append("## Runs")
    lines.append("")
    lines.append(f"- total: {summary['runs']['total']}")
    lines.append(
        f"- by status: {_format_counter(Counter(run.status.value for run in project.runs))}"
    )
    lines.append(
        "- run_id is a tool-assigned identifier; it is not the tracking-system id, "
        "not a seed and not a repetition index"
    )
    absent = [run.run_id for run in project.runs if run.status is RunStatus.ABSENT_NO_ARTIFACT]
    if absent:
        lines.append(f"- slots without any history artifact: {len(absent)} (first: `{absent[0]}`)")

    lines.append("")
    lines.append("## Aggregations")
    lines.append("")
    if not project.aggregations:
        lines.append("_No aggregation records were recovered._")
    else:
        statuses = Counter(record.comparison_status.value for record in project.aggregations)
        lines.append(f"- records: {len(project.aggregations)} ({_format_counter(statuses)})")
        lines.append(
            "- recomputation is done from the member runs' final metric values, with the record's own "
            "``std_ddof`` and ``display_multiplier * std / sqrt(N)`` spread"
        )
        lines.append("")
        lines.append("| aggregation | metric | N | recomputed | reported | status |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        interesting = [
            record
            for record in project.aggregations
            if record.comparison_status is not ComparisonStatus.UNKNOWN or record.excluded_run_ids
        ]
        for record in (interesting or project.aggregations)[:_MAX_LISTINGS]:
            lines.append(
                f"| `{record.aggregation_id}` | {record.metric_name} | {record.n} | "
                f"{_num(record.recomputed_value)} +/- {_num(record.recomputed_spread)} | "
                f"{_num(record.reported_value)} +/- {_num(record.reported_spread)} | "
                f"{record.comparison_status.value} |"
            )
        if len(interesting or project.aggregations) > _MAX_LISTINGS:
            lines.append(
                f"| ... | | | | | _{len(project.aggregations) - _MAX_LISTINGS} more in report.json_ |"
            )

    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if audit is None:
        lines.append("_Audit was not run._")
    elif not audit.findings:
        lines.append("_No findings._")
    else:
        counts = Counter(finding.category.value for finding in audit.findings)
        severities = Counter(finding.severity.value for finding in audit.findings)
        lines.append(f"- total: {len(audit.findings)}")
        lines.append(f"- by category: {_format_counter(counts)}")
        lines.append(f"- by severity: {_format_counter(severities)}")
        lines.append("")
        for finding in audit.findings[:_MAX_LISTINGS]:
            lines.append(
                f"- **{finding.severity.value} / {finding.category.value}** - {finding.title} "
                f"(`{finding.entity_id}`)"
            )
            for item in finding.evidence[:3]:
                lines.append(f"    - {item}")
        if len(audit.findings) > _MAX_LISTINGS:
            lines.append(f"- _{len(audit.findings) - _MAX_LISTINGS} more findings in report.json_")

    lines.append("")
    lines.append("## Provenance Coverage")
    lines.append("")
    lines.append("Field-level evidence counts.  There is deliberately no composite trust score.")
    lines.append("")
    lines.append("| field | runs | CONFIRMED | SUPPORTED | INFERRED | UNKNOWN | CONFLICTING |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    if audit is not None:
        for name, evidence in sorted(audit.coverage.items()):
            lines.append(
                f"| {name} | {evidence.total} | {evidence.confirmed} | {evidence.supported} | "
                f"{evidence.inferred} | {evidence.unknown} | {evidence.conflicting} |"
            )
    else:
        lines.append("")
        lines.append("_Run `experiment-doctor audit` for per-field evidence grades._")
        for name, value in sorted(summary["provenance_coverage"].items()):
            if isinstance(value, int):
                lines.append(f"- {name}: {value}")
    if project.notes:
        lines.append("")
        lines.append("## Discovery Notes")
        lines.append("")
        for note in project.notes:
            lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def write_report(
    output_dir: Path, project: ExperimentProject, audit: AuditResult | None, markdown: str
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    import json

    json_path.write_text(
        json.dumps(report_payload(project, audit), indent=1, ensure_ascii=False), encoding="utf-8"
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path


def _field(value: Any) -> Any:
    return value


def _num(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4g}"


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "-"
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))


__all__ = [
    "IdentityStatus",
    "render_markdown",
    "report_payload",
    "scan_summary",
    "write_report",
]
