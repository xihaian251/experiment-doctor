"""ED010 - can the software and hardware a historical run executed on be established?

A dependency file in the repository states what the author intended to install.  It
cannot show what was installed on the machine that ran the job months ago, so a
declaration never produces PASS here; only a value read out of the run's own artifact
does.  The schema refinement keeps that standard and makes the two sides explicit:
runtime evidence lives on ``ExperimentRun.runtime_environment`` (or the legacy scalar
when a run-local artifact cites it), declared evidence lives in the project's
dependency declarations, and the rule reports how the two stand together without ever
promoting one into the other.
"""

from __future__ import annotations

from typing import Any, ClassVar

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus
from experiment_doctor.rules.base import Rule, RuleContext, RuleResult, RuleStatus, attached_to_run
from experiment_doctor.schema import (
    ArtifactRole,
    ArtifactType,
    DeclaredEnvironment,
    EnvironmentRelationship,
    ExperimentProject,
    RuntimeEnvironment,
    Severity,
    relate_environment_evidence,
)

_RECORDED = (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED)


class RuntimeEnvironmentProvenance(Rule):
    rule_id: ClassVar[str] = "ED010"
    title: ClassVar[str] = "Runtime Environment Provenance"
    purpose: ClassVar[str] = "Is the environment the run executed in recorded by the run?"
    entity_type: ClassVar[str] = "run"
    fail_severity: ClassVar[Severity] = Severity.HIGH
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM

    def evaluate(self, context: RuleContext) -> list[RuleResult]:
        declarations = _declaration_paths(context.project)
        declared = _primary_declaration(context.project)
        return [self._one(run, declarations, declared) for run in context.project.runs]

    def _one(
        self,
        run: Any,
        declarations: list[str],
        declared: DeclaredEnvironment | None,
    ) -> RuleResult:
        environment: ProvenanceField[str] = run.environment
        source = environment.source.describe() if environment.source else "-"
        attached = attached_to_run(run, environment.source)
        scalar_recorded = environment.status in _RECORDED and attached is not None
        scalar_cited_declaration = environment.status in _RECORDED and attached is None
        slot = _run_recorded_runtime(run)
        slot_cited_declaration = _declaration_cited_runtime(run)
        runtime_recorded = scalar_recorded or slot is not None
        conflict = _version_conflict(slot, declared)
        any_evidence = (
            runtime_recorded
            or scalar_cited_declaration
            or slot_cited_declaration
            or bool(declarations)
            or declared is not None
            or environment.status is ProvenanceStatus.CONFLICTING
        )
        relationship = _relationship(
            scalar_recorded=scalar_recorded,
            slot=slot,
            declared=declared,
            runtime_recorded=runtime_recorded,
            any_evidence=any_evidence,
        )
        measurements = {
            "environment_status": environment.status.value,
            "source_attached_to_run": attached is not None,
            "declared_environment_files": len(declarations),
            "compute_budget_status": run.compute_budget.status.value,
            "environment_relationship": relationship.value,
            "runtime_evidence_recorded": runtime_recorded,
        }
        declaration_evidence = (
            [f"repository-level declarations present: {', '.join(declarations[:5])}"]
            if declarations
            else ["no dependency declaration was found anywhere in the repository"]
        )

        if environment.status is ProvenanceStatus.CONFLICTING or _slot_is_conflicting(run):
            return self.result(
                run.run_id,
                RuleStatus.FAIL,
                "the artifacts state mutually exclusive runtime environments for this run",
                evidence=[f"environment is CONFLICTING between: {source}"],
                measurements=measurements,
                recommendation="keep one environment record per run, emitted by the process itself",
            )

        if conflict is not None:
            package, runtime_value, declared_value = conflict
            declared_ref = declared.source_path if declared is not None else "declaration"
            return self.result(
                run.run_id,
                RuleStatus.FAIL,
                f"the environment the run recorded contradicts the environment declared for the "
                f"project ({package}: run recorded {runtime_value}, {declared_ref} says "
                f"{declared_value})",
                evidence=[
                    f"runtime record cites: {_runtime_citation(run, slot)}",
                    f"declaration cites: {declared_ref}",
                ],
                measurements=measurements,
                recommendation="record the environment inside the run and keep the repository "
                "declaration in step with it, or state which one the table was produced with",
            )

        if runtime_recorded:
            limitations = []
            if not _hardware_recorded(run):
                limitations.append("no artifact records the hardware or the compute budget")
            if slot is not None and environment.value is None:
                evidence = [f"runtime record cites: {_runtime_citation(run, slot)}"]
            else:
                evidence = [
                    f"environment: {environment.value} ({environment.status.value}) at {source}"
                ]
            citation = (attached or "runtime_environment").lower()
            return self.result(
                run.run_id,
                RuleStatus.PASS,
                f"the run's own {citation} artifact records the environment it ran in",
                evidence=evidence,
                measurements=measurements,
                limitations=limitations,
            )

        if not any_evidence:
            return self.result(
                run.run_id,
                RuleStatus.NOT_APPLICABLE,
                "no runtime record and no dependency declaration exist anywhere, so this run "
                "carries no environment claim to check",
                evidence=["no artifact records the environment this run executed in"],
                measurements=measurements,
                limitations=[
                    "NOT_APPLICABLE says the question cannot arise for this project, not that "
                    "the environment was recorded or was sound",
                ],
            )

        limitations = [
            "a dependency file in the repository describes intended versions; it cannot show which "
            "versions a historical run actually loaded",
            "UNKNOWN here means the run recorded nothing about its environment, not that the "
            "environment was wrong or unreproducible",
            "a declared environment is never promoted into runtime evidence, and no agreement is "
            "inferred from versions that merely happen to be absent",
        ]
        if scalar_cited_declaration or slot_cited_declaration:
            summary = (
                "the environment is only established from a declaration outside the run's own "
                "artifacts"
            )
        else:
            summary = "no artifact records the environment this run executed in"
        return self.result(
            run.run_id,
            RuleStatus.INCONCLUSIVE,
            summary,
            evidence=[
                f"environment: {environment.value or '-'} ({environment.status.value}) at {source}",
                *declaration_evidence,
            ],
            measurements=measurements,
            limitations=limitations,
            recommendation="have the runner print interpreter, library, accelerator and device "
            "identity into the log it writes for that run",
        )


def _relationship(
    *,
    scalar_recorded: bool,
    slot: RuntimeEnvironment | None,
    declared: DeclaredEnvironment | None,
    runtime_recorded: bool,
    any_evidence: bool,
) -> EnvironmentRelationship:
    if not any_evidence:
        return EnvironmentRelationship.UNKNOWN
    if not runtime_recorded:
        return EnvironmentRelationship.ONLY_DECLARED
    if slot is not None:
        return relate_environment_evidence(slot, declared)
    if declared is not None:
        # A scalar runtime string cannot be version-compared against pins; treating
        # the absence of a contradiction as agreement is the inference this forbids.
        return EnvironmentRelationship.UNKNOWN
    if scalar_recorded:
        return EnvironmentRelationship.ONLY_RUNTIME
    return EnvironmentRelationship.ONLY_RUNTIME


def _run_recorded_runtime(run: Any) -> RuntimeEnvironment | None:
    """The run's structured runtime slot, but only when a run-local artifact cites it.

    A slot whose citations all point at repository files is declaration evidence;
    counting it as runtime would let ``environment.yml`` manufacture a PASS.
    """
    slot = run.runtime_environment
    if slot is None or not slot.is_evidenced():
        return None
    return slot if _slot_is_run_local(run, slot) else None


def _declaration_cited_runtime(run: Any) -> bool:
    """True when the runtime slot exists but is only cited outside the run's artifacts."""
    slot = run.runtime_environment
    return slot is not None and slot.is_evidenced() and not _slot_is_run_local(run, slot)


def _slot_is_conflicting(run: Any) -> bool:
    slot = run.runtime_environment
    if slot is None:
        return False
    return any(
        getattr(slot, name).status is ProvenanceStatus.CONFLICTING
        for name in ("python_version", "framework_versions", "cuda_version", "hardware", "os")
    )


def _slot_is_run_local(run: Any, slot: RuntimeEnvironment) -> bool:
    paths = {artifact.path for artifact in run.artifacts}
    if any(
        field.source is not None and field.source.path in paths
        for field in slot.evidenced_fields().values()
    ):
        return True
    return any(ref.path in paths for ref in slot.source_artifacts if ref.path)


def _hardware_recorded(run: Any) -> bool:
    if run.compute_budget.status in _RECORDED:
        return True
    slot = run.runtime_environment
    return slot is not None and slot.hardware.status in _RECORDED


def _runtime_citation(run: Any, slot: RuntimeEnvironment | None) -> str:
    if slot is not None:
        refs = [
            field.source.describe()
            for field in slot.evidenced_fields().values()
            if field.source is not None
        ]
        refs += [ref.describe() for ref in slot.source_artifacts]
        if refs:
            return "; ".join(refs[:3])
    environment: ProvenanceField[str] = run.environment
    if environment.source is not None:
        return environment.source.describe()
    return "-"


def _version_conflict(
    slot: RuntimeEnvironment | None,
    declared: DeclaredEnvironment | None,
) -> tuple[str, str, str] | None:
    """One (package, runtime value, declared value) the two sides disagree on, if any.

    Only run-local runtime records and pins the declaration actually states are
    compared; a missing pin contradicts nothing.
    """
    if slot is None or declared is None:
        return None
    if relate_environment_evidence(slot, declared) is not EnvironmentRelationship.CONFLICTING:
        return None
    runtime_versions = slot.version_map()
    declared_versions = declared.version_map()
    for name in sorted(runtime_versions.keys() & declared_versions.keys()):
        if runtime_versions[name] != declared_versions[name]:
            return name, runtime_versions[name], declared_versions[name]
    return None


def _primary_declaration(project: ExperimentProject) -> DeclaredEnvironment | None:
    """The project declaration with the richest stated pins, or None.

    Registration is the adapter's job and no v0.1 adapter fills this yet, so on the
    two accepted projects this is None and the rule reads the artifact inventory
    instead; the slot exists so the declared-versus-runtime comparison is reachable.
    """
    candidates = [
        declared for declared in project.declared_environments if declared.version_map()
    ] or list(project.declared_environments)
    return candidates[0] if candidates else None


def _declaration_paths(project: ExperimentProject) -> list[str]:
    paths = {
        artifact.path
        for artifact in project.artifacts
        if artifact.artifact_type is ArtifactType.ENVIRONMENT
        or artifact.artifact_role is ArtifactRole.DECLARED_ENVIRONMENT
    }
    paths.update(declared.source_path for declared in project.declared_environments)
    return sorted(paths)
