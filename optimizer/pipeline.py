"""Explicit orchestration for evaluated candidates -> allocation -> one-swap refine.

This module adds no candidate-discovery heuristic.  Callers must provide the
initial candidate pool and, when refinement is enabled, the incoming-character
order/budget.  Its purpose is to make real-account benchmarking honest: every
candidate and refined neighbor is evaluated through the same MorisEvaluator,
then the existing exact candidate-pool allocator is run before and after refine.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from time import perf_counter

from .candidates import CandidateTeam
from .evaluator import MorisEvaluator
from .global_search import Allocation, select_global_allocation
from .refinement import OneSwapNeighbor, generate_one_swap_neighbors

Team = tuple[str, ...]
TeamValidator = Callable[[Team], bool]


@dataclass(frozen=True)
class PipelineStageMetrics:
    simulate_calls: int
    requests: int
    cache_hits: int
    simulate_s: float
    wall_s: float


@dataclass(frozen=True)
class AllocationRefinementResult:
    initial_candidates: tuple[CandidateTeam, ...]
    initial_allocation: Allocation | None
    refinement_neighbors: tuple[OneSwapNeighbor, ...]
    refined_candidates: tuple[CandidateTeam, ...]
    refined_allocation: Allocation | None
    candidate_stage: PipelineStageMetrics
    refinement_stage: PipelineStageMetrics

    @property
    def initial_total(self) -> float | None:
        return None if self.initial_allocation is None else self.initial_allocation.total_score

    @property
    def refined_total(self) -> float | None:
        return None if self.refined_allocation is None else self.refined_allocation.total_score

    @property
    def refine_gain(self) -> float | None:
        if self.initial_total is None or self.refined_total is None:
            return None
        return self.refined_total - self.initial_total

    @property
    def refine_gain_pct(self) -> float | None:
        gain = self.refine_gain
        if gain is None or self.initial_total in (None, 0):
            return None
        return gain / self.initial_total * 100.0


def _stage_delta(evaluator: MorisEvaluator, before: tuple[int, int, int, float], wall_s: float) -> PipelineStageMetrics:
    calls, requests, hits, simulate_s = before
    stats = evaluator.stats
    return PipelineStageMetrics(
        simulate_calls=stats.simulate_calls - calls,
        requests=stats.requests - requests,
        cache_hits=stats.cache_hits - hits,
        simulate_s=stats.simulate_s - simulate_s,
        wall_s=wall_s,
    )


def _snapshot_stats(evaluator: MorisEvaluator) -> tuple[int, int, int, float]:
    stats = evaluator.stats
    return stats.simulate_calls, stats.requests, stats.cache_hits, stats.simulate_s


def evaluate_allocation_with_one_swap_refinement(
    evaluator: MorisEvaluator,
    candidates: Iterable[CandidateTeam],
    *,
    team_count: int = 5,
    legal: TeamValidator | None = None,
    refinement_incoming: Sequence[str] = (),
    refinement_positions: Sequence[int] | None = None,
    refinement_max_new: int = 0,
    evaluate_kwargs: dict | None = None,
) -> AllocationRefinementResult:
    """Evaluate an explicit pool, allocate globally, then optionally one-swap refine.

    Initial `simulated_score` values are deliberately ignored and rebuilt through
    `evaluator`.  This prevents stale scores from another account snapshot/engine
    from entering the current allocation.

    Refinement has no implicit full-roster policy.  If `refinement_max_new` is
    positive, callers must explicitly provide `refinement_incoming` in the order
    they want examined.  Seeds are the teams in the current exact allocation;
    this is orchestration around the selected five-team solution, not a new
    proxy/search score.
    """

    if team_count <= 0:
        raise ValueError("team_count must be positive")
    if refinement_max_new < 0:
        raise ValueError("refinement_max_new must be non-negative")
    if refinement_max_new and not refinement_incoming:
        raise ValueError(
            "refinement_incoming must be explicit when refinement_max_new is positive"
        )

    source_pool = list(candidates)
    ordered_keys = [tuple(item.members) for item in source_pool]
    if len(ordered_keys) != len(set(ordered_keys)):
        raise ValueError("initial candidate ordered teams must be unique")
    if legal is not None:
        illegal = [team for team in ordered_keys if not legal(team)]
        if illegal:
            raise ValueError(f"initial candidate pool contains hard-illegal team: {illegal[0]}")

    kwargs = dict(evaluate_kwargs or {})
    before = _snapshot_stats(evaluator)
    start = perf_counter()
    evaluated: list[CandidateTeam] = []
    for item in source_pool:
        score = evaluator.evaluate(item.members, **kwargs).score
        evaluated.append(item.with_simulated_score(score))
    candidate_wall = perf_counter() - start
    candidate_stage = _stage_delta(evaluator, before, candidate_wall)

    initial_allocation = select_global_allocation(
        evaluated,
        team_count=team_count,
        require_simulated=True,
    )

    if initial_allocation is None or refinement_max_new == 0:
        return AllocationRefinementResult(
            initial_candidates=tuple(evaluated),
            initial_allocation=initial_allocation,
            refinement_neighbors=(),
            refined_candidates=(),
            refined_allocation=initial_allocation,
            candidate_stage=candidate_stage,
            refinement_stage=PipelineStageMetrics(0, 0, 0, 0.0, 0.0),
        )

    seen = tuple(item.members for item in evaluated)
    seeds = tuple(item.members for item in initial_allocation.teams)
    neighbors = generate_one_swap_neighbors(
        seeds,
        tuple(refinement_incoming),
        legal=legal,
        seen=seen,
        positions=refinement_positions,
        max_new=refinement_max_new,
    )

    before = _snapshot_stats(evaluator)
    start = perf_counter()
    refined: list[CandidateTeam] = []
    for neighbor in neighbors:
        score = evaluator.evaluate(neighbor.members, **kwargs).score
        refined.append(
            CandidateTeam(
                members=neighbor.members,
                proxy_score=0.0,
                simulated_score=score,
                source="one-swap-refine",
            )
        )
    refinement_wall = perf_counter() - start
    refinement_stage = _stage_delta(evaluator, before, refinement_wall)

    refined_allocation = select_global_allocation(
        [*evaluated, *refined],
        team_count=team_count,
        require_simulated=True,
    )
    return AllocationRefinementResult(
        initial_candidates=tuple(evaluated),
        initial_allocation=initial_allocation,
        refinement_neighbors=tuple(neighbors),
        refined_candidates=tuple(refined),
        refined_allocation=refined_allocation,
        candidate_stage=candidate_stage,
        refinement_stage=refinement_stage,
    )
