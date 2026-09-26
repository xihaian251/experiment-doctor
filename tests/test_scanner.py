"""The generic fallback: inventory and gaps, and nothing it cannot evidence."""

from __future__ import annotations

from pathlib import Path

from experiment_doctor.audit import audit_project
from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.scanner import classify, scan_project
from experiment_doctor.schema import ArtifactType, FamilyKind, FindingCategory, RunStatus

CSV = ",_step,num_samples,_runtime,-elbo\n0,1000,3000,10.0,1.0\n0,2000,6000,20.0,0.5\n"


def _write_tree(root: Path) -> None:
    (root / "exp" / "results" / "method_a").mkdir(parents=True)
    (root / "exp" / "results" / "method_b").mkdir(parents=True)
    (root / "exp" / "results" / "method_a" / "run_0.csv").write_text(CSV, encoding="utf-8")
    (root / "exp" / "results" / "method_a" / "run_1.csv.bad").write_text(CSV, encoding="utf-8")
    (root / "exp" / "results" / "method_a" / "run_0_config.yml").write_text(
        "lr: 0.1\n", encoding="utf-8"
    )
    (root / "exp" / "results" / "method_b" / "metrics.csv").write_text(CSV, encoding="utf-8")
    (root / "exp" / "run.sh").write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
    (root / "exp" / "requirements.txt").write_text("numpy==1.24.0\n", encoding="utf-8")


def test_generic_scanner(tmp_path: Path) -> None:
    _write_tree(tmp_path)
    project = scan_project(tmp_path)

    assert project.adapter == "generic"
    # The generic scanner cannot evidence a repository, a commit, or a run's identity.
    assert project.code_repository.status is ProvenanceStatus.UNKNOWN
    assert project.code_repository.value is None
    families = {family.family_id: family for family in project.families}
    assert set(families) == {"exp/results/method_a", "exp/results/method_b"}
    assert all(family.kind is FamilyKind.UNKNOWN for family in families.values())
    assert all(
        family.membership_rule.status is ProvenanceStatus.UNKNOWN for family in families.values()
    )

    runs = {run.run_id: run for run in project.runs}
    assert len(runs) == 3
    for run in runs.values():
        assert run.metrics == [], "an unlabelled column is not promoted to a metric of record"
        assert run.seed.status is ProvenanceStatus.UNKNOWN
        assert run.included_in_aggregation.value is None
        assert run.status is RunStatus.UNKNOWN

    # Config-to-run binding is only a stem match, and is graded as such.
    bound = runs["exp/results/method_a#run_0"]
    assert bound.config_source.status is ProvenanceStatus.INFERRED
    assert bound.config_source.value == "exp/results/method_a/run_0_config.yml"
    assert runs["exp/results/method_a#run_1.csv"].config_source.status is ProvenanceStatus.UNKNOWN

    types = {artifact.path: artifact.artifact_type for artifact in project.artifacts}
    assert types["exp/results/method_a/run_1.csv.bad"] is ArtifactType.METRIC
    assert types["exp/requirements.txt"] is ArtifactType.ENVIRONMENT
    assert types["exp/run.sh"] is ArtifactType.SCRIPT
    assert types["exp/results/method_a/run_0_config.yml"] is ArtifactType.CONFIG

    result = audit_project(project)
    assert result.coverage["seed"].unknown == len(project.runs)
    assert result.coverage["code_commit"].unknown == len(project.runs)
    assert any(finding.category is FindingCategory.PROVENANCE_GAP for finding in result.findings)
    assert all(
        finding.category is not FindingCategory.AGGREGATION_MISMATCH for finding in result.findings
    )
    assert project.aggregations == []


def test_classify_does_not_invent_semantics() -> None:
    """Classification is an extension->kind map; it never promotes a column to a metric."""
    assert classify(Path("a/run_0.csv")) is ArtifactType.METRIC
    assert classify(Path("a/run_0.csv.bad")) is ArtifactType.METRIC
    assert classify(Path("a/model.pt")) is ArtifactType.CHECKPOINT
    assert classify(Path("a/job.sbatch")) is ArtifactType.ENVIRONMENT
    assert classify(Path("a/notes.txt")) is ArtifactType.LOG
    assert classify(Path("a/plot.png")) is ArtifactType.UNKNOWN
