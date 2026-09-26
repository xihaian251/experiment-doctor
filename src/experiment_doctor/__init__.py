"""Experiment Doctor v0.1 - read-only provenance and aggregation audit for ML experiments.

Public API::

    from experiment_doctor import scan_project, audit_project, write_report

The tool never writes into the audited project.
"""

from __future__ import annotations

from experiment_doctor.adapters import available_adapters
from experiment_doctor.adapters import build as build_adapter
from experiment_doctor.audit import AuditResult, audit_project
from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.report import render_markdown, report_payload, scan_summary, write_report
from experiment_doctor.scanner import ExperimentAdapter, scan_project
from experiment_doctor.schema import (
    AggregationRecord,
    ArtifactRef,
    ExperimentFamily,
    ExperimentProject,
    ExperimentRun,
    Finding,
    MetricRecord,
)

__version__ = "0.1.dev0"

__all__ = [
    "AggregationRecord",
    "ArtifactRef",
    "AuditResult",
    "ExperimentAdapter",
    "ExperimentFamily",
    "ExperimentProject",
    "ExperimentRun",
    "Finding",
    "MetricRecord",
    "ProvenanceField",
    "ProvenanceStatus",
    "SourceRef",
    "__version__",
    "audit_project",
    "available_adapters",
    "build_adapter",
    "render_markdown",
    "report_payload",
    "scan_project",
    "scan_summary",
    "write_report",
]
