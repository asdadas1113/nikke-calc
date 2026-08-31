"""Compose score-neutral candidate generation without collapsing proxy views.

A previous failure study showed that first-probe and deeper marginal evidence can
prefer different useful teams. Automatic candidate generation must not undo that
by folding everything back into one universal scalar before the candidate pool
exists. Each complete ProxyView therefore receives its own bounded discovery
bundle; only the resulting candidate identities are unioned.

This module contains no search defaults. Beam widths, limits, core coverage,
allocation width, and placement policy are all caller-owned.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .candidate_generation import (
    AllocationCandidateGenerationResult,
    CandidateGenerationResult,
    PartialTeamViability,
    PlacementExpander,
    Team,
    TeamValidator,
    generate_additive_allocation_beam_candidates,
    generate_additive_beam_candidates,
)
from .proxy_views import ProxyView


def _interleave_team_channels(channels: Sequence[Sequence[Team]]) -> tuple[Team, ...]:
    """Rank-round-robin ordered-team channels while deduplicating identities."""

    seen: set[Team] = set()
    out: list[Team] = []
    max_rank = max((len(channel) for channel in channels), default=0)
    for rank in range(max_rank):
        for channel in channels:
            if rank >= len(channel):
                continue
            team = channel[rank]
            if team in seen:
                continue
            seen.add(team)
            out.append(team)
    return tuple(out)


@dataclass(frozen=True)
class CandidateDiscoveryBundle:
    ordinary: CandidateGenerationResult
    allocation: AllocationCandidateGenerationResult

    @property
    def ordinary_teams(self) -> tuple[Team, ...]:
        return self.ordinary.teams

    @property
    def core_channels(self) -> tuple[tuple[Team, ...], ...]:
        """Group generated core completions by the exact required-member relation."""

        order: list[tuple[str, ...]] = []
        grouped: dict[tuple[str, ...], list[Team]] = {}
        for row in self.ordinary.candidates:
            if not row.required_members:
                continue
            key = tuple(row.required_members)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(row.members)
        return tuple(tuple(grouped[key]) for key in order)

    @property
    def allocation_channels(self) -> tuple[tuple[Team, ...], ...]:
        return tuple(
            tuple(row.members for row in channel)
            for channel in self.allocation.candidate_channels
        )

    @property
    def protected_channels(self) -> tuple[tuple[Team, ...], ...]:
        return self.core_channels + self.allocation_channels

    @property
    def protected_teams(self) -> tuple[Team, ...]:
        """Fair stream inside this bundle's protected category."""

        return _interleave_team_channels(self.protected_channels)


@dataclass(frozen=True)
class SkippedDiscoveryView:
    name: str
    missing_members: tuple[str, ...]


@dataclass(frozen=True)
class MultiViewCandidateDiscovery:
    """Independent discovery bundles plus fair identity-level unions."""

    bundles: tuple[tuple[str, CandidateDiscoveryBundle], ...]
    skipped_views: tuple[SkippedDiscoveryView, ...]

    @property
    def source_views(self) -> tuple[str, ...]:
        return tuple(name for name, _bundle in self.bundles)

    @property
    def ordinary_teams(self) -> tuple[Team, ...]:
        """Rank-round-robin ordinary candidates across independent views."""

        channels = [bundle.ordinary_teams for _name, bundle in self.bundles]
        return _interleave_team_channels(channels)

    @property
    def protected_channels(self) -> tuple[tuple[Team, ...], ...]:
        """Keep every view's bounded core/allocation channels independent."""

        return tuple(
            channel
            for _name, bundle in self.bundles
            for channel in bundle.protected_channels
        )

    @property
    def protected_teams(self) -> tuple[Team, ...]:
        """Collapse protected subchannels only after fair internal interleaving.

        ``run_anytime_search_round`` schedules top-level candidate channels with
        equal turns. Passing every protected subchannel separately would give the
        protected category N turns for every one seed/proxy turn when N is large.
        Automatic search therefore passes this single internally-fair stream as
        one top-level protected category.
        """

        return _interleave_team_channels(self.protected_channels)


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
    partial_viable: PartialTeamViability | None = None,
) -> CandidateDiscoveryBundle:
    """Build ordinary and protected coverage from exactly one proxy mapping."""

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
        partial_viable=partial_viable,
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
        partial_viable=partial_viable,
    )
    return CandidateDiscoveryBundle(ordinary=ordinary, allocation=allocation)


def generate_multi_view_candidate_discovery(
    roster: Sequence[str],
    views: Sequence[ProxyView],
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
    partial_viable: PartialTeamViability | None = None,
) -> MultiViewCandidateDiscovery:
    """Run the same bounded discovery policy independently for every full view.

    A view missing even one member of the discovery roster is skipped rather than
    assigning that member a zero/default proxy. At least one complete view is
    required; otherwise automatic generation must stop and the caller can spend
    more marginal budget, broaden references, or use an explicit candidate plan.
    """

    names = tuple(str(name) for name in roster)
    if not names or len(set(names)) != len(names):
        raise ValueError("roster must contain unique members")
    if not views:
        raise ValueError("automatic multi-view discovery requires at least one proxy view")
    view_names = tuple(view.name for view in views)
    if len(set(view_names)) != len(view_names):
        raise ValueError("proxy view names must be unique")

    bundles: list[tuple[str, CandidateDiscoveryBundle]] = []
    skipped: list[SkippedDiscoveryView] = []
    for view in views:
        missing = tuple(name for name in names if name not in view.values)
        if missing:
            skipped.append(SkippedDiscoveryView(view.name, missing))
            continue
        bundles.append(
            (
                view.name,
                generate_candidate_discovery_bundle(
                    names,
                    view.values,
                    team_size=team_size,
                    team_count=team_count,
                    single_team_beam_width=single_team_beam_width,
                    single_team_global_limit=single_team_global_limit,
                    required_cores=required_cores,
                    single_team_per_core_limit=single_team_per_core_limit,
                    allocation_team_beam_width=allocation_team_beam_width,
                    allocation_team_options_per_state=allocation_team_options_per_state,
                    allocation_beam_width=allocation_beam_width,
                    allocation_limit=allocation_limit,
                    legal=legal,
                    placement_expander=placement_expander,
                    partial_viable=partial_viable,
                ),
            )
        )

    if not bundles:
        detail = "; ".join(
            f"{row.name}: missing {row.missing_members}" for row in skipped
        )
        raise ValueError(
            "no proxy view covers the full discovery roster"
            + (f" ({detail})" if detail else "")
        )
    return MultiViewCandidateDiscovery(
        bundles=tuple(bundles),
        skipped_views=tuple(skipped),
    )
