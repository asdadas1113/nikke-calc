"""Reversible meta-guided cold-pool primitives.

External Solo Raid usage may decide which owned characters receive expensive
search budget first, but it must not alter Moris damage scores or hard legality.
This module therefore implements only auditable roster partitioning, cheap
structural feasibility, and incremental restoration.  Numeric usage thresholds,
exploration budgets, and promotion thresholds remain caller policy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from math import inf, isfinite
from typing import Protocol

from .overload import OverloadKnowledge, OverloadPieceEvidence


class UsageClass(str, Enum):
    """Coarse external-usage verdict; the rule producing it lives elsewhere."""

    USED = "used"
    LOW = "low"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class SoloRaidUsageEvidence:
    """Usage evidence already classified by a separately benchmarked policy.

    ``boundary_distance`` is optional and only orders already-cold characters:
    smaller means closer to the eventual low-usage boundary.  It does not decide
    whether usage is LOW.  Recent/boss-specific flags are similarly restoration
    evidence only and never modify Moris scores.
    """

    character: str
    classification: UsageClass
    boundary_distance: float | None = None
    recent_evidence: bool = False
    boss_specific_evidence: bool = False

    def __post_init__(self) -> None:
        if not self.character:
            raise ValueError("character must be non-empty")
        if self.boundary_distance is not None:
            value = float(self.boundary_distance)
            if not isfinite(value) or value < 0:
                raise ValueError("boundary_distance must be finite and non-negative")

    @property
    def niche_evidence(self) -> bool:
        return self.recent_evidence or self.boss_specific_evidence


@dataclass(frozen=True)
class ColdDecision:
    character: str
    pool: str
    reason: str


@dataclass(frozen=True)
class ColdPoolPartition:
    primary: tuple[str, ...]
    cold: tuple[str, ...]
    protected: tuple[str, ...]
    fail_open: tuple[str, ...]
    decisions: tuple[ColdDecision, ...]


class BurstInspector(Protocol):
    def inspect(self, members: Sequence[str]): ...


def partition_meta_guided_roster(
    roster: Sequence[str],
    usage_by_character: Mapping[str, SoloRaidUsageEvidence],
    overload_by_character: Mapping[str, OverloadPieceEvidence],
    *,
    protected_names: Sequence[str] = (),
) -> ColdPoolPartition:
    """Cold-defer only ``LOW usage AND proven Overload zero``.

    Missing/insufficient usage, missing Overload evidence, and unknown Overload
    state all stay Primary.  This is deliberately asymmetric: a false defer can
    erase a strong composition before Moris sees it, while a false keep only
    spends extra search budget.
    """

    names = tuple(str(name) for name in roster)
    if len(set(names)) != len(names):
        raise ValueError("roster members must be unique")
    protected_set = frozenset(str(name) for name in protected_names)
    unknown_protected = protected_set - set(names)
    if unknown_protected:
        raise ValueError(f"protected names are not in roster: {sorted(unknown_protected)}")

    primary: list[str] = []
    cold: list[str] = []
    protected: list[str] = []
    fail_open: list[str] = []
    decisions: list[ColdDecision] = []

    for name in names:
        if name in protected_set:
            primary.append(name)
            protected.append(name)
            decisions.append(ColdDecision(name, "primary", "explicit-user-protection"))
            continue

        usage = usage_by_character.get(name)
        if usage is None:
            primary.append(name)
            fail_open.append(name)
            decisions.append(ColdDecision(name, "primary", "usage-missing-fail-open"))
            continue
        if usage.character != name:
            raise ValueError(f"usage evidence key/name mismatch for {name}")
        if usage.classification is UsageClass.INSUFFICIENT:
            primary.append(name)
            fail_open.append(name)
            decisions.append(ColdDecision(name, "primary", "usage-insufficient-fail-open"))
            continue
        if usage.classification is UsageClass.USED:
            primary.append(name)
            decisions.append(ColdDecision(name, "primary", "meaningful-usage-protection"))
            continue

        overload = overload_by_character.get(name)
        if overload is None:
            primary.append(name)
            fail_open.append(name)
            decisions.append(ColdDecision(name, "primary", "overload-missing-fail-open"))
            continue
        if overload.character != name:
            raise ValueError(f"overload evidence key/name mismatch for {name}")
        if overload.knowledge is OverloadKnowledge.UNKNOWN:
            primary.append(name)
            fail_open.append(name)
            decisions.append(ColdDecision(name, "primary", "overload-unknown-fail-open"))
            continue
        if overload.knowledge is OverloadKnowledge.PRESENT:
            primary.append(name)
            decisions.append(ColdDecision(name, "primary", "overload-investment-protection"))
            continue

        # At this point usage is LOW and Overload zero is explicitly proven.
        if not overload.proven_zero:
            raise AssertionError("ZERO Overload knowledge must prove piece_count == 0")
        cold.append(name)
        decisions.append(ColdDecision(name, "cold", "low-usage-and-overload-zero"))

    return ColdPoolPartition(
        primary=tuple(primary),
        cold=tuple(cold),
        protected=tuple(protected),
        fail_open=tuple(fail_open),
        decisions=tuple(decisions),
    )


@dataclass(frozen=True)
class StructuralDemand:
    """Same role set required by every non-overlapping team."""

    team_count: int
    team_size: int
    required_roles: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.team_count <= 0:
            raise ValueError("team_count must be positive")
        if self.team_size <= 0:
            raise ValueError("team_size must be positive")
        if not self.required_roles:
            raise ValueError("required_roles must not be empty")
        if len(set(self.required_roles)) != len(self.required_roles):
            raise ValueError("required_roles must be unique")

    @property
    def required_members(self) -> int:
        return self.team_count * self.team_size

    @property
    def required_role_slots(self) -> int:
        return self.team_count * len(self.required_roles)


@dataclass(frozen=True)
class StructuralFeasibility:
    feasible: bool
    member_count: int
    required_members: int
    member_deficit: int
    complete_teams: int
    team_count: int
    covered_role_slots: int
    required_role_slots: int


@dataclass(frozen=True)
class RestorationStep:
    restored: tuple[str, ...]
    before: StructuralFeasibility
    after: StructuralFeasibility


@dataclass(frozen=True)
class ColdRestorationResult:
    primary: tuple[str, ...]
    remaining_cold: tuple[str, ...]
    restored: tuple[str, ...]
    steps: tuple[RestorationStep, ...]
    feasibility: StructuralFeasibility


State = tuple[tuple[int, int], ...]


def _role_masks(
    members: Sequence[str],
    roles_by_character: Mapping[str, Sequence[str]],
    required_roles: tuple[str, ...],
) -> tuple[int, ...]:
    bit = {role: 1 << index for index, role in enumerate(required_roles)}
    masks: list[int] = []
    for name in members:
        if name not in roles_by_character:
            raise ValueError(f"missing structural roles for {name}")
        mask = 0
        for role in roles_by_character[name]:
            if role in bit:
                mask |= bit[role]
        masks.append(mask)
    return tuple(masks)


def check_structural_feasibility(
    members: Sequence[str],
    roles_by_character: Mapping[str, Sequence[str]],
    demand: StructuralDemand,
) -> StructuralFeasibility:
    """Check whether the roster can be partitioned into role-complete teams.

    This dynamic program keeps teams symmetric and lets one character satisfy
    multiple required roles inside its one assigned team.  That matters for
    NIKKE burst-all characters: treating each role as consuming a distinct
    character would restore too aggressively.

    Role-bearing assignments never add a character to a team when it contributes
    no new role.  Remaining owned characters are interchangeable fillers, so the
    separate total-member check is sufficient to fill each team to ``team_size``.
    """

    names = tuple(str(name) for name in members)
    if len(set(names)) != len(names):
        raise ValueError("structural feasibility members must be unique")
    masks = _role_masks(names, roles_by_character, demand.required_roles)
    full_mask = (1 << len(demand.required_roles)) - 1
    initial: State = tuple((0, 0) for _ in range(demand.team_count))
    states: set[State] = {initial}

    for char_mask in masks:
        if char_mask == 0:
            continue
        next_states = set(states)
        for state in states:
            seen_team_states: set[tuple[int, int]] = set()
            for index, (team_mask, used) in enumerate(state):
                team_state = (team_mask, used)
                if team_state in seen_team_states:
                    continue
                seen_team_states.add(team_state)
                if used >= demand.team_size:
                    continue
                new_mask = team_mask | char_mask
                if new_mask == team_mask:
                    continue
                changed = list(state)
                changed[index] = (new_mask, used + 1)
                next_states.add(tuple(sorted(changed)))
        states = next_states

    def progress(state: State) -> tuple[int, int, int]:
        complete = sum(mask == full_mask for mask, _used in state)
        covered = sum(mask.bit_count() for mask, _used in state)
        used = sum(count for _mask, count in state)
        return complete, covered, -used

    best = max(states, key=progress)
    complete, covered, _negative_used = progress(best)
    roles_feasible = complete == demand.team_count
    member_deficit = max(0, demand.required_members - len(names))
    return StructuralFeasibility(
        feasible=roles_feasible and member_deficit == 0,
        member_count=len(names),
        required_members=demand.required_members,
        member_deficit=member_deficit,
        complete_teams=complete,
        team_count=demand.team_count,
        covered_role_slots=covered,
        required_role_slots=demand.required_role_slots,
    )


def build_burst_role_map(
    validator: BurstInspector,
    roster: Sequence[str],
) -> dict[str, frozenset[str]]:
    """Project the conservative BurstStructureValidator into role masks.

    Static eligible stages and runtime-possible ``uncertain_stages`` both count
    as possible roles.  This mirrors the existing hard-constraint policy: an
    uncertain dynamic stage is not safe to prune.  Explicit burst sequences are
    intentionally rejected here because their role semantics were already
    deferred to Moris rather than reimplemented by the optimizer.
    """

    out: dict[str, frozenset[str]] = {}
    for name in roster:
        report = validator.inspect((name,))
        if getattr(report, "deferred_reason", None):
            raise ValueError(
                "structural burst-role projection is unavailable when burst semantics are deferred"
            )
        eligible = getattr(report, "eligible_by_stage")
        roles = {
            str(stage)
            for stage, candidates in eligible.items()
            if str(name) in tuple(str(candidate) for candidate in candidates)
        }
        roles.update(str(stage) for stage in getattr(report, "uncertain_stages", ()))
        out[str(name)] = frozenset(roles)
    return out


def _restoration_key(
    name: str,
    *,
    active: tuple[str, ...],
    base: StructuralFeasibility,
    roles_by_character: Mapping[str, Sequence[str]],
    demand: StructuralDemand,
    usage_by_character: Mapping[str, SoloRaidUsageEvidence],
    stable_index: int,
) -> tuple[float, ...]:
    trial = check_structural_feasibility(active + (name,), roles_by_character, demand)
    complete_gain = trial.complete_teams - base.complete_teams
    coverage_gain = trial.covered_role_slots - base.covered_role_slots
    member_gain = base.member_deficit - trial.member_deficit
    usage = usage_by_character.get(name)
    boundary = (
        float(usage.boundary_distance)
        if usage is not None and usage.boundary_distance is not None
        else inf
    )
    niche_rank = 0.0 if usage is not None and usage.niche_evidence else 1.0
    return (
        -float(complete_gain),
        -float(coverage_gain),
        -float(member_gain),
        boundary,
        niche_rank,
        float(stable_index),
    )


def restore_cold_until_feasible(
    partition: ColdPoolPartition,
    usage_by_character: Mapping[str, SoloRaidUsageEvidence],
    roles_by_character: Mapping[str, Sequence[str]],
    demand: StructuralDemand,
    *,
    batch_size: int,
) -> ColdRestorationResult:
    """Restore a small ordered batch, recheck feasibility, and repeat.

    Restoration order is recomputed after every batch because the structural
    deficit changes as characters return.  The priority is deliberately simple:

    1. improvement in complete-team/role coverage;
    2. total-member deficit repair;
    3. closeness to the supplied usage boundary;
    4. presence of recent or boss-specific evidence;
    5. original Cold order.

    No weighted meta score is introduced here.  Exact evidence construction and
    ``batch_size`` remain caller-owned policy/benchmark choices.
    """

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    active = list(partition.primary)
    remaining = list(partition.cold)
    restored: list[str] = []
    steps: list[RestorationStep] = []
    current = check_structural_feasibility(active, roles_by_character, demand)

    while not current.feasible and remaining:
        active_tuple = tuple(active)
        indexed = list(enumerate(remaining))
        ranked = sorted(
            indexed,
            key=lambda row: _restoration_key(
                row[1],
                active=active_tuple,
                base=current,
                roles_by_character=roles_by_character,
                demand=demand,
                usage_by_character=usage_by_character,
                stable_index=row[0],
            ),
        )
        chosen = tuple(name for _index, name in ranked[:batch_size])
        before = current
        chosen_set = set(chosen)
        active.extend(chosen)
        restored.extend(chosen)
        remaining = [name for name in remaining if name not in chosen_set]
        current = check_structural_feasibility(active, roles_by_character, demand)
        steps.append(RestorationStep(chosen, before, current))

    return ColdRestorationResult(
        primary=tuple(active),
        remaining_cold=tuple(remaining),
        restored=tuple(restored),
        steps=tuple(steps),
        feasibility=current,
    )
