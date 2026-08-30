"""Explicit policy wiring from meta-epoch usage evidence into the Cold pool.

The lower-level modules deliberately stay separate:

- ``meta_usage`` normalizes external season observations without thresholds;
- ``meta_eligibility`` decides whether a complete post-epoch window exists and
  applies an explicit low-usage policy;
- ``overload`` proves whether account evidence shows zero/present/unknown OL;
- ``cold_pool`` partitions LOW + proven-OL0 characters reversibly.

This module only wires those audited inputs together. Missing meta-epoch evidence
is converted to UNKNOWN and therefore fails open to Primary. No Moris score is
modified and no hidden account-strength composite is introduced.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .cold_pool import (
    ColdPoolPartition,
    SoloRaidUsageEvidence,
    partition_meta_guided_roster,
)
from .meta_eligibility import (
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    MetaUsageDecision,
    SoloRaidSchedule,
    classify_meta_epoch_usage,
    to_solo_raid_usage_evidence,
)
from .meta_usage import EnikkSeasonUsageSnapshot
from .overload import OverloadPieceEvidence


@dataclass(frozen=True)
class MetaUsageRosterResult:
    decisions: tuple[MetaUsageDecision, ...]
    usage_by_character: Mapping[str, SoloRaidUsageEvidence]


@dataclass(frozen=True)
class MetaGuidedPartitionResult:
    usage: MetaUsageRosterResult
    partition: ColdPoolPartition


def classify_roster_meta_usage(
    roster: Sequence[str],
    snapshots: Sequence[EnikkSeasonUsageSnapshot],
    epochs_by_character: Mapping[str, MetaEpochEvidence],
    *,
    schedule: SoloRaidSchedule,
    completed_through: date,
    policy: LowUsagePolicy = LowUsagePolicy(),
) -> MetaUsageRosterResult:
    """Classify every owned character with missing epoch evidence failing open."""

    names = tuple(str(name) for name in roster)
    if len(set(names)) != len(names):
        raise ValueError("roster members must be unique")

    decisions: list[MetaUsageDecision] = []
    usage: dict[str, SoloRaidUsageEvidence] = {}
    for name in names:
        epoch = epochs_by_character.get(name)
        if epoch is None:
            epoch = MetaEpochEvidence(
                character=name,
                knowledge=MetaEpochKnowledge.UNKNOWN,
                valid_from=None,
                source="meta-epoch:missing",
                reason="no validated history-reset epoch supplied",
            )
        elif epoch.character != name:
            raise ValueError(f"meta epoch key/name mismatch for {name}")

        decision = classify_meta_epoch_usage(
            name,
            snapshots,
            epoch=epoch,
            schedule=schedule,
            completed_through=completed_through,
            policy=policy,
        )
        decisions.append(decision)
        usage[name] = to_solo_raid_usage_evidence(decision)

    return MetaUsageRosterResult(
        decisions=tuple(decisions),
        usage_by_character=usage,
    )


def build_meta_guided_partition(
    roster: Sequence[str],
    snapshots: Sequence[EnikkSeasonUsageSnapshot],
    epochs_by_character: Mapping[str, MetaEpochEvidence],
    overload_by_character: Mapping[str, OverloadPieceEvidence],
    *,
    schedule: SoloRaidSchedule,
    completed_through: date,
    policy: LowUsagePolicy = LowUsagePolicy(),
    protected_names: Sequence[str] = (),
) -> MetaGuidedPartitionResult:
    """Build the reversible Primary/Cold partition from explicit evidence.

    ``protected_names`` is the existing Priority-review/Force-include bypass. A
    later seed-aware controller may add temporary seed members to this list for a
    particular probe without permanently reclassifying those characters.
    """

    classified = classify_roster_meta_usage(
        roster,
        snapshots,
        epochs_by_character,
        schedule=schedule,
        completed_through=completed_through,
        policy=policy,
    )
    partition = partition_meta_guided_roster(
        roster,
        classified.usage_by_character,
        overload_by_character,
        protected_names=protected_names,
    )
    return MetaGuidedPartitionResult(usage=classified, partition=partition)
