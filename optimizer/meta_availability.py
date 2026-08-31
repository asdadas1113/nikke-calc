"""Conservative availability evidence from first positive Solo Raid observation.

This module exists for one narrow problem: historical ranking archives may not
carry an authoritative character release date. A positive mapped appearance can
prove that the character existed by that raid, but it cannot prove that the
character was available from the raid's first day.

Therefore the derived availability floor begins *after* the observed raid ends.
It is intentionally weaker than ``MetaEpochEvidence``: first-positive evidence
cannot prove that no later favorite-item/skill/balance change reset usage history.
Production Cold classification must still require an independently validated
meta epoch. This evidence is diagnostic/eligibility provenance only and never
alters Moris scores.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from .meta_eligibility import SoloRaidSchedule
from .meta_usage import EnikkSeasonUsageSnapshot


class AvailabilityKnowledge(str, Enum):
    """Whether a conservative post-observation availability floor is usable."""

    KNOWN = "known"
    UNKNOWN = "unknown"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class FirstPositiveAvailability:
    """Earliest mapped positive observation and the conservative next-day floor."""

    character: str
    knowledge: AvailabilityKnowledge
    first_positive_raid: int | None
    valid_from: date | None
    source: str
    reason: str

    def __post_init__(self) -> None:
        if not self.character:
            raise ValueError("character must be non-empty")
        if not self.source.strip():
            raise ValueError("availability source must be non-empty")
        known = self.knowledge is AvailabilityKnowledge.KNOWN
        if known and (self.first_positive_raid is None or self.valid_from is None):
            raise ValueError("KNOWN availability requires raid and valid_from")
        if not known and (self.first_positive_raid is not None or self.valid_from is not None):
            raise ValueError("unknown/uncertain availability must not invent dates")


def derive_first_positive_availability(
    character: str,
    snapshots: Iterable[EnikkSeasonUsageSnapshot],
    schedule: SoloRaidSchedule,
    *,
    source: str = "external-usage:first-positive",
) -> FirstPositiveAvailability:
    """Derive a conservative availability floor without inventing release dates.

    Positive usage remains evidence even when some ranking rows are incomplete;
    only zero usage needs complete row coverage. The character must still be in
    the snapshot's mapped-character catalog so an ambiguous external label cannot
    become release evidence.

    The first positive raid itself is deliberately excluded from future complete-
    season counting by setting ``valid_from`` to one day after that raid ends.
    If the schedule is incomplete, the observed raid is absent from the schedule,
    or no mapped positive observation exists, the result is non-KNOWN and must
    not be used to unlock low-usage pruning.
    """

    name = str(character)
    if not name:
        raise ValueError("character must be non-empty")
    if not schedule.complete:
        return FirstPositiveAvailability(
            name,
            AvailabilityKnowledge.UNCERTAIN,
            None,
            None,
            source,
            "raid schedule is incomplete; first-positive timing cannot be audited",
        )

    periods = {period.raid: period for period in schedule.periods}
    chronological_raids = {period.raid: index for index, period in enumerate(schedule.periods)}
    positives: list[tuple[int, int]] = []
    for snapshot in snapshots:
        observation = snapshot.observe(name)
        if (
            observation.source_character_known
            and observation.player_count > 0
            and observation.player_appearances > 0
        ):
            order = chronological_raids.get(snapshot.raid)
            if order is None:
                return FirstPositiveAvailability(
                    name,
                    AvailabilityKnowledge.UNCERTAIN,
                    None,
                    None,
                    source,
                    f"positive raid S{snapshot.raid} is absent from the trusted schedule",
                )
            positives.append((order, snapshot.raid))

    if not positives:
        return FirstPositiveAvailability(
            name,
            AvailabilityKnowledge.UNKNOWN,
            None,
            None,
            source,
            "no mapped positive Solo Raid observation proves historical availability",
        )

    _order, raid = min(positives)
    period = periods[raid]
    return FirstPositiveAvailability(
        name,
        AvailabilityKnowledge.KNOWN,
        raid,
        period.end_on + timedelta(days=1),
        source,
        (
            f"first mapped positive usage is S{raid}; that season is excluded because "
            "the observation does not prove availability from raid start"
        ),
    )


def completed_raids_after_first_positive(
    availability: FirstPositiveAvailability,
    schedule: SoloRaidSchedule,
    *,
    completed_through: date,
) -> tuple[int, ...]:
    """Return completed raids safely known to start after first-positive evidence.

    This helper is for provenance/backtest eligibility only. It must not be fed
    into production Cold classification as a substitute for ``MetaEpochEvidence``.
    UNKNOWN/UNCERTAIN availability or an incomplete schedule returns no eligible
    raids rather than guessing.
    """

    if (
        availability.knowledge is not AvailabilityKnowledge.KNOWN
        or availability.valid_from is None
        or not schedule.complete
    ):
        return ()
    return tuple(
        period.raid
        for period in schedule.periods
        if period.end_on <= completed_through and availability.valid_from <= period.start_on
    )


def derive_roster_first_positive_availability(
    roster: Sequence[str],
    snapshots: Sequence[EnikkSeasonUsageSnapshot],
    schedule: SoloRaidSchedule,
    *,
    source: str = "external-usage:first-positive",
) -> Mapping[str, FirstPositiveAvailability]:
    """Derive the same conservative evidence for every unique roster member."""

    names = tuple(str(name) for name in roster)
    if len(set(names)) != len(names):
        raise ValueError("roster members must be unique")
    return {
        name: derive_first_positive_availability(
            name,
            snapshots,
            schedule,
            source=source,
        )
        for name in names
    }
