"""Compose score-neutral candidate-generation channels from one proxy snapshot.

This module deliberately contains no defaults. A caller chooses every beam width,
team limit, allocation width, and placement policy. The same character proxy map
feeds both the ordinary single-team universe and the protected non-overlap
allocation channels, avoiding separate hidden scoring systems.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .candidate_generation import (
    AllocationCandidateGenerationResult,
    CandidateGenerationResult,
    PlacementExpander,
    Team,
    TeamValidator,
    generate_additive_allocation_beam_candidates,
    generate_additive_beam_candidates,
)


@dataclass(frozen=True)
class CandidateDiscoveryBundle:
    ordinary: CandidateGenerationResult
    allocation: AllocationCandidateGenerationResult

    @property
    def ordinary_teams(self) -> tuple[Team, ...]:
        return self.ordinary.teams

    @property
    def protected_channels(self) -> tuple[tuple[Team, ...], ...]:
        return tuple(
            tuple(row.members for row in channel)
            for channel in self.allocation.candidate_channels
        )


def generate_candidate_discovery_bundle(
    roster: Sequence[str],
    score_by_character: Mapping[str, float],
    *,
    team_size: int,
    team_count: int,
    single_team_beam_width: int,
    single_team_global_limit: int,
    required_cores: Sequence[Sequence[str]],
    single_team_per_core_limit: int,
    allocation_team_beam_width: int,
    allocation_team_options_per_state: int,
    allocation_beam_width: int,
    allocation_limit: int,
    legal: TeamValidator | None = None,
    placement_expander: PlacementExpander | None = None,
) -> CandidateDiscoveryBundle:
    """Build ordinary and multi-team coverage from exactly one proxy mapping.

    ``ordinary`` feeds the usual proxy Top-K/multi-view selector. ``allocation``
    supplies separate protected channels so a cheap non-overlap path is not erased
    merely because one of its squads ranks below the strongest overlapping single
    teams. Neither channel changes actual Moris scores.
    """

    ordinary = generate_additive_beam_candidates(
        roster,
        score_by_character,
        team_size=team_size,
        beam_width=single_team_beam_width,
        global_limit=single_team_global_limit,
        required_cores=required_cores,
        per_core_limit=single_team_per_core_limit,
        legal=legal,
        placement_expander=placement_expander,
    )
    allocation = generate_additive_allocation_beam_candidates(
        roster,
        score_by_character,
        team_size=team_size,
        team_count=team_count,
        team_beam_width=allocation_team_beam_width,
        team_options_per_state=allocation_team_options_per_state,
        allocation_beam_width=allocation_beam_width,
        allocation_limit=allocation_limit,
        legal=legal,
        placement_expander=placement_expander,
    )
    return CandidateDiscoveryBundle(ordinary=ordinary, allocation=allocation)
