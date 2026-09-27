"""Git provenance capture via ``subprocess`` (stdlib only, no GitPython).

Each function returns an evidence-graded field; a missing git binary, a
non-repository directory or a failed call yields ``UNKNOWN`` with no value --
never a guess (the GMMVI lesson: 0 of 7,004 archived files named the commit).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef

_GIT_TIMEOUT_S = 20


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    if shutil.which("git") is None:
        return None
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _failed(note: str) -> ProvenanceField[str]:
    return ProvenanceField(value=None, status=ProvenanceStatus.UNKNOWN, confidence_note=note)


def repository_root(cwd: Path) -> ProvenanceField[str]:
    proc = _git(["rev-parse", "--show-toplevel"], cwd)
    if proc is None or proc.returncode != 0:
        return _failed("git unavailable or directory is not a repository")
    return ProvenanceField.of(
        proc.stdout.strip(),
        ProvenanceStatus.CONFIRMED,
        SourceRef(note="git rev-parse --show-toplevel"),
    )


def repository_url(root: Path) -> ProvenanceField[str]:
    """``origin`` URL when present, else the local root path (never a guess)."""
    proc = _git(["remote", "get-url", "origin"], root)
    if proc is not None and proc.returncode == 0 and proc.stdout.strip():
        return ProvenanceField.of(
            proc.stdout.strip(),
            ProvenanceStatus.CONFIRMED,
            SourceRef(note="git remote get-url origin"),
        )
    root_field = repository_root(root)
    if root_field.value is not None:
        return ProvenanceField.of(
            str(root_field.value),
            ProvenanceStatus.SUPPORTED,
            SourceRef(note="repository root path (no origin remote)"),
        )
    return _failed("no origin remote and no repository root")


def current_commit(root: Path) -> ProvenanceField[str]:
    proc = _git(["rev-parse", "HEAD"], root)
    if proc is None or proc.returncode != 0 or not proc.stdout.strip():
        return _failed("git HEAD not resolvable")
    return ProvenanceField.of(
        proc.stdout.strip(), ProvenanceStatus.CONFIRMED, SourceRef(note="git rev-parse HEAD")
    )


def is_dirty(root: Path) -> ProvenanceField[bool]:
    """True iff tracked changes *or* untracked files exist (both alter the run)."""
    tracked = _git(["status", "--porcelain"], root)
    if tracked is None or tracked.returncode != 0:
        return ProvenanceField(
            value=None, status=ProvenanceStatus.UNKNOWN, confidence_note="git status not available"
        )
    dirty = bool(tracked.stdout.strip())
    return ProvenanceField.of(
        dirty, ProvenanceStatus.CONFIRMED, SourceRef(note="git status --porcelain")
    )


def diff_hash(root: Path) -> ProvenanceField[str]:
    """sha256 over tracked diff plus untracked file names/contents.

    A bare commit does not identify a dirty work tree (the TorchSSL lesson: the
    shipped checkout disagreed with the archived logs), so untracked content is
    folded into the hash.  ``UNKNOWN`` when the tree is clean: there is nothing
    to hash, and that absence is recorded, not fabricated.
    """
    tracked = _git(["diff"], root)
    untracked = _git(["ls-files", "--others", "--exclude-standard"], root)
    if tracked is None or untracked is None:
        return _failed("git unavailable")
    if tracked.returncode != 0 or untracked.returncode != 0:
        return _failed("git diff/ls-files failed")
    if not tracked.stdout.strip() and not untracked.stdout.strip():
        return _failed("clean work tree: no diff to hash")
    digest = hashlib.sha256()
    digest.update(tracked.stdout.encode("utf-8", errors="replace"))
    for name in sorted(untracked.stdout.splitlines()):
        digest.update(f"\n---untracked {name}\n".encode("utf-8"))
        path = root / name
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
    return ProvenanceField.of(
        "sha256:" + digest.hexdigest(),
        ProvenanceStatus.CONFIRMED,
        SourceRef(note="sha256(git diff + untracked file contents)"),
    )
