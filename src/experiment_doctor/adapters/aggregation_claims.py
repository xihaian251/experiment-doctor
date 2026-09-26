"""What a project's own files state about the statistics in its reported tables.

A published ``mean +/- spread`` cell rests on two independent statements: the
script that builds the number, and - when the authors wrote one - a sentence that
names the statistic.  This module extracts only what a line actually says.

* :func:`spread_expressions` reads an aggregation script and reports, per computing
  line, whether the spread divides by ``sqrt(N)`` and what multiplier stands in
  front of it.
* :func:`prose_claims` reads documentation and reports the statistic vocabulary it
  contains, quoting the sentence it matched.

Both feed :class:`StatisticClaims`, which is what an adapter writes onto an
``AggregationRecord``.  Three of its four fields are readable from the files;
which *observation of a run* a script aggregates is project knowledge and stays
with the adapter.  A project that never states its spread semantics in prose gets
UNKNOWN there rather than an assumed convention, and a project whose files state
two different things gets CONFLICTING rather than the reading that matches.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from experiment_doctor.provenance import (
    ProvenanceField,
    ProvenanceStatus,
    SourceRef,
    unknown_field,
)
from experiment_doctor.schema import AggregationRecord, SelectionPolicy, SpreadSemantics

#: The separator a project prints between a mean and its spread, matched case-insensitively
#: because the escape appears as both ``\\u00b1`` and ``\\u00B1`` in real scripts.
CELL_SEPARATORS = ("+/-", "\\u00b1", "±")
#: The call that computes the spread across a group of run values.
STD_CALL = "np.std("
#: Prose files a project might state its reporting conventions in.
README_NAMES = ("README.md", "README.rst", "README.txt", "README")

_SQRT = re.compile(r"(?:np|numpy|math)\.sqrt\s*\(")
_MULTIPLIER_BEFORE_SQRT = re.compile(r"([0-9]*\.?[0-9]+)\s*/\s*(?:np|numpy|math)\.sqrt")
_MULTIPLIER_BEFORE_STD = re.compile(r"([0-9]*\.?[0-9]+)\s*\*\s*(?:np|numpy|math)\.std")

#: Phrases that name what a ``+/-`` is.  A bare "std" or "error" is not a claim.
SPREAD_TERMS: tuple[tuple[str, SpreadSemantics], ...] = (
    ("standard error", SpreadSemantics.STANDARD_ERROR),
    ("standard deviation", SpreadSemantics.STANDARD_DEVIATION),
)

#: Phrases that name which observation of a run a published number stands for.
#: "best run" and "best setting" are deliberately absent: they pick a configuration,
#: not a checkpoint, so reading them as a selection policy would invent a claim.
SELECTION_TERMS: tuple[tuple[str, SelectionPolicy], ...] = (
    ("best accurac", SelectionPolicy.BEST),
    ("best checkpoint", SelectionPolicy.BEST),
    ("best epoch", SelectionPolicy.BEST),
    ("best model", SelectionPolicy.BEST),
    ("final performance", SelectionPolicy.LAST),
    ("final epoch", SelectionPolicy.LAST),
    ("last epoch", SelectionPolicy.LAST),
)


@dataclass(frozen=True)
class SpreadExpression:
    """One line of aggregation code that computes a reported spread."""

    semantics: SpreadSemantics
    multiplier: float
    divides_by_sqrt_n: bool
    line: int
    text: str


@dataclass(frozen=True)
class ProseClaim:
    """A sentence of documentation that names a reported statistic."""

    spread: SpreadSemantics | None
    selection: SelectionPolicy | None
    line: int
    text: str


@dataclass
class StatisticClaims:
    """The statistic-level attestations one aggregation record can carry.

    ``implemented_selection`` is left UNKNOWN by :func:`collect_claims`: which
    observation of a run a script aggregates is read from that script by the
    adapter that understands it.
    """

    implemented_spread: ProvenanceField[SpreadSemantics] = field(default_factory=unknown_field)
    documented_spread: ProvenanceField[SpreadSemantics] = field(default_factory=unknown_field)
    implemented_selection: ProvenanceField[SelectionPolicy] = field(default_factory=unknown_field)
    documented_selection: ProvenanceField[SelectionPolicy] = field(default_factory=unknown_field)

    def apply_to(self, record: AggregationRecord) -> None:
        """Write the four attestations onto the record they describe."""
        record.implemented_spread = self.implemented_spread
        record.documented_spread = self.documented_spread
        record.implemented_selection = self.implemented_selection
        record.documented_selection = self.documented_selection


def read_lines(path: Path | None) -> list[str]:
    if path is None or not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def readme_of(root: Path | None) -> Path | None:
    """The repository's README, or None when the root holds none."""
    if root is None:
        return None
    for name in README_NAMES:
        path = root / name
        if path.is_file():
            return path
    return None


def find_line(lines: Sequence[str], needle: str) -> tuple[int, str] | None:
    """The first uncommented line containing ``needle``, as (1-based number, text)."""
    for number, text in enumerate(lines, start=1):
        if text.strip().startswith("#"):
            continue
        if needle in text:
            return number, text.strip()[:200]
    return None


def spread_expressions(lines: Sequence[str]) -> list[SpreadExpression]:
    """Every uncommented line that computes ``np.std`` while printing a mean+/-spread cell."""
    found: list[SpreadExpression] = []
    for number, text in enumerate(lines, start=1):
        stripped = text.strip()
        if stripped.startswith("#") or STD_CALL not in text:
            continue
        lowered = text.lower()
        if not any(separator in lowered for separator in CELL_SEPARATORS):
            continue
        divides = bool(_SQRT.search(text))
        matched = _MULTIPLIER_BEFORE_SQRT.search(text) if divides else None
        if matched is None:
            matched = _MULTIPLIER_BEFORE_STD.search(text)
        multiplier = float(matched.group(1)) if matched else 1.0
        found.append(
            SpreadExpression(
                semantics=_semantics(divides, multiplier),
                multiplier=multiplier,
                divides_by_sqrt_n=divides,
                line=number,
                text=stripped[:200],
            )
        )
    return found


def _semantics(divides_by_sqrt_n: bool, multiplier: float) -> SpreadSemantics:
    if divides_by_sqrt_n:
        return (
            SpreadSemantics.STANDARD_ERROR
            if multiplier == 1.0
            else SpreadSemantics.SCALED_STANDARD_ERROR
        )
    if multiplier == 1.0:
        return SpreadSemantics.STANDARD_DEVIATION
    return SpreadSemantics.CUSTOM


def prose_claims(lines: Sequence[str]) -> list[ProseClaim]:
    """Every documentation line that names a spread or a selection statistic."""
    claims: list[ProseClaim] = []
    for number, text in enumerate(lines, start=1):
        lowered = text.lower()
        spreads = [value for term, value in SPREAD_TERMS if term in lowered]
        selections = [value for term, value in SELECTION_TERMS if term in lowered]
        if not spreads and not selections:
            continue
        claims.append(
            ProseClaim(
                spread=spreads[0] if len(set(spreads)) == 1 else None,
                selection=selections[0] if len(set(selections)) == 1 else None,
                line=number,
                text=text.strip()[:200],
            )
        )
    return claims


T = TypeVar("T")

#: An attested value with the line that states it and the text shown as its citation.
Attributed = tuple[T, int, str]


def attest(
    items: Sequence[Attributed[T]],
    rel_path: str,
    *,
    absent_note: str,
    note: str,
) -> ProvenanceField[T]:
    """Turn matched (value, line, citation) triples into an evidenced claim."""
    if not items:
        return ProvenanceField.unknown(note=absent_note)
    sources = [SourceRef(path=rel_path, line=line, key=citation) for _v, line, citation in items]
    distinct = {item[0] for item in items}
    if len(distinct) > 1:
        named = " and ".join(sorted(str(getattr(value, "value", value)) for value in distinct))
        return ProvenanceField.conflicting(
            sources, note=f"{rel_path} states both {named}; neither is assertable alone"
        )
    return ProvenanceField.of(items[0][0], ProvenanceStatus.CONFIRMED, sources[0], note=note)


def collect_claims(
    *,
    script: Path | None,
    script_rel: str,
    readme: Path | None,
    readme_rel: str,
) -> StatisticClaims:
    """Read the spread semantics and the documented selection out of a project's files."""
    shapes: list[Attributed[SpreadSemantics]] = []
    for expression in spread_expressions(read_lines(script)):
        shape = f"{format(expression.multiplier, 'g')} x std"
        if expression.divides_by_sqrt_n:
            shape += " / sqrt(N)"
        shapes.append((expression.semantics, expression.line, shape))
    claims = prose_claims(read_lines(readme))
    spreads: list[Attributed[SpreadSemantics]] = [
        (claim.spread, claim.line, claim.text) for claim in claims if claim.spread is not None
    ]
    selections: list[Attributed[SelectionPolicy]] = [
        (claim.selection, claim.line, claim.text) for claim in claims if claim.selection is not None
    ]
    return StatisticClaims(
        implemented_spread=attest(
            shapes,
            script_rel,
            absent_note=f"{script_rel} has no line computing a spread for a printed "
            "mean+/-spread cell",
            note="the multiplier and any sqrt(N) division are read off the cited line",
        ),
        documented_spread=attest(
            spreads,
            readme_rel,
            absent_note=f"no sentence of {readme_rel} names the statistic the reported +/- is",
            note="quoted from the project's own documentation",
        ),
        documented_selection=attest(
            selections,
            readme_rel,
            absent_note=f"no sentence of {readme_rel} says which observation of a run it published",
            note="quoted from the project's own documentation",
        ),
    )


__all__ = [
    "CELL_SEPARATORS",
    "README_NAMES",
    "SELECTION_TERMS",
    "SPREAD_TERMS",
    "STD_CALL",
    "Attributed",
    "ProseClaim",
    "SpreadExpression",
    "StatisticClaims",
    "attest",
    "collect_claims",
    "find_line",
    "prose_claims",
    "read_lines",
    "readme_of",
    "spread_expressions",
]
