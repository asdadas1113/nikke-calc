"""Reversible Cold-pool wiring for certified bounded Solo Raid usage evidence.

This module mirrors ``meta_policy`` but requires
``CertifiedEnikkSeasonUsageSnapshot`` inputs and the conservative bounded
classifier.  Keeping the path explicit prevents legacy/descriptive ranking
snapshots from accidentally becoming production zero-usage evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from .cold_exploration import plan_cold_exploration
from .cold_pool import (
    OverloadPieceEvidence,  # type: ignore[attr-defined]
)
from .cold_pool import (
    StructuralDemand,
    partition_meta_guided_roster,
    restore_cold_until_feasible,
)
from .meta_eligibility import (
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    SoloRaidSchedule,
    to_solo_raid_usage_evidence,
)
from .meta_eligibility_bounds import classify_meta_epoch_usage_bounded
from .meta_policy import (
    MetaGuidedPartitionResult,
    MetaUsageRosterResult,
    PreparedMetaGuidedRoster,
    PreparedMetaGuidedSearchRoster,
)
from .meta_usage_bounds import CertifiedEnikkSeasonUsageSnapshot
from .overload import OverloadPieceEvidence


def classify_roster_meta_usage_bounded(
    roster: Sequence[str],
    snapshots: Sequence[CertifiedEnikkSeasonUsageSnapshot],
    epochs_by_character: Mapping[str, MetaEpochEvidence],
    *,
    schedule: SoloRaidSchedule,
    completed_through: date,
    policy: LowUsagePolicy,
) -> MetaUsageRosterResult:
    names = tuple(str(name) for name in roster)
    if len(set(names)) != len(names):
        raise ValueError("roster members must be unique")

    decisions = []
    usage = {}
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

        decision = classify_meta_epoch_usage_bounded(
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


def build_meta_guided_partition_bounded(
    roster: Sequence[str],
    snapshots: Sequence[CertifiedEnikkSeasonUsageSnapshot],
    epochs_by_character: Mapping[str, MetaEpochEvidence],
    overload_by_character: Mapping[str, OverloadPieceEvidence],
    *,
    schedule: SoloRaidSchedule,
    completed_through: date,
    policy: LowUsagePolicy,
    protected_names: Sequence[str] = (),
) -> MetaGuidedPartitionResult:
    classified = classify_roster_meta_usage_bounded(
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


def prepare_meta_guided_roster_bounded(
    roster: Sequence[str],
    snapshots: Sequence[CertifiedEnikkSeasonUsageSnapshot],
    epochs_by_character: Mapping[str, MetaEpochEvidence],
    overload_by_character: Mapping[str, OverloadPieceEvidence],
    roles_by_character: Mapping[str, Sequence[str]],
    demand: StructuralDemand,
    *,
    schedule: SoloRaidSchedule,
    completed_through: date,
    policy: LowUsagePolicy,
    restoration_batch_size: int,
    protected_names: Sequence[str] = (),
) -> PreparedMetaGuidedRoster:
    built = build_meta_guided_partition_bounded(
        roster,
        snapshots,
        epochs_by_character,
        overload_by_character,
        schedule=schedule,
        completed_through=completed_through,
        policy=policy,
        protected_names=protected_names,
    )
    restoration = restore_cold_until_feasible(
        built.partition,
        built.usage.usage_by_character,
        roles_by_character,
        demand,
        batch_size=restoration_batch_size,
    )
    return PreparedMetaGuidedRoster(
        usage=built.usage,
        initial_partition=built.partition,
        restoration=restoration,
    )


def prepare_meta_guided_search_roster_bounded(
    roster: Sequence[str],
    snapshots: Sequence[CertifiedEnikkSeasonUsageSnapshot],
    epochs_by_character: Mapping[str, MetaEpochEvidence],
    overload_by_character: Mapping[str, OverloadPieceEvidence],
    roles_by_character: Mapping[str, Sequence[str]],
    demand: StructuralDemand,
    *,
    schedule: SoloRaidSchedule,
    completed_through: date,
    policy: LowUsagePolicy,
    restoration_batch_size: int,
    cold_exploration_limit: int,
    protected_names: Sequence[str] = (),
) -> PreparedMetaGuidedSearchRoster:
    prepared = prepare_meta_guided_roster_bounded(
        roster,
        snapshots,
        epochs_by_character,
        overload_by_character,
        roles_by_character,
        demand,
        schedule=schedule,
        completed_through=completed_through,
        policy=policy,
        restoration_batch_size=restoration_batch_size,
        protected_names=protected_names,
    )
    exploration = plan_cold_exploration(
        prepared.active_roster,
        prepared.remaining_cold,
        prepared.usage.usage_by_character,
        roles_by_character,
        demand,
        limit=cold_exploration_limit,
    )
    return PreparedMetaGuidedSearchRoster(
        prepared=prepared,
        exploration=exploration,
    )
