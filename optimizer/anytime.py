"""Budgeted orchestration over explicit candidate discovery inputs.

The caller may supply either a cheap candidate-team universe/order directly or a
``candidate_builder`` that constructs one after marginal evidence is measured.
This layer itself still does not prescribe a roster-wide generator or hidden
search constants. It spends a hard SearchBudget on candidate-specific marginals,
protected seed candidates, selected proxy teams, exact candidate-pool allocation,
and bounded one-swap refine.

A caller may feed ``prior_candidates`` from an earlier round back into a later
round. With the same MorisEvaluator/cache identity, those evaluations are cache
hits and remain in the candidate pool, so increasing the budget cannot discard a
previously found allocation merely because the proxy shortlist changed.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from .budget import BudgetedEvaluator, SearchBudget, SearchBudgetExhausted
from .candidates import CandidateTeam
from .evaluator import MorisEvaluator
from .global_search import Allocation, select_global_allocation
from .marginal import (
    MarginalMeasurement,
    PositionPriority,
    measure_planned_marginals_with_candidates,
    plan_candidate_specific_marginals,
)
from .proxy_views import (
    build_planned_marginal_prefix_views,
    select_proxy_view_candidates,
)
from .refinement import OneSwapNeighbor, PlacementResolver, generate_one_swap_neighbors
from .seeds import CoreSeed, ExactCompSeed, SeedSelection, select_seed_candidates

Team = tuple[str, ...]
TeamValidator = Callable[[Team], bool]
CandidateBuilder = Callable[[MarginalMeasurement], Iterable[Sequence[str]]]
CandidateRow = tuple[Team, float, str]


@dataclass(frozen=True)
class AnytimeStageMetrics:
    simulate_calls: int
    attempted_teams: int
    evaluated_teams: int


@dataclass(frozen=True)
class AnytimeSearchResult:
    """One budgeted search round plus all candidates safe to carry forward."""

    marginal_measurement: MarginalMeasurement
    proxy_selected: tuple[Team, ...]
    seed_selection: SeedSelection
    candidate_evaluation_order: tuple[Team, ...]
    refinement_neighbors: tuple[OneSwapNeighbor, ...]
    evaluated_candidates: tuple[CandidateTeam, ...]
    allocation_before_refine: Allocation | None
    allocation: Allocation | None
    marginal_stage: AnytimeStageMetrics
    candidate_stage: AnytimeStageMetrics
    refinement_stage: AnytimeStageMetrics
    budget_used: int
    budget_remaining: int

    @property
    def total_score(self) -> float | None:
        return None if self.allocation is None else self.allocation.total_score


def _merge_candidate(
    candidates: dict[Team, CandidateTeam],
    item: CandidateTeam,
) -> None:
    previous = candidates.get(item.members)
    if previous is None:
        candidates[item.members] = item
        return
    if previous.simulated_score is None and item.simulated_score is not None:
        candidates[item.members] = item


def _top_proxy_teams(
    candidate_teams: Iterable[Sequence[str]],
    marginal: MarginalMeasurement,
    *,
    limit: int,
    legal: TeamValidator | None,
) -> tuple[tuple[Team, float], ...]:
    if limit <= 0:
        return ()
    values = marginal.values
    heap: list[tuple[float, int, Team]] = []
    seen: set[Team] = set()
    for index, raw in enumerate(candidate_teams):
        team = tuple(raw)
        if team in seen:
            continue
        seen.add(team)
        if not team or len(set(team)) != len(team):
            continue
        if legal is not None and not legal(team):
            continue
        if any(name not in values for name in team):
            continue
        score = sum(values[name].mean_delta for name in team)
        row = (float(score), -index, team)
        if len(heap) < limit:
            heapq.heappush(heap, row)
        elif row[:2] > heap[0][:2]:
            heapq.heapreplace(heap, row)
    ranked = sorted(heap, key=lambda row: (row[0], row[1]), reverse=True)
    return tuple((team, score) for score, _neg_index, team in ranked)


def _interleave_candidate_channels(*channels: Sequence[CandidateRow]) -> tuple[CandidateRow, ...]:
    seen: set[Team] = set()
    out: list[CandidateRow] = []
    max_rank = max((len(channel) for channel in channels), default=0)
    for rank in range(max_rank):
        for channel in channels:
            if rank >= len(channel):
                continue
            row = channel[rank]
            if row[0] in seen:
                continue
            seen.add(row[0])
            out.append(row)
    return tuple(out)


def _stage_metrics(
    before_calls: int,
    attempted: int,
    evaluated: int,
    budgeted: BudgetedEvaluator,
) -> AnytimeStageMetrics:
    return AnytimeStageMetrics(
        simulate_calls=budgeted.used_simulate_calls - before_calls,
        attempted_teams=attempted,
        evaluated_teams=evaluated,
    )


def run_anytime_search_round(
    evaluator: MorisEvaluator,
    *,
    budget: SearchBudget,
    roster: Sequence[str],
    reference_teams: Iterable[Sequence[str]],
    candidate_teams: Iterable[Sequence[str]],
    positions_per_candidate: int,
    candidate_limit: int,
    team_count: int = 5,
    legal: TeamValidator | None = None,
    position_priority: PositionPriority | None = None,
    prior_candidates: Iterable[CandidateTeam] = (),
    refinement_incoming: Sequence[str] = (),
    refinement_positions: Sequence[int] | None = None,
    refinement_max_new: int = 0,
    placement_resolver: PlacementResolver | None = None,
    marginal_max_simulate_calls: int | None = None,
    proxy_view_limit_per_view: int | None = None,
    candidate_builder: CandidateBuilder | None = None,
    exact_seeds: Sequence[ExactCompSeed] = (),
    core_seeds: Sequence[CoreSeed] = (),
    seed_max_per_core: int = 1,
    seed_roster: Sequence[str] | None = None,
    seed_candidate_teams: Iterable[Sequence[str]] | None = None,
    evaluate_kwargs: dict | None = None,
) -> AnytimeSearchResult:
    """Spend one explicit simulate-call budget without hiding search constants.

    Stage order is marginal measurement, optional simulation-free candidate
    generation, seed/proxy candidate evaluation, exact allocation, optional
    bounded one-swap refinement, then exact allocation again.

    ``candidate_builder`` is optional. It receives the completed
    ``MarginalMeasurement`` and replaces ``candidate_teams`` for ordinary proxy
    discovery. It is outside the evaluator budget and must not call Moris; its
    widths and limits remain caller policy. Static ``candidate_teams`` remains the
    backward-compatible path.

    Seeds are discovery protection only. If CoreSeed reuses the ordinary universe
    while a candidate builder is active, it filters that builder output. Seed
    candidates receive no score bonus and final selection still depends only on
    actual Moris scores.
    """

    if team_count <= 0:
        raise ValueError("team_count must be positive")
    if candidate_limit < 0:
        raise ValueError("candidate_limit must be non-negative")
    if marginal_max_simulate_calls is not None and marginal_max_simulate_calls < 0:
        raise ValueError("marginal_max_simulate_calls must be non-negative")
    if proxy_view_limit_per_view is not None and proxy_view_limit_per_view < 0:
        raise ValueError("proxy_view_limit_per_view must be non-negative")
    if seed_max_per_core < 0:
        raise ValueError("seed_max_per_core must be non-negative")
    if refinement_max_new < 0:
        raise ValueError("refinement_max_new must be non-negative")
    if refinement_max_new and not refinement_incoming:
        raise ValueError(
            "refinement_incoming must be explicit when refinement_max_new is positive"
        )

    kwargs = dict(evaluate_kwargs or {})
    budgeted = BudgetedEvaluator(evaluator, budget)
    candidates: dict[Team, CandidateTeam] = {}

    for item in prior_candidates:
        team = tuple(item.members)
        if legal is not None and not legal(team):
            raise ValueError(f"prior candidate is hard-illegal: {team}")
        try:
            result = budgeted.evaluate(team, **kwargs)
        except SearchBudgetExhausted:
            continue
        _merge_candidate(
            candidates,
            CandidateTeam(
                members=team,
                proxy_score=item.proxy_score,
                simulated_score=result.score,
                source=item.source,
            ),
        )

    marginal_before = budgeted.used_simulate_calls
    plan = plan_candidate_specific_marginals(
        roster,
        reference_teams,
        positions_per_candidate=positions_per_candidate,
        legal=legal,
        position_priority=position_priority,
    )
    marginal_evaluator: MorisEvaluator | BudgetedEvaluator = budgeted
    if marginal_max_simulate_calls is not None:
        marginal_evaluator = BudgetedEvaluator(
            budgeted,
            SearchBudget(marginal_max_simulate_calls),
        )
    marginal = measure_planned_marginals_with_candidates(
        marginal_evaluator,
        plan,
        evaluate_kwargs=kwargs,
    )
    for item in marginal.evaluated_candidates:
        _merge_candidate(candidates, item)
    marginal_stage = AnytimeStageMetrics(
        simulate_calls=budgeted.used_simulate_calls - marginal_before,
        attempted_teams=len(plan.used_reference_teams) + plan.planned_probe_count,
        evaluated_teams=len(marginal.evaluated_candidates),
    )

    ordinary_source: Iterable[Sequence[str]] = (
        candidate_builder(marginal) if candidate_builder is not None else candidate_teams
    )
    candidate_source: Iterable[Sequence[str]]
    seed_candidate_source: Iterable[Sequence[str]]
    if core_seeds and seed_candidate_teams is None:
        shared = tuple(tuple(raw) for raw in ordinary_source)
        candidate_source = shared
        seed_candidate_source = shared
    else:
        candidate_source = ordinary_source
        seed_candidate_source = seed_candidate_teams or ()

    proxy_rows: tuple[CandidateRow, ...]
    if proxy_view_limit_per_view is None:
        proxy_rows = tuple(
            (team, score, "budgeted-proxy-top")
            for team, score in _top_proxy_teams(
                candidate_source,
                marginal,
                limit=candidate_limit,
                legal=legal,
            )
        )
    else:
        views = build_planned_marginal_prefix_views(plan, marginal)
        proxy_rows = tuple(
            (
                item.members,
                max(hit.score for hit in item.hits),
                "budgeted-proxy-views:" + ",".join(item.source_views),
            )
            for item in select_proxy_view_candidates(
                candidate_source,
                views,
                limit_per_view=proxy_view_limit_per_view,
                legal=legal,
            )
        )

    seed_selection = select_seed_candidates(
        seed_candidate_source if core_seeds else (),
        exact_seeds=exact_seeds,
        core_seeds=core_seeds,
        roster=roster if seed_roster is None else seed_roster,
        legal=legal,
        max_per_core=seed_max_per_core,
    )
    seed_rows: tuple[CandidateRow, ...] = tuple(
        (
            item.members,
            0.0,
            f"budgeted-seed:{item.seed_kind}:{item.seed_source}",
        )
        for item in seed_selection.candidates
    )
    selected = _interleave_candidate_channels(seed_rows, proxy_rows)

    candidate_before = budgeted.used_simulate_calls
    candidate_attempted = 0
    candidate_evaluated = 0
    for team, proxy_score, source in selected:
        candidate_attempted += 1
        try:
            result = budgeted.evaluate(team, **kwargs)
        except SearchBudgetExhausted:
            continue
        candidate_evaluated += 1
        _merge_candidate(
            candidates,
            CandidateTeam(
                members=team,
                proxy_score=proxy_score,
                simulated_score=result.score,
                source=source,
            ),
        )
    candidate_stage = _stage_metrics(
        candidate_before,
        candidate_attempted,
        candidate_evaluated,
        budgeted,
    )

    allocation_before = select_global_allocation(
        candidates.values(),
        team_count=team_count,
        require_simulated=True,
    )

    neighbors: list[OneSwapNeighbor] = []
    refinement_before = budgeted.used_simulate_calls
    refinement_attempted = 0
    refinement_evaluated = 0
    if allocation_before is not None and refinement_max_new:
        seeds = tuple(item.members for item in allocation_before.teams)
        neighbors = generate_one_swap_neighbors(
            seeds,
            tuple(refinement_incoming),
            legal=legal,
            seen=tuple(candidates),
            positions=refinement_positions,
            placement_resolver=placement_resolver,
            max_new=refinement_max_new,
        )
        for neighbor in neighbors:
            refinement_attempted += 1
            try:
                result = budgeted.evaluate(neighbor.members, **kwargs)
            except SearchBudgetExhausted:
                continue
            refinement_evaluated += 1
            _merge_candidate(
                candidates,
                CandidateTeam(
                    members=neighbor.members,
                    proxy_score=0.0,
                    simulated_score=result.score,
                    source="budgeted-one-swap",
                ),
            )
    refinement_stage = _stage_metrics(
        refinement_before,
        refinement_attempted,
        refinement_evaluated,
        budgeted,
    )

    allocation = select_global_allocation(
        candidates.values(),
        team_count=team_count,
        require_simulated=True,
    )
    return AnytimeSearchResult(
        marginal_measurement=marginal,
        proxy_selected=tuple(team for team, _score, _source in proxy_rows),
        seed_selection=seed_selection,
        candidate_evaluation_order=tuple(team for team, _score, _source in selected),
        refinement_neighbors=tuple(neighbors),
        evaluated_candidates=tuple(candidates.values()),
        allocation_before_refine=allocation_before,
        allocation=allocation,
        marginal_stage=marginal_stage,
        candidate_stage=candidate_stage,
        refinement_stage=refinement_stage,
        budget_used=budgeted.used_simulate_calls,
        budget_remaining=budgeted.remaining_simulate_calls,
    )