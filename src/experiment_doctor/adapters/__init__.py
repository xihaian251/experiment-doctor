"""Adapter registry.  Importing this module installs the shipped adapters."""

from __future__ import annotations

from pathlib import Path

from experiment_doctor.adapters import generic, gmmvi
from experiment_doctor.scanner import AdapterSpec, ExperimentAdapter, registry, select_adapter


def install_adapters() -> None:
    """Idempotent registration of every adapter v0.1 ships."""
    if any(spec.name == "generic" for spec in registry()):
        return
    generic.install()
    gmmvi.install()


def available_adapters() -> list[AdapterSpec]:
    install_adapters()
    return registry()


def build(name: str, root: Path) -> ExperimentAdapter:
    install_adapters()
    for spec in registry():
        if spec.name == name:
            return spec.factory(Path(root))
    raise KeyError(f"unknown adapter '{name}'; available: {', '.join(s.name for s in registry())}")


__all__ = ["available_adapters", "build", "install_adapters", "select_adapter"]
