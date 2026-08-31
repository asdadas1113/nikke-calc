"""Meta-epoch-aware validity gate for external Solo Raid usage history.

This module does not decide whether a release, favorite item, balance change, or
bug fix is "large enough" to reset history. A caller supplies the latest
*confirmed history-resetting event* as ``MetaEpochEvidence``. The optimizer only
uses that evidence to decide which completed Solo Raid seasons are old enough to
be valid low-usage evidence.

A character must have been fully eligible from the start of a raid for that raid
to count after the epoch. Unknown/uncertain epoch provenance, incomplete raid
schedule provenance, too few completed post-epoch raids, or incomplete usage
snapshots all fail open to ``UsageClass.INSUFFICIENT``. This module never alters
Moris scores or hard legality.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import Enum
from math import isfinite

from .cold_pool import SoloRaidUsageEvidence, UsageClass
from .meta_usage import (
    CharacterUsageWindow,
    EnikkSeasonUsageSnapshot,
    aggregate_character_window,
)


class MetaEpochKnowledge(str, Enum):
    """Whether the latest history-resetting point is safe to use."""

    KNOWN = "known"
    UNKNOWN = "unknown"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class MetaEpochEvidence:
    """Latest confirmed point from which prior usage history becomes stale.

    ``valid_from`` is required only for KNOWN evidence. The event may be initial
    release or any later clearly material change supplied by an external policy.
    The optimizer intentionally does not infer materiality from patch text.
    """

    character: str
    knowledge: MetaEpochKnowledge
    valid_from: date | None
    source: str
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.character:
            raise ValueError("character must be non-empty")
        if not self.source.strip():
            raise ValueError("meta epoch source must be non-empty")
        if self.knowledge is MetaEpochKnowledge.KNOWN and self.valid_from is None:
            raise ValueError("KNOWN meta epoch requires valid_from")
        if self.knowledge is not MetaEpochKnowledge.KNOWN and self.valid_from is not None:
            raise ValueError("unknown/uncertain meta epoch must not invent valid_from")


@dataclass(frozen=True)
class SoloRaidPeriod:
    raid: int
    start_on: date
    end_on: date

    def __post_init__(self) -> None:
        if self.raid <= 0:
            raise ValueError("raid number must be positive")
        if self.end_on < self.start_on:
            raise ValueError("raid end date must not precede start date")


@dataclass(frozen=True)
class SoloRaidSchedule:
    """Date mapping used only to establish post-epoch season eligibility."""

    periods: tuple[SoloRaidPeriod, ...]
    complete: bool
    source: str

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("raid schedule source must be non-empty")
        raids = [period.raid for period in self.periods]
        if len(raids) != len(set(raids)):
            raise ValueError("raid schedule must not contain duplicate raid numbers")
        chronological = tuple(sorted(self.periods, key=lambda row: (row.start_on, row.raid)))
        if chronological != self.periods:
            raise ValueError("raid schedule periods must be chronological")


@dataclass(frozen=True)
class LowUsagePolicy:
    completed_seasons: int = 8
    max_peak_usage: float = 0.01

    def __post_init__(self) -> None:
        if self.completed_seasons <= 0:
            raise ValueError("completed_seasons must be positive")
        value = float(self.max_peak_usage)
        if not isfinite(value) or not 0 <= value <= 1:
            raise ValueError("max_peak_usage must be finite and between 0 and 1")


@dataclass(frozen=True)
class MetaUsageDecision:
    character: str
    classification: UsageClass
    reason: str
    eligible_post_epoch_raids: tuple[int, ...]
    inspected_raids: tuple[int, ...]
    window: CharacterUsageWindow | None
    epoch: MetaEpochEvidence
    schedule_source: str
    policy: LowUsagePolicy

    @property
    def boundary_distance(self) -> float | None:
        """Distance below the LOW boundary, only for complete LOW decisions.

        Smaller means closer to the boundary and is therefore suitable for the
        existing Cold-restoration tie-break. It remains ordering metadata only;
        it never changes damage or the LOW verdict itself.
        """

        if (
            self.classification is not UsageClass.LOW
            or self.window is None
            or self.window.peak_usage is None
        ):
            return None
        return max(0.0, self.policy.max_peak_usage - self.window.peak_usage)


def post_epoch_completed_raids(
    epoch: MetaEpochEvidence,
    schedule: SoloRaidSchedule,
    *,
    completed_through: date,
) -> tuple[int, ...]:
    """Return completed raids whose full participation window starts after epoch.

    This model intentionally stores dates rather than timestamps. Therefore an
    epoch on the same calendar day as a raid start is *not* enough to prove that
    the character/current version was available before the raid opened. Same-day
    cases are conservatively excluded and can only be recovered later by a
    timestamp-aware evidence model. Active/future raids whose end date is after
    ``completed_through`` are also excluded.
    """

    if epoch.knowledge is not MetaEpochKnowledge.KNOWN or epoch.valid_from is None:
        return ()
    return tuple(
        period.raid
        for period in schedule.periods
        if period.end_on <= completed_through and epoch.valid_from < period.start_on
    )


def classify_meta_epoch_usage(
    character: str,
    snapshots: Iterable[EnikkSeasonUsageSnapshot],
    *,
    epoch: MetaEpochEvidence,
    schedule: SoloRaidSchedule,
    completed_through: date,
    policy: LowUsagePolicy,
) -> MetaUsageDecision:
    """Classify usage only when a complete post-epoch evidence window exists.

    The latest ``policy.completed_seasons`` fully eligible completed raids are
    inspected. ``aggregate_character_window`` remains responsible for source-row
    completeness and name-mapping safety. Any uncertainty produces INSUFFICIENT,
    which the Cold pool already fails open to Primary.
    """

    name = str(character)
    if epoch.character != name:
        raise ValueError("meta epoch character does not match classification target")

    def decision(
        classification: UsageClass,
        reason: str,
        *,
        eligible: tuple[int, ...] = (),
        inspected: tuple[int, ...] = (),
        window: CharacterUsageWindow | None = None,
    ) -> MetaUsageDecision:
        return MetaUsageDecision(
            character=name,
            classification=classification,
            reason=reason,
            eligible_post_epoch_raids=eligible,
            inspected_raids=inspected,
            window=window,
            epoch=epoch,
            schedule_source=schedule.source,
            policy=policy,
        )

    if epoch.knowledge is not MetaEpochKnowledge.KNOWN:
        return decision(
            UsageClass.INSUFFICIENT,
            f"meta-epoch-{epoch.knowledge.value}-fail-open",
        )

    if not schedule.complete:
        return decision(
            UsageClass.INSUFFICIENT,
            "raid-schedule-incomplete-fail-open",
        )

    eligible = post_epoch_completed_raids(
        epoch,
        schedule,
        completed_through=completed_through,
    )
    if len(eligible) < policy.completed_seasons:
        return decision(
            UsageClass.INSUFFICIENT,
            "insufficient-completed-post-epoch-raids",
            eligible=eligible,
        )

    inspected = eligible[-policy.completed_seasons :]
    window = aggregate_character_window(
        name,
        snapshots,
        eligible_raids=inspected,
    )
    if not window.complete_for_requested_window or window.peak_usage is None:
        return decision(
            UsageClass.INSUFFICIENT,
            "usage-window-incomplete-fail-open",
            eligible=eligible,
            inspected=inspected,
            window=window,
        )

    if window.peak_usage <= policy.max_peak_usage:
        classification = UsageClass.LOW
        reason = "complete-post-epoch-window-below-peak-boundary"
    else:
        classification = UsageClass.USED
        reason = "post-epoch-window-has-meaningful-usage"

    return decision(
        classification,
        reason,
        eligible=eligible,
        inspected=inspected,
        window=window,
    )


def to_solo_raid_usage_evidence(
    decision: MetaUsageDecision,
    *,
    recent_evidence: bool = False,
    boss_specific_evidence: bool = False,
) -> SoloRaidUsageEvidence:
    """Adapt an audited meta-epoch decision into the existing Cold-pool input.

    The classification is copied exactly. No score or extra protection is added.
    Boundary distance is available only for complete LOW decisions and serves the
    Cold-restoration ordering already implemented in ``cold_pool.py``.
    """

    return SoloRaidUsageEvidence(
        character=decision.character,
        classification=decision.classification,
        boundary_distance=decision.boundary_distance,
        recent_evidence=recent_evidence,
        boss_specific_evidence=boss_specific_evidence,
    )
