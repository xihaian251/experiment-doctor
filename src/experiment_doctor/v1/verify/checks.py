"""V001-V006: the six deterministic checks of Phase 3.

Each check reads the bundle and reports what it observed.  No check ever
writes to, repairs, or re-serialises a lock/run file, and no check looks at
stdout content, metrics or exit-code semantics (those are not evidence-grade
claims in a bundle).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from experiment_doctor.provenance import ProvenanceStatus
from experiment_doctor.v1.lock.schema import ExperimentLock
from experiment_doctor.v1.run.schema import ExperimentRunRecord
from experiment_doctor.v1.verify.schema import (
    REQUIRED_BUNDLE_FILES,
    BundleIdentity,
    CheckRecord,
    CheckStatus,
    HashPair,
    VerificationReport,
    file_sha256,
    recompute_seal_hash,
    vf,
)

LOCK_NAME = "experiment.lock.json"
RUN_NAME = "experiment.run.json"
BUNDLE_MARKER = "experiment-evidence"

#: fields whose values are filesystem-path claims made by capture code
PATH_CLAIM_FIELDS = {
    "lock_path",
    "stdout_path",
    "stderr_path",
    "output_directory",
    "paths",
    "config_files",
}
#: records whose path claims are bundle-write claims (V006 scope).  The lock's
#: cwd/lock_path are input-side observations, not bundle writes -> exempt.
V006_SCANNED_SOURCES = ("run",)
#: the path claim that defines the boundary itself (allowed to be absolute)
PATH_BOUNDARY_FIELDS = {"cwd"}
#: string carriers deliberately exempt from the path-boundary scan
PATH_SCAN_EXEMPT = {"repository", "seed_source", "note", "confidence_note", "source"}


def resolve_bundle(directory: Path) -> Path:
    """Accept a bundle dir, or a project dir that contains one."""
    directory = directory.resolve()
    if (directory / BUNDLE_MARKER).is_dir():
        return directory / BUNDLE_MARKER
    if (directory / LOCK_NAME).is_file() or (directory / RUN_NAME).is_file():
        return directory
    raise ValueError(f"no evidence bundle found in {directory}")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _pair(path: Path, hash_key: str) -> HashPair:
    stored, recomputed = recompute_seal_hash(path, hash_key)
    pair = HashPair()
    if stored is not None:
        pair.expected = vf(stored, f"stored {hash_key} claimed by {path.name}")
    if recomputed is not None:
        pair.observed = vf(recomputed, f"recomputed sha256 over {path.name} canonical body")
    return pair


def _check(check_id: str, status: CheckStatus, evidence: list[str], message: str) -> CheckRecord:
    return CheckRecord(check_id=check_id, status=status, evidence=evidence, message=message)


def _v001(pair: HashPair, lock: ExperimentLock | None) -> CheckRecord:
    cid = "V001"
    stored, recomputed = pair.expected.value, pair.observed.value
    if stored is None or recomputed is None:
        return _check(
            cid,
            CheckStatus.FAIL,
            [],
            "lock file missing, unreadable or unparseable; seal unverifiable",
        )
    if stored != recomputed:
        return _check(
            cid,
            CheckStatus.FAIL,
            [f"stored={stored}", f"recomputed={recomputed}"],
            "lock body does not match its seal: experiment.lock.json was edited after sealing",
        )
    if lock is None:
        return _check(
            cid,
            CheckStatus.FAIL,
            ["seal matches but the body violates the ProvenanceField invariants"],
            "lock hash is consistent but the lock is structurally invalid",
        )
    return _check(
        cid,
        CheckStatus.PASS,
        [f"stored == recomputed == {stored}"],
        "lock canonical body matches its seal (canonical_json/lock_hash contract of Phase 1)",
    )


def _v002(run: ExperimentRunRecord | None, observed_lock_hash: str | None) -> CheckRecord:
    cid = "V002"
    if run is None:
        return _check(
            cid, CheckStatus.NOT_APPLICABLE, [], "run record unavailable; nothing to compare"
        )
    ref = run.lock_reference.lock_hash
    if ref.value is None or ref.status is ProvenanceStatus.UNKNOWN:
        return _check(
            cid,
            CheckStatus.INCONCLUSIVE,
            [f"lock_reference.lock_hash is UNKNOWN ({ref.confidence_note})"],
            "the run makes no lock-hash claim; absence is not a mismatch",
        )
    if observed_lock_hash is None:
        return _check(
            cid,
            CheckStatus.INCONCLUSIVE,
            ["lock hash could not be recomputed from the bundle"],
            "reference exists but there is no trustworthy observed lock hash to compare",
        )
    if ref.value != observed_lock_hash:
        return _check(
            cid,
            CheckStatus.FAIL,
            [f"run claims {ref.value}", f"bundle lock recomputes to {observed_lock_hash}"],
            "run references a different lock than the one shipped in this bundle",
        )
    return _check(
        cid, CheckStatus.PASS, [f"{ref.value} == observed"], "run -> lock chain is intact"
    )


def _v003(pair: HashPair, run: ExperimentRunRecord | None) -> CheckRecord:
    cid = "V003"
    stored, recomputed = pair.expected.value, pair.observed.value
    if stored is None or recomputed is None:
        return _check(
            cid,
            CheckStatus.FAIL,
            [],
            "run record missing, unreadable or unparseable; seal unverifiable",
        )
    if stored != recomputed:
        return _check(
            cid,
            CheckStatus.FAIL,
            [f"stored={stored}", f"recomputed={recomputed}"],
            "run body does not match its seal: experiment.run.json was edited after sealing",
        )
    if run is None:
        return _check(
            cid,
            CheckStatus.FAIL,
            ["seal matches but the body violates the ProvenanceField invariants"],
            "run hash is consistent but the record is structurally invalid",
        )
    return _check(
        cid,
        CheckStatus.PASS,
        [f"stored == recomputed == {stored}"],
        "run canonical body matches its seal (canonical_json/run_hash contract of Phase 2)",
    )


def _v004(bundle: Path) -> CheckRecord:
    missing = [name for name in REQUIRED_BUNDLE_FILES if not (bundle / name).is_file()]
    empty = [
        name
        for name in REQUIRED_BUNDLE_FILES
        if (bundle / name).is_file() and (bundle / name).stat().st_size == 0
    ]
    evidence = [f"required: {', '.join(REQUIRED_BUNDLE_FILES)}"]
    bad_json = [name for name in empty if name.endswith(".json")]
    if missing:
        evidence.append(f"missing: {missing}")
        return _check("V004", CheckStatus.FAIL, evidence, "incomplete bundle")
    if bad_json:
        evidence.append(f"empty json (zero-byte): {bad_json}")
        return _check(
            "V004",
            CheckStatus.FAIL,
            evidence,
            "members exist but some are zero-byte; for logs that is a faithful record of a "
            "silent run, not a structural violation -- but the JSON records must never be empty",
        )
    return _check(
        "V004",
        CheckStatus.PASS,
        evidence,
        "all four required bundle members exist and are non-empty",
    )


def _resolve_claimed(name: str, bundle: Path, project: Path | None) -> Path | None:
    p = Path(name)
    candidates = [p] if p.is_absolute() else []
    candidates.append(bundle / name)
    if project is not None:
        candidates.append(project / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _v005(run: ExperimentRunRecord | None, bundle: Path, project: Path | None) -> CheckRecord:
    cid = "V005"
    if run is None:
        return _check(cid, CheckStatus.NOT_APPLICABLE, [], "run record unavailable")
    claims: list[tuple[str, str, str]] = []
    for label in ("created_files", "modified_files"):
        field = getattr(run.artifacts, label)
        if field.value is None or field.status is ProvenanceStatus.UNKNOWN:
            continue
        claims.extend((label, name, digest) for name, digest in field.value.items())
    if not claims:
        return _check(
            cid,
            CheckStatus.NOT_APPLICABLE,
            ["artifacts.created_files/modified_files carry no claims"],
            "the run declared no artifact writes; there is nothing to confirm or deny",
        )
    missing: list[str] = []
    mismatched: list[str] = []
    verified = 0
    for label, name, digest in claims:
        found = _resolve_claimed(name, bundle, project)
        if found is None:
            missing.append(f"{label}:{name}")
        elif file_sha256(found) != digest:
            mismatched.append(f"{label}:{name}")
        else:
            verified += 1
    evidence = [f"claims={len(claims)}", f"verified={verified}"]
    if mismatched:
        evidence.append(f"content mismatch: {mismatched}")
        return _check(
            cid,
            CheckStatus.FAIL,
            evidence,
            "recorded artifact digests do not match the files that are present",
        )
    if missing:
        evidence.append(f"not found at verify time: {missing}")
        return _check(
            cid,
            CheckStatus.INCONCLUSIVE,
            evidence,
            "recorded artifacts are not findable now; NOT read as deletion (they may live on "
            "another machine or volume) and NOT as fabrication",
        )
    return _check(cid, CheckStatus.PASS, evidence, "every recorded artifact matches its digest")


def _walk_values(data: Any, trail: str = "") -> Iterator[tuple[str, str, str]]:
    """Yield (trail, owning-field, string) for ProvenanceField ``value`` carriers."""
    if isinstance(data, dict):
        for key, value in data.items():
            yield from _walk_values(value, f"{trail}.{key}" if trail else str(key))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from _walk_values(value, f"{trail}[{index}]")
    elif isinstance(data, str):
        owner = "unknown"
        parts = trail.split(".")
        for index, part in enumerate(parts):
            if part == "value" and index > 0:
                owner = parts[index - 1]
                break
        yield trail, owner, data


def _outside(path: Path, *roots: Path | None) -> bool:
    for root in roots:
        if root is None:
            continue
        try:
            path.relative_to(root)
            return False
        except ValueError:
            continue
    return True


def _looks_absolute(value: str) -> bool:
    return Path(value).is_absolute() or (len(value) > 2 and value[1] == ":" and value[2] in "\\/")


def _v006(run_data: dict[str, Any] | None, bundle: Path) -> CheckRecord:
    """Path-boundary check: records must not claim locations outside the project.

    ``execution.cwd`` is capture-observed and *defines* the boundary, so it is
    allowed to be absolute; free-text fields are exempt (a note is not a write
    claim).  The boundary = bundle dir ∪ its parent (the project that ran).
    """
    project = bundle.parent
    offenders: list[str] = []
    scanned = 0
    sources: dict[str, dict[str, Any] | None] = {"run": run_data}
    for source in V006_SCANNED_SOURCES:
        data = sources.get(source)
        if data is None:
            continue
        body = {k: v for k, v in data.items() if k not in ("lock_hash", "run_hash")}
        for trail, owner, value in _walk_values(body):
            if any(exempt in trail for exempt in PATH_SCAN_EXEMPT):
                continue
            if not _looks_absolute(value):
                continue
            if owner in PATH_BOUNDARY_FIELDS:
                if _outside(Path(value), bundle, project):
                    offenders.append(f"{source}.{trail} defines an out-of-bundle cwd: {value}")
                continue
            if owner not in PATH_CLAIM_FIELDS:
                continue
            scanned += 1
            if _outside(Path(value), bundle, project):
                offenders.append(f"{source}.{trail} -> {value}")
    evidence = [f"absolute path claims scanned: {scanned}"]
    if offenders:
        return _check(
            "V006",
            CheckStatus.FAIL,
            evidence + offenders,
            "evidence records claim locations outside the project that produced the bundle",
        )
    return _check(
        "V006",
        CheckStatus.PASS,
        evidence,
        "no path claim resolves outside the bundle/project boundary (cwd defines it, notes exempt)",
    )


def verify_bundle(directory: Path) -> tuple[VerificationReport, Path]:
    bundle = resolve_bundle(directory)
    lock_path, run_path = bundle / LOCK_NAME, bundle / RUN_NAME

    lock_data = _load_json(lock_path)
    run_data = _load_json(run_path)
    lock: ExperimentLock | None = None
    run: ExperimentRunRecord | None = None
    try:
        if lock_data is not None:
            lock = ExperimentLock.model_validate(lock_data)
    except ValidationError:
        lock = None
    try:
        if run_data is not None:
            run = ExperimentRunRecord.model_validate(run_data)
    except ValidationError:
        run = None

    lock_pair = _pair(lock_path, "lock_hash")
    run_pair = _pair(run_path, "run_hash")
    identity = BundleIdentity(
        bundle_path=vf(str(bundle), "resolved bundle directory"),
        lock_hash_expected=lock_pair.expected,
        lock_hash_observed=lock_pair.observed,
        run_hash_expected=run_pair.expected,
        run_hash_observed=run_pair.observed,
    )
    checks = [
        _v001(lock_pair, lock),
        _v002(run, lock_pair.observed.value),
        _v003(run_pair, run),
        _v004(bundle),
        _v005(run, bundle, bundle.parent),
        _v006(run_data, bundle),
    ]
    return VerificationReport(bundle_identity=identity, checks=checks), bundle


def render_markdown(report: VerificationReport, bundle: Path) -> str:
    lines = [
        "# Verification report",
        "",
        f"- bundle: `{bundle}`",
        f"- report digest: `{report.digest()}`",
        f"- exit code: {report.exit_code} (only FAIL exits 1; UNKNOWN is not an error)",
        "",
        "| check | status | message |",
        "|---|---|---|",
    ]
    for check in report.checks:
        lines.append(f"| {check.check_id} | {check.status.value} | {check.message} |")
    lines += ["", "## Evidence", ""]
    for check in report.checks:
        lines.append(f"- **{check.check_id}** ({check.status.value}): {check.evidence or '-'}")
    return "\n".join(lines) + "\n"


def write_verify_outputs(report: VerificationReport, bundle: Path) -> tuple[Path, Path]:
    json_path = bundle / "verify.json"
    md_path = bundle / "verify.md"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report, bundle), encoding="utf-8")
    return json_path, md_path
