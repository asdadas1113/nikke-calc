"""Score-blind planner for bounded exploration of still-deferred Cold members.

Structural restoration answers only whether the active pool can form enough legal
team skeletons. Even after that succeeds, a small caller-owned exploration quota
may inspect Cold members to catch meta misses. This module chooses *where to look*
without predicting damage:

1. characters covering the scarcest currently active required role first;
2. then closeness to the already-supplied low-usage boundary;
3. then recent/boss-specific evidence;
4. then stable Cold input order.

The role supply is updated after every pick, so a bounded list naturally spreads
attention across scarce roles instead of repeatedly selecting the same role. No
Moris score, external ranker damage, or weighted strength score is used here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import inf

from .cold_pool import SoloRaidUsageEvidence, StructuralDemand


@dataclass(frozen=True)
class ColdExplorationPick:
    character: str
    scarce_role_slack: int | None
    boundary_distance: float | None
    niche_evidence: bool


@dataclass(frozen=True)
class ColdExplorationPlan:
    active_roster: tuple[str, ...]
    selected: tuple[ColdExplorationPick, ...]
    deferred: tuple[str, ...]

    @property
    def selected_characters(self) -> tuple[str, ...]:
        return tuple(row.character for row in self.selected)

    @property
    def search_roster(self) -> tuple[str, ...]:
        return self.active_roster + self.selected_characters


def plan_cold_exploration(
    active_roster: Sequence[str],
    remaining_cold: Sequence[str],
    usage_by_character: Mapping[str, SoloRaidUsageEvidence],
    roles_by_character: Mapping[str, Sequence[str]],
    demand: StructuralDemand,
    *,
    limit: int,
) -> ColdExplorationPlan:
    """Select a bounded Cold probe roster using only auditable search priors.

    ``limit`` is required caller policy. This function does not evaluate teams or
    promote selected characters; it only returns a temporary search roster. A
    caller may pass ``search_roster`` into a budgeted search round while retaining
    ``deferred`` as Cold. Strong/weak status is determined only after actual Moris
    evaluations.
    """

    if limit < 0:
        raise ValueError("limit must be non-negative")

    active = tuple(str(name) for name in active_roster)
    cold = tuple(str(name) for name in remaining_cold)
    if len(set(active)) != len(active):
        raise ValueError("active_roster members must be unique")
    if len(set(cold)) != len(cold):
        raise ValueError("remaining_cold members must be unique")
    overlap = set(active) & set(cold)
    if overlap:
        raise ValueError(f"active and Cold rosters must be disjoint: {sorted(overlap)}")

    required = set(demand.required_roles)
    for name in active + cold:
        if name not in roles_by_character:
            raise ValueError(f"missing structural roles for {name}")

    role_supply = {
        role: sum(role in set(roles_by_character[name]) for name in active)
        for role in demand.required_roles
    }
    stable_index = {name: index for index, name in enumerate(cold)}
    remaining = list(cold)
    selected: list[ColdExplorationPick] = []

    while remaining and len(selected) < limit:
        def key(name: str) -> tuple[float, float, float, int]:
            roles = required & set(str(role) for role in roles_by_character[name])
            scarcity = (
                min(role_supply[role] - demand.team_count for role in roles)
                if roles
                else inf
            )
            usage = usage_by_character.get(name)
            if usage is not None and usage.character != name:
                raise ValueError(f"usage evidence key/name mismatch for {name}")
            boundary = (
                float(usage.boundary_distance)
                if usage is not None and usage.boundary_distance is not None
                else inf
            )
            niche_rank = 0.0 if usage is not None and usage.niche_evidence else 1.0
            return float(scarcity), boundary, niche_rank, stable_index[name]

        chosen = min(remaining, key=key)
        usage = usage_by_character.get(chosen)
        roles = required & set(str(role) for role in roles_by_character[chosen])
        scarcity = (
            min(role_supply[role] - demand.team_count for role in roles)
            if roles
            else None
        )
        selected.append(
            ColdExplorationPick(
                character=chosen,
                scarce_role_slack=scarcity,
                boundary_distance=(
                    None if usage is None else usage.boundary_distance
                ),
                niche_evidence=False if usage is None else usage.niche_evidence,
            )
        )
        for role in roles:
            role_supply[role] += 1
        remaining.remove(chosen)

    return ColdExplorationPlan(
        active_roster=active,
        selected=tuple(selected),
        deferred=tuple(remaining),
    )
