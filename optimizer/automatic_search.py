"""Explicit automatic candidate discovery on top of the existing anytime search.

This controller removes the need for a caller to hand-enumerate roster-wide
candidate teams, but it does not hide search constants or introduce a second
score system. Every discovery width and placement policy is explicit, discovery
uses independent measured ProxyViews, and every winning squad still needs an
actual Moris score before exact allocation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .anytime import AnytimeSearchResult, CandidateDiscoveryContext, run_anytime_search_round
from .budget import SearchBudget
from .candidate_generation import (
    PartialTeamViability,
    all_permutation_placements,
    identity_placement,
)
from .discovery import MultiViewCandidateDiscovery, generate_multi_view_candidate_discovery
from .evaluator import MorisEvaluator
from .marginal import PositionPriority
from .refinement import PlacementResolver
from .seeds import CoreSeed, ExactCompSeed


class AutomaticPlacementMode(str, Enum):
    """How unordered generated memberships expose ordered Moris squads."""

    CANONICAL_ONLY = "canonical-only"
    ALL_PERMUTATIONS = "all-permutations"


@dataclass(frozen=True)
class AutomaticDiscoveryPolicy:
    """All cheap-discovery widths are caller-owned; there are no numeric defaults."""

    team_size: int
    single_team_beam_width: int
    single_team_global_limit: int
    single_team_per_core_limit: int
    allocation_team_beam_width: int
    allocation_team_options_per_state: int
    allocation_beam_width: int
    allocation_limit: int
    placement_mode: AutomaticPlacementMode

    def __post_init__(self) -> None:
        if self.team_size <= 0:
            raise ValueError("team_size must be positive")
        positive = {
            "single_team_beam_width": self.single_team_beam_width,
            "allocation_team_beam_width": self.allocation_team_beam_width,
            "allocation_team_options_per_state": self.allocation_team_options_per_state,
            "allocation_beam_width": self.allocation_beam_width,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        nonnegative = {
            "single_team_global_limit": self.single_team_global_limit,
            "single_team_per_core_limit": self.single_team_per_core_limit,
            "allocation_limit": self.allocation_limit,
        }
        for name, value in nonnegative.items():
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class AutomaticSearchResult:
    search: AnytimeSearchResult
    discovery: MultiViewCandidateDiscovery

    @property
    def total_score(self) -> float | None:
        return self.search.total_score


def _placement_expander(mode: AutomaticPlacementMode):
    if mode is AutomaticPlacementMode.CANONICAL_ONLY:
        return identity_placement
    if mode is AutomaticPlacementMode.ALL_PERMUTATIONS:
        return all_permutation_placements
    raise ValueError(f"unsupported placement mode: {mode}")


def _resolve_partial_viability(
    legal,
    explicit: PartialTeamViability | None,
    *,
    team_size: int,
) -> PartialTeamViability | None:
    """Use only an explicitly exposed hard-feasibility method when available.

    Automatic discovery may safely prune a partial membership only when the
    legality object itself exposes ``can_complete(partial, roster, team_size=...)``.
    We do not infer partial semantics from an arbitrary final-team callable.
    Caller-supplied ``partial_viable`` always wins so experiments can override the
    adapter explicitly.
    """

    if explicit is not None:
        return explicit
    can_complete = getattr(legal, "can_complete", None)
    if not callable(can_complete):
        return None

    def from_legal(partial: tuple[str, ...], available: tuple[str, ...]) -> bool:
        return bool(can_complete(partial, available, team_size=team_size))

    return from_legal


def run_automatic_anytime_search_round(
    evaluator: MorisEvaluator,
    *,
    budget: SearchBudget,
    roster: Sequence[str],
    reference_teams: Sequence[Sequence[str]],
    discovery_policy: AutomaticDiscoveryPolicy,
    positions_per_candidate: int,
    candidate_limit: int,
    team_count: int = 5,
    legal=None,
    partial_viable: PartialTeamViability | None = None,
    position_priority: PositionPriority | None = None,
    prior_candidates=(),
    refinement_incoming: Sequence[str] = (),
    refinement_positions: Sequence[int] | None = None,
    refinement_max_new: int = 0,
    placement_resolver: PlacementResolver | None = None,
    marginal_max_simulate_calls: int | None = None,
    proxy_view_limit_per_view: int | None = None,
    exact_seeds: Sequence[ExactCompSeed] = (),
    core_seeds: Sequence[CoreSeed] = (),
    seed_max_per_core: int = 1,
    seed_roster: Sequence[str] | None = None,
    seed_candidate_teams: Sequence[Sequence[str]] | None = None,
    evaluate_kwargs: dict | None = None,
) -> AutomaticSearchResult:
    """Run marginal -> multi-view discovery -> Moris -> exact allocation.

    Core seeds whose members are all inside the ordinary search roster become
    required-core discovery channels. A core crossing outside that roster is not
    assigned fake marginal values; it remains available only through the explicit
    seed-only candidate path supplied by ``seed_candidate_teams``.

    Generated core/allocation subchannels are internally rank-round-robin merged
    into one protected *category* before entering ``run_anytime_search_round``.
    This prevents a large number of protected subchannels from receiving N turns
    for every one ordinary proxy turn. No source gets a score bonus; only exposure
    under a tight Moris-call budget is made category-fair.

    Partial membership pruning remains hard-only. When ``partial_viable`` is not
    supplied, an object passed as ``legal`` may opt in by exposing a callable
    ``can_complete`` method. Ordinary legality functions have no inferred partial
    semantics and therefore keep the previous fail-open behavior.
    """

    names = tuple(str(name) for name in roster)
    if len(names) < discovery_policy.team_size * team_count:
        raise ValueError("search roster is too small for requested non-overlapping teams")
    roster_set = frozenset(names)
    required_cores = tuple(
        seed.members
        for seed in core_seeds
        if set(seed.members) <= roster_set
    )
    placement = _placement_expander(discovery_policy.placement_mode)
    resolved_partial_viable = _resolve_partial_viability(
        legal,
        partial_viable,
        team_size=discovery_policy.team_size,
    )
    holder: dict[str, MultiViewCandidateDiscovery] = {}

    def get_discovery(context: CandidateDiscoveryContext) -> MultiViewCandidateDiscovery:
        if "value" not in holder:
            holder["value"] = generate_multi_view_candidate_discovery(
                names,
                context.proxy_views,
                team_size=discovery_policy.team_size,
                team_count=team_count,
                single_team_beam_width=discovery_policy.single_team_beam_width,
                single_team_global_limit=discovery_policy.single_team_global_limit,
                required_cores=required_cores,
                single_team_per_core_limit=discovery_policy.single_team_per_core_limit,
                allocation_team_beam_width=discovery_policy.allocation_team_beam_width,
                allocation_team_options_per_state=discovery_policy.allocation_team_options_per_state,
                allocation_beam_width=discovery_policy.allocation_beam_width,
                allocation_limit=discovery_policy.allocation_limit,
                legal=legal,
                placement_expander=placement,
                partial_viable=resolved_partial_viable,
            )
        return holder["value"]

    def protected_category(context: CandidateDiscoveryContext):
        teams = get_discovery(context).protected_teams
        return (teams,) if teams else ()

    search = run_anytime_search_round(
        evaluator,
        budget=budget,
        roster=names,
        reference_teams=reference_teams,
        candidate_teams=(),
        candidate_builder=lambda context: get_discovery(context).ordinary_teams,
        protected_candidate_channel_builder=protected_category,
        positions_per_candidate=positions_per_candidate,
        candidate_limit=candidate_limit,
        team_count=team_count,
        legal=legal,
        position_priority=position_priority,
        prior_candidates=prior_candidates,
        refinement_incoming=refinement_incoming,
        refinement_positions=refinement_positions,
        refinement_max_new=refinement_max_new,
        placement_resolver=placement_resolver,
        marginal_max_simulate_calls=marginal_max_simulate_calls,
        proxy_view_limit_per_view=proxy_view_limit_per_view,
        exact_seeds=exact_seeds,
        core_seeds=core_seeds,
        seed_max_per_core=seed_max_per_core,
        seed_roster=seed_roster,
        seed_candidate_teams=seed_candidate_teams,
        evaluate_kwargs=evaluate_kwargs,
    )
    if "value" not in holder:
        raise RuntimeError("automatic discovery builder was not invoked")
    return AutomaticSearchResult(search=search, discovery=holder["value"])
