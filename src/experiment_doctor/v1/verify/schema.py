"""``verify.json`` schema (v1 Phase 3): VerificationReport.

Hard schema rules from the task book: no ``overall_score``, no ``confidence``,
no ``trust_score``.  Statuses are the four deterministic grades; ``UNKNOWN``
evidence never escalates into a FAIL (missing/unobservable claims are
INCONCLUSIVE or NOT_APPLICABLE, both of which exit 0).
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef

SCHEMA_VERSION = "1.0"
REQUIRED_BUNDLE_FILES = ("experiment.lock.json", "experiment.run.json", "stdout.log", "stderr.log")


def _unknown(name: str) -> ProvenanceField[Any]:
    return ProvenanceField(
        value=None,
        status=ProvenanceStatus.UNKNOWN,
        confidence_note=f"{name}: not observable in the bundle",
    )


def vf(value: Any, note: str) -> ProvenanceField[Any]:
    """Wrap a direct observation of the verifier itself."""
    return ProvenanceField.of(value, ProvenanceStatus.CONFIRMED, SourceRef(note=note))


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CheckRecord(BaseModel):
    check_id: str
    status: CheckStatus
    evidence: list[str] = Field(default_factory=list)
    message: str


class HashPair(BaseModel):
    """stored (= claimed by the file) vs recomputed (= observed now)."""

    expected: ProvenanceField[str] = _unknown("expected (stored hash)")
    observed: ProvenanceField[str] = _unknown("observed (recomputed hash)")


class BundleIdentity(BaseModel):
    bundle_path: ProvenanceField[str] = _unknown("bundle_identity.bundle_path")
    lock_hash_expected: ProvenanceField[str] = _unknown("bundle_identity.lock_hash_expected")
    lock_hash_observed: ProvenanceField[str] = _unknown("bundle_identity.lock_hash_observed")
    run_hash_expected: ProvenanceField[str] = _unknown("bundle_identity.run_hash_expected")
    run_hash_observed: ProvenanceField[str] = _unknown("bundle_identity.run_hash_observed")


class VerificationReport(BaseModel):
    schema_version: str = SCHEMA_VERSION
    bundle_identity: BundleIdentity = Field(default_factory=BundleIdentity)
    checks: list[CheckRecord] = Field(default_factory=list)

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def fails(self) -> list[CheckRecord]:
        return [c for c in self.checks if c.status is CheckStatus.FAIL]

    @property
    def exit_code(self) -> int:
        """FAIL -> 1; PASS/INCONCLUSIVE/NOT_APPLICABLE -> 0.  UNKNOWN is not an error."""
        return 1 if self.fails else 0


def file_sha256(path: Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def recompute_seal_hash(path: Any, hash_key: str) -> tuple[str | None, str | None]:
    """Return (stored_hash, recomputed_hash) over the file's canonical body.

    The recomputation uses the identical Phase 1/2 contract: drop the seal key,
    sort keys, no whitespace, UTF-8 safe.  Returns None entries when the file
    cannot be read or parsed -- which the checks report honestly.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8") if hasattr(path, "read_text") else "")
    except (OSError, ValueError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    stored = data.pop(hash_key, None)
    body = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    recomputed = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
    return stored, recomputed
