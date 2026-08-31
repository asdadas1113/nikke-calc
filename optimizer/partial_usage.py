"""Positive-only usage evidence from incomplete public ranking surfaces.

Some public Solo Raid pages expose a scoped usage table (for example only
"Advantage Nikkes") without proving that omitted characters have zero usage or
that the displayed percentage denominator equals the full ranked-player pool.
Such data must never be normalized into ``EnikkSeasonUsageSnapshot`` because that
snapshot can support exact zero evidence when row coverage is complete.

This module therefore represents only *positive observations*. A row with 0%
cannot be constructed, and absence from a surface remains unknown. The only
integration helper copies existing ``SoloRaidUsageEvidence`` classifications and
optionally marks an observed character as recent/niche evidence for reversible
Cold restoration/exploration ordering. It never changes LOW/USED/INSUFFICIENT and
never modifies Moris scores.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from math import isfinite

from .cold_pool import SoloRaidUsageEvidence


class PartialUsageScope(str, Enum):
    """Known scope of a positive-only public usage surface."""

    ADVANTAGE_ONLY = "advantage_only"
    PARTIAL_POSITIVE = "partial_positive"


@dataclass(frozen=True)
class PartialPositiveUsageObservation:
    character: str
    raid: int
    usage_fraction: float
    scope: PartialUsageScope
    source: str

    def __post_init__(self) -> None:
        if not self.character:
            raise ValueError("character must be non-empty")
        if self.raid <= 0:
            raise ValueError("raid must be positive")
        value = float(self.usage_fraction)
        if not isfinite(value) or not 0 < value <= 1:
            raise ValueError(
                "partial usage observations must be strictly positive; "
                "0% is not safe evidence on an incomplete surface"
            )
        if not self.source.strip():
            raise ValueError("partial usage source must be non-empty")


@dataclass(frozen=True)
class PartialPositiveUsageSurface:
    """One scoped page/table where only positive rows are trustworthy."""

    raid: int
    scope: PartialUsageScope
    source: str
    observations: tuple[PartialPositiveUsageObservation, ...]

    def __post_init__(self) -> None:
        if self.raid <= 0:
            raise ValueError("raid must be positive")
        if not self.source.strip():
            raise ValueError("partial usage surface source must be non-empty")
        names: set[str] = set()
        for row in self.observations:
            if row.raid != self.raid:
                raise ValueError("partial usage observation raid mismatch")
            if row.scope is not self.scope:
                raise ValueError("partial usage observation scope mismatch")
            if row.source != self.source:
                raise ValueError("partial usage observation source mismatch")
            if row.character in names:
                raise ValueError(f"duplicate partial usage character: {row.character}")
            names.add(row.character)

    @property
    def observed_characters(self) -> tuple[str, ...]:
        return tuple(row.character for row in self.observations)

    def get(self, character: str) -> PartialPositiveUsageObservation | None:
        name = str(character)
        return next((row for row in self.observations if row.character == name), None)

    def absence_is_zero_safe(self, character: str) -> bool:
        """Always false: omission from a partial surface proves nothing."""

        _ = character
        return False


def build_partial_positive_surface(
    raid: int,
    usage_by_character: Mapping[str, float],
    *,
    scope: PartialUsageScope,
    source: str,
) -> PartialPositiveUsageSurface:
    """Normalize already-mapped positive fractions without inventing omissions.

    Callers must map external labels/resource ids to canonical names before this
    boundary. No threshold, denominator inference, or zero filling happens here.
    """

    rows = tuple(
        PartialPositiveUsageObservation(
            character=str(character),
            raid=raid,
            usage_fraction=float(fraction),
            scope=scope,
            source=source,
        )
        for character, fraction in usage_by_character.items()
    )
    return PartialPositiveUsageSurface(
        raid=raid,
        scope=scope,
        source=source,
        observations=rows,
    )


def mark_recent_positive_usage(
    usage_by_character: Mapping[str, SoloRaidUsageEvidence],
    surfaces: Sequence[PartialPositiveUsageSurface],
) -> dict[str, SoloRaidUsageEvidence]:
    """Copy classifications exactly while tagging positive observations as recent.

    This helper is intentionally weak. It does not protect a character from Cold
    outright and does not reinterpret 0.3% (or any other fraction) as meaningful
    usage. It only supplies the existing lexicographic restoration/exploration
    tie-break with audited evidence that the character appeared in a public
    recent surface.
    """

    positive = {
        row.character
        for surface in surfaces
        for row in surface.observations
    }
    out: dict[str, SoloRaidUsageEvidence] = {}
    for name, evidence in usage_by_character.items():
        if evidence.character != name:
            raise ValueError(f"usage evidence key/name mismatch for {name}")
        out[name] = (
            replace(evidence, recent_evidence=True)
            if name in positive
            else evidence
        )
    return out
