"""Rule engine primitives for the v0.1 formal rule set (ED001-ED010).

A rule answers one question about one entity: *is this experimental claim
supported by the artifacts that exist?*  It never answers whether the experiment
was well designed.  The five statuses are the whole vocabulary:

``PASS``            checked, and the artifacts agree with the claim
``FAIL``            checked, and the artifacts contradict the claim
``INCONCLUSIVE``    the claim could not be checked with the evidence available
``NOT_APPLICABLE``  the claim does not exist for this entity, so there is nothing
                    to check
``NOT_RUN``         the tool could not execute the check (input or capability)

Absence of evidence is therefore never promoted to a contradiction: a missing
commit, a missing seed or an unreadable log produces ``INCONCLUSIVE``, and the
summary says what cannot be established rather than what went wrong.

Status and severity are independent by construction.  Status reports the
evidence; severity reports what is at stake *if* the evidence means what it
appears to mean, which is why an ``INCONCLUSIVE`` result carries ``MEDIUM`` and
not ``HIGH`` in the rules where nothing has actually been contradicted.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from experiment_doctor.audit import AuditResult
from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef
from experiment_doctor.schema import (
    ExperimentFamily,
    ExperimentProject,
    ExperimentRun,
    Severity,
)

MEASUREMENT = int | float | str | bool | None

#: Grades that mean "an artifact of this project says so, with a citation".
_EVIDENCED = (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED)


class RuleStatus(str, Enum):
    """Frozen v0.1 outcome vocabulary.  There is no WARNING, RISKY, SAFE or INVALID."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_RUN = "NOT_RUN"


#: Statuses that report evidence rather than a judgement about the project.
UNCERTAIN_STATUSES = frozenset({RuleStatus.INCONCLUSIVE, RuleStatus.NOT_RUN})


class RuleResult(BaseModel):
    """One rule's outcome for one entity.

    ``recommendation`` is advisory text only: it is never read by anything that
    computes a status, and the tool remains read-only (it tells a project what to
    record, not what to change).
    """

    rule_id: str
    title: str
    entity_type: str
    entity_id: str
    status: RuleStatus
    severity: Severity
    summary: str
    evidence: list[str] = Field(default_factory=list)
    measurements: dict[str, MEASUREMENT] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    recommendation: str | None = None

    @property
    def is_uncertain(self) -> bool:
        return self.status in UNCERTAIN_STATUSES


@dataclass
class RuleContext:
    """Everything a rule may read: the scanned project plus the five audit checks.

    Rules consume the unified schema and the check outputs; they never open a
    project file and never learn a project's format.
    """

    project: ExperimentProject
    audit: AuditResult
    _runs_by_family: dict[str, list[ExperimentRun]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for run in self.project.runs:
            self._runs_by_family.setdefault(run.family_id, []).append(run)

    def runs_of(self, family_id: str) -> list[ExperimentRun]:
        return self._runs_by_family.get(family_id, [])

    def family(self, family_id: str) -> ExperimentFamily | None:
        return self.project.family(family_id)

    def run(self, run_id: str) -> ExperimentRun | None:
        return self.project.run(run_id)

    def identity(self, family_id: str) -> Any:
        return _by_key(self.audit.identity, family_id)

    def seeds(self, family_id: str) -> Any:
        return _by_key(self.audit.seeds, family_id)

    def membership(self, family_id: str) -> Any:
        return _by_key(self.audit.membership, family_id)


def _by_key(items: Iterable[Any], key: str) -> Any:
    for item in items:
        if getattr(item, "family_id", None) == key:
            return item
    return None


#: Artifact types that describe intent rather than execution: a repository-level
#: dependency lock, a config template or a script is not something the run produced.
DECLARATIVE_ARTIFACT_TYPES = frozenset({"CONFIG", "SCRIPT", "ENVIRONMENT", "TABLE"})


def attached_to_run(run: ExperimentRun, source: SourceRef | None) -> str | None:
    """Return the artifact type when a field's source is one of this run's own files.

    A repository file (``environment.yml``, ``requirements.txt``, a config template,
    the current clone) can support a value without ever having been present at run
    time, so it does not appear in a run's artifact list and does not qualify.
    """
    if source is None or not source.path:
        return None
    for artifact in run.artifacts:
        if artifact.path == source.path:
            return artifact.artifact_type.value
    return None


def run_recorded(field: ProvenanceField[Any]) -> bool:
    """True when a value has a citable source at all, run-local or not."""
    return field.status in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.SUPPORTED)


class Rule(ABC):
    """One formal rule.  Ten exist; there is no scheduler and no plugin loading."""

    rule_id: ClassVar[str] = ""
    title: ClassVar[str] = ""
    purpose: ClassVar[str] = ""
    entity_type: ClassVar[str] = ""
    #: Severity carried when the artifacts contradict the claim.
    fail_severity: ClassVar[Severity] = Severity.HIGH
    #: Severity carried when the artifacts cannot settle the question.
    inconclusive_severity: ClassVar[Severity] = Severity.MEDIUM
    #: Severity carried when the check contradicts nothing but the claim is absent.
    not_applicable_severity: ClassVar[Severity] = Severity.INFO

    @abstractmethod
    def evaluate(self, context: RuleContext) -> list[RuleResult]: ...

    def result(
        self,
        entity_id: str,
        status: RuleStatus,
        summary: str,
        *,
        evidence: Iterable[str] = (),
        measurements: Mapping[str, MEASUREMENT] | None = None,
        limitations: Iterable[str] = (),
        severity: Severity | None = None,
        recommendation: str | None = None,
    ) -> RuleResult:
        return RuleResult(
            rule_id=self.rule_id,
            title=self.title,
            entity_type=self.entity_type,
            entity_id=entity_id,
            status=status,
            severity=severity if severity is not None else self.default_severity(status),
            summary=summary,
            evidence=[item for item in evidence if item],
            measurements=dict(measurements or {}),
            limitations=list(limitations),
            recommendation=recommendation,
        )

    def default_severity(self, status: RuleStatus) -> Severity:
        if status is RuleStatus.FAIL:
            return self.fail_severity
        if status in UNCERTAIN_STATUSES:
            return self.inconclusive_severity
        if status is RuleStatus.NOT_APPLICABLE:
            return self.not_applicable_severity
        return Severity.INFO

    def describe(self) -> dict[str, str]:
        return {
            "id": self.rule_id,
            "title": self.title,
            "entity": self.entity_type,
            "description": self.purpose,
        }


def claim_comparison(implemented: ProvenanceField[Any], documented: ProvenanceField[Any]) -> str:
    """Classify an implemented-versus-documented claim, the shared shape of ED005 and ED008.

    ``implementation-only`` is not the same as ``documentation-only``: the artifact that
    produced the number establishes what it is, whereas prose alone leaves the quantity
    behind the number undetermined.
    """
    if ProvenanceStatus.CONFLICTING in (implemented.status, documented.status):
        return "conflicting-evidence"
    impl = implemented.status in _EVIDENCED and implemented.value is not None
    doc = documented.status in _EVIDENCED and documented.value is not None
    if impl and doc:
        return "consistent" if implemented.value == documented.value else "contradiction"
    if impl:
        return "implementation-only"
    if doc:
        return "documentation-only"
    return "undetermined"


def status_of_field(field: ProvenanceField[Any]) -> str:
    return str(field.status.value)


def sources_of(*fields: ProvenanceField[Any]) -> list[str]:
    return [field.source.describe() for field in fields if field.source is not None]
