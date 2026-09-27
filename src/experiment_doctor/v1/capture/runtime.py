"""Invocation facts: command, working directory, timestamps.

Only what is directly observable is graded CONFIRMED.  The training command is
never invented from a ``train.py`` on disk (GMMVI's effective budget was injected
through a gitignored file -- what runs can differ from what is shipped), so it
must be declared to be captured.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def timestamp_field() -> ProvenanceField[str]:
    return ProvenanceField.of(
        now_iso(), ProvenanceStatus.CONFIRMED, SourceRef(note="system clock (UTC)")
    )


def declared_command(command: str | None) -> ProvenanceField[str]:
    if command is None or not command.strip():
        return ProvenanceField(
            value=None,
            status=ProvenanceStatus.UNKNOWN,
            confidence_note="no --command given; the invoked command is not inferred",
        )
    return ProvenanceField.of(
        command.strip(), ProvenanceStatus.CONFIRMED, SourceRef(note="declared via --command")
    )


def working_directory(cwd: Path) -> ProvenanceField[str]:
    return ProvenanceField.of(
        str(cwd.resolve()),
        ProvenanceStatus.CONFIRMED,
        SourceRef(note="capture-time working directory"),
    )
