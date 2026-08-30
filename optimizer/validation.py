"""Small exhaustive ground-truth harness for optimizer experiments.

This module is intentionally evaluator-agnostic. Synthetic score functions keep
regression tests cheap; a later Moris experiment can pass separate ground-truth
and optimizer evaluators plus their simulate-call counters.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations
from time import perf_counter
from typing import Callable, Iterable, Sequence

from .candidates import CandidateTeam
from .constraints import ConstraintSet
from .global_search import select_global_allocation

ScoreFn = Callable[[tuple[str, ...]], float]
CandidateSelector = Callable[[Sequence[CandidateTeam]], Sequence[CandidateTeam]]
CallCounter = Callable[[], int]


@dataclass(frozen=True)
class ValidationMetrics:
    legal_team_count: int
    candidate_count: int
    exhaustive_evaluator_calls: int
    optimizer_evaluator_calls: int
    true_optimum_survival: float
    top_n_recall: float
    exhaustive_optimum: float
    final_score: float
    final_to_optimum: float
    exhaustive_runtime_s: float
    optimizer_runtime_s: float


def enumerate_legal_teams(
    roster: Sequence[str],
    constraints: ConstraintSet,
    *,
    ordered: bool = True,
) -> list[tuple[str, ...]]:
    """Enumerate a tiny legal team space for ground-truth experiments.

    Ordered enumeration is the default because NIKKE placement/order can affect
    burst priority and operation. Use ``ordered=False`` only for synthetic cases
    whose score is explicitly order-independent.
    """
    names = tuple(roster)
    if len(set(names)) != len(names):
        raise ValueError("roster members must be unique")

    if ordered:
        generated = permutations(names, constraints.team_size)
    else:
        generated = combinations(names, constraints.team_size)
    return [tuple(team) for team in generated if constraints.validate_team(team)]


def _unique_candidates(items: Iterable[CandidateTeam]) -> list[CandidateTeam]:
    seen: set[tuple[str, ...]] = set()
    out: list[CandidateTeam] = []
    for item in items:
        if item.members in seen:
            continue
        seen.add(item.members)
        out.append(item)
    return out


def _counter_value(counter: CallCounter | None, fallback: int) -> int:
    return counter() if counter is not None else fallback


def run_exhaustive_validation(
    legal_teams: Sequence[tuple[str, ...]],
    *,
    true_score: ScoreFn,
    proxy_score: ScoreFn,
    select_candidates: CandidateSelector,
    optimizer_score: ScoreFn | None = None,
    team_count: int = 5,
    top_n: int = 20,
    ground_truth_call_count: CallCounter | None = None,
    optimizer_call_count: CallCounter | None = None,
) -> ValidationMetrics:
    """Compare a candidate selector with exhaustive ground truth.

    ``true_score`` builds the exhaustive truth. ``optimizer_score`` evaluates only
    the selected candidate pool; it can be a separate MorisEvaluator instance so
    cache reuse from ground-truth generation cannot make the optimizer call budget
    look artificially cheap.

    When call counters are supplied, their deltas are recorded. For Moris these
    should return ``evaluator.stats.simulate_calls`` so the metric is actual
    ``simulate()`` calls rather than requests. Without counters, score-function
    invocation counts are reported, which is sufficient for synthetic fixtures.
    """
    if team_count <= 0:
        raise ValueError("team_count must be positive")
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    teams: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for raw in legal_teams:
        team = tuple(raw)
        if team in seen:
            continue
        if not team or len(set(team)) != len(team):
            raise ValueError("legal teams must be non-empty with unique members")
        seen.add(team)
        teams.append(team)
    if not teams:
        raise ValueError("legal_teams must not be empty")

    proxy_candidates = [
        CandidateTeam(team, float(proxy_score(team)), source="proxy")
        for team in teams
    ]

    ground_before = _counter_value(ground_truth_call_count, 0)
    ground_invocations = 0
    t0 = perf_counter()
    evaluated_all: list[CandidateTeam] = []
    for item in proxy_candidates:
        evaluated_all.append(item.with_simulated_score(float(true_score(item.members))))
        ground_invocations += 1
    optimum = select_global_allocation(evaluated_all, team_count=team_count)
    exhaustive_runtime = perf_counter() - t0
    ground_after = _counter_value(ground_truth_call_count, ground_invocations)
    exhaustive_calls = ground_after - ground_before if ground_truth_call_count else ground_invocations

    if optimum is None:
        raise ValueError("legal team space cannot form the requested disjoint allocation")

    selected = _unique_candidates(select_candidates(proxy_candidates))
    legal_keys = {item.members for item in proxy_candidates}
    unknown = [item.members for item in selected if item.members not in legal_keys]
    if unknown:
        raise ValueError(f"candidate selector returned teams outside legal space: {unknown}")

    selected_keys = {item.members for item in selected}
    optimum_keys = {item.members for item in optimum.teams}
    true_optimum_survival = len(optimum_keys & selected_keys) / len(optimum_keys)

    ranked = sorted(
        evaluated_all,
        key=lambda item: (
            item.simulated_score
            if item.simulated_score is not None
            else float("-inf")
        ),
        reverse=True,
    )
    top = ranked[: min(top_n, len(ranked))]
    top_n_recall = sum(item.members in selected_keys for item in top) / len(top)

    score_selected = optimizer_score or true_score
    optimizer_before = _counter_value(optimizer_call_count, 0)
    optimizer_invocations = 0
    t1 = perf_counter()
    evaluated_selected: list[CandidateTeam] = []
    for item in selected:
        evaluated_selected.append(
            item.with_simulated_score(float(score_selected(item.members)))
        )
        optimizer_invocations += 1
    final = select_global_allocation(evaluated_selected, team_count=team_count)
    optimizer_runtime = perf_counter() - t1
    optimizer_after = _counter_value(optimizer_call_count, optimizer_invocations)
    optimizer_calls = (
        optimizer_after - optimizer_before
        if optimizer_call_count
        else optimizer_invocations
    )

    final_score = final.total_score if final is not None else 0.0
    ratio = final_score / optimum.total_score if optimum.total_score else 1.0
    return ValidationMetrics(
        legal_team_count=len(teams),
        candidate_count=len(selected),
        exhaustive_evaluator_calls=exhaustive_calls,
        optimizer_evaluator_calls=optimizer_calls,
        true_optimum_survival=true_optimum_survival,
        top_n_recall=top_n_recall,
        exhaustive_optimum=optimum.total_score,
        final_score=final_score,
        final_to_optimum=ratio,
        exhaustive_runtime_s=exhaustive_runtime,
        optimizer_runtime_s=optimizer_runtime,
    )
