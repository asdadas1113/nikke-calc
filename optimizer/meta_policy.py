"""Explicit policy wiring from meta-epoch usage evidence into the Cold pool.

The lower-level modules deliberately stay separate:

- ``meta_usage`` normalizes external season observations without thresholds;
- ``meta_eligibility`` decides whether a complete post-epoch window exists and
  applies an explicit low-usage policy;
- ``overload`` proves whether account evidence shows zero/present/unknown OL;
- ``cold_pool`` partitions LOW + proven-OL0 characters reversibly and restores
  deferred characters only when structural feasibility requires it;
- ``cold_exploration`` gives a small caller-owned subset of still-Cold members a
  temporary search look without changing their classification.

This module only wires those audited inputs together. Missing meta-epoch evidence
is converted to UNKNOWN and therefore fails open to Primary. No Moris score is
modified and no hidden account-strength composite is introduced.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .cold_exploration import ColdExplorationPlan, plan_cold_exploration
from .cold_pool import (
    ColdPoolPartition,
    ColdRestorationResult,
    SoloRaidUsageEvidence,
    StructuralDemand,
    partition_meta_guided_roster,
    restore_cold_until_feasible,
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


@dataclass(frozen=True)
class PreparedMetaGuidedRoster:
    """Meta partition after only the restoration needed for legal team supply."""

    usage: MetaUsageRosterResult
    initial_partition: ColdPoolPartition
    restoration: ColdRestorationResult

    @property
    def active_roster(self) -> tuple[str, ...]:
        return self.restoration.primary

    @property
    def remaining_cold(self) -> tuple[str, ...]:
        return self.restoration.remaining_cold

    @property
    def restored(self) -> tuple[str, ...]:
        return self.restoration.restored

    @property
    def structurally_feasible(self) -> bool:
        return self.restoration.feasibility.feasible


@dataclass(frozen=True)
class PreparedMetaGuidedSearchRoster:
    """Structural preparation plus temporary bounded Cold exploration."""

    prepared: PreparedMetaGuidedRoster
    exploration: ColdExplorationPlan

    @property
    def search_roster(self) -> tuple[str, ...]:
        return self.exploration.search_roster

    @property
    def explored_cold(self) -> tuple[str, ...]:
        return self.exploration.selected_characters

    @property
    def still_deferred_cold(self) -> tuple[str, ...]:
        return self.exploration.deferred


def classify_roster_meta_usage(
    roster: Sequence[str],
    snapshots: Sequence[EnikkSeasonUsageSnapshot],
    epochs_by_character: Mapping[str, MetaEpochEvidence],
    *,
    schedule: SoloRaidSchedule,
    completed_through: date,
    policy: LowUsagePolicy,
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
    policy: LowUsagePolicy,
    protected_names: Sequence[str] = (),
) -> MetaGuidedPartitionResult:
    """Build the reversible Primary/Cold partition from explicit evidence.

    ``protected_names`` is the existing Priority-review/Force-include bypass.
    Seed probes should normally use the separate seed-only roster path in
    ``run_anytime_search_round`` rather than permanently adding every seed member
    here.
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


def prepare_meta_guided_roster(
    roster: Sequence[str],
    snapshots: Sequence[EnikkSeasonUsageSnapshot],
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
    """Partition, then restore only as much Cold roster as structure requires.

    This is deliberately a pre-search preparation step. It does not evaluate a
    squad, rank characters by Moris damage, or choose a Cold-exploration budget.
    If Primary is already structurally feasible, no Cold member is restored. If
    Primary is not feasible, the existing lexicographic restoration policy adds
    small batches until feasibility is recovered or Cold is exhausted.

    The low-usage policy and restoration batch size are required caller inputs so
    provisional benchmark values cannot silently become production defaults.

    A result that remains infeasible is returned as such instead of silently
    disabling the meta filter or inventing characters. The caller can then report
    insufficient roster structure or explicitly fall back to a broader policy.
    """

    built = build_meta_guided_partition(
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


def prepare_meta_guided_search_roster(
    roster: Sequence[str],
    snapshots: Sequence[EnikkSeasonUsageSnapshot],
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
    """Prepare the temporary roster that a Meta-guided search round may inspect.

    The first phase restores Cold only when structural legality requires it. The
    second phase gives at most ``cold_exploration_limit`` still-deferred members a
    temporary search look using ``plan_cold_exploration``. The original Cold
    classification is retained; exploration is not promotion and does not add a
    score bonus.

    Both numeric policy values are caller-owned so later Fast/Standard/Precise
    presets can be benchmarked instead of silently becoming primitive defaults.
    """

    prepared = prepare_meta_guided_roster(
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
