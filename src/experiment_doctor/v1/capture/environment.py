"""Environment capture: the interpreter, resolved packages, platform.

This is the runtime side of the CRDA finding that declaration is not execution
(``requirements.txt`` present, ``runtime_environment`` absent for 1,350 runs):
everything here is read from the process that will actually run the experiment.
"""

from __future__ import annotations

import platform as _platform
import sys
from importlib import metadata

from experiment_doctor.provenance import ProvenanceField, ProvenanceStatus, SourceRef


def python_version() -> ProvenanceField[str]:
    return ProvenanceField.of(
        sys.version.split()[0], ProvenanceStatus.CONFIRMED, SourceRef(note="sys.version")
    )


def installed_packages() -> ProvenanceField[dict[str, str]]:
    """name -> version for every distribution importlib can resolve.

    The *resolved* set, not a declared file: this is what the interpreter would
    actually import.
    """
    try:
        packages = {
            dist.metadata["Name"]: dist.version
            for dist in metadata.distributions()
            if dist.metadata["Name"]
        }
    except metadata.PackageNotFoundError:  # pragma: no cover - defensive
        return ProvenanceField(
            value=None,
            status=ProvenanceStatus.UNKNOWN,
            confidence_note="package metadata unreadable",
        )
    return ProvenanceField.of(
        dict(sorted(packages.items())),
        ProvenanceStatus.CONFIRMED,
        SourceRef(note="importlib.metadata.distributions()"),
    )


def platform_info() -> ProvenanceField[str]:
    return ProvenanceField.of(
        _platform.platform(), ProvenanceStatus.CONFIRMED, SourceRef(note="platform.platform()")
    )
