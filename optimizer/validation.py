"""Validation harnesses for optimizer search and Fast-vs-Moris ranking.

The exhaustive allocation helper predates Fast Engine and remains useful for tiny
search spaces.  The ranking diagnostics added below are deliberately evaluator-
agnostic: production/local experiments can bind Moris and Fast callables, while CI
uses synthetic scores and public fixtures without committing account data.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations, permutations
from math import isfinite
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


# ---------------------------------------------------------------------------
# Fast-vs-Moris ranking diagnostics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RankingObservation:
    """One candidate scored by Moris and, when safe, by Fast.

    ``fast_score=None`` means Fast deliberately failed closed.  That is kept
    distinct from a low numeric score because a blocked strong team must be
    protected/fallback-scored rather than pruned as weak.

    ``groups`` are caller-owned diagnostic labels such as ``weapon:MG``,
    ``mechanic:core`` or ``archetype:charge``.  The validation core never assigns
    game-specific meaning to those labels.
    """

    members: tuple[str, ...]
    moris_score: float
    fast_score: float | None
    blockers: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroupRankingMetrics:
    group: str
    candidate_count: int
    fast_scored_count: int
    blocked_count: int
    top_n_count: int
    top_n_recalled: int
    top_n_recall: float | None
    mean_rank_percentile_error: float | None


@dataclass(frozen=True)
class RankingValidationMetrics:
    candidate_count: int
    fast_scored_count: int
    blocked_count: int
    top_n: int
    top_k: int
    top_n_recalled: int
    top_n_recall: float
    top_n_blocked: int
    top_n_ranked_out: int
    catastrophic_false_negative_rate: float
    pairwise_accuracy: float | None
    comparable_pairs: int
    best_missed_true_rank: int | None
    best_missed_team: tuple[str, ...] | None
    blocker_counts: tuple[tuple[str, int], ...]
    unsupported_counts: tuple[tuple[str, int], ...]
    groups: tuple[GroupRankingMetrics, ...]


def _validate_ranking_observations(
    observations: Sequence[RankingObservation],
) -> tuple[RankingObservation, ...]:
    rows = tuple(observations)
    if not rows:
        raise ValueError("observations must not be empty")

    seen: set[tuple[str, ...]] = set()
    normalized: list[RankingObservation] = []
    for raw in rows:
        members = tuple(raw.members)
        if not members or len(set(members)) != len(members):
            raise ValueError("ranking members must be non-empty with unique members")
        if members in seen:
            raise ValueError(f"duplicate ranking candidate: {members}")
        seen.add(members)
        moris = float(raw.moris_score)
        fast = None if raw.fast_score is None else float(raw.fast_score)
        if not isfinite(moris):
            raise ValueError(f"non-finite Moris score for {members}")
        if fast is not None and not isfinite(fast):
            raise ValueError(f"non-finite Fast score for {members}")
        normalized.append(
            RankingObservation(
                members=members,
                moris_score=moris,
                fast_score=fast,
                blockers=tuple(dict.fromkeys(str(value) for value in raw.blockers)),
                unsupported=tuple(dict.fromkeys(str(value) for value in raw.unsupported)),
                groups=tuple(dict.fromkeys(str(value) for value in raw.groups)),
            )
        )
    return tuple(normalized)


def _rank_percentile(rank: int, count: int) -> float:
    if count <= 1:
        return 0.0
    return (rank - 1) / (count - 1)


def analyze_fast_moris_ranking(
    observations: Sequence[RankingObservation],
    *,
    top_n: int,
    top_k: int,
) -> RankingValidationMetrics:
    """Measure whether Fast preserves the Moris ranking that pruning cares about.

    Ranking is deterministic on ties via ``members``.  Pairwise accuracy excludes
    Moris ties (there is no true ordering to preserve); a Fast tie on a comparable
    pair receives half credit.  Blocked candidates never receive an artificial
    numeric score and are reported separately from scored candidates that merely
    fall below Fast Top-K.

    ``mean_rank_percentile_error`` is scale-free.  Positive means the scored group
    is, on average, pushed *down* by Fast relative to Moris; negative means Fast
    promotes it.  Blocked rows are excluded from this signed error and exposed via
    ``blocked_count`` instead.
    """

    if top_n <= 0 or top_k <= 0:
        raise ValueError("top_n and top_k must be positive")
    rows = _validate_ranking_observations(observations)

    moris_ranked = sorted(rows, key=lambda row: (-row.moris_score, row.members))
    scored = tuple(row for row in rows if row.fast_score is not None)
    fast_ranked = sorted(
        scored,
        key=lambda row: (-float(row.fast_score), row.members),
    )

    true_top = tuple(moris_ranked[: min(top_n, len(moris_ranked))])
    fast_top = tuple(fast_ranked[: min(top_k, len(fast_ranked))])
    fast_top_keys = {row.members for row in fast_top}

    recalled = sum(row.members in fast_top_keys for row in true_top)
    top_blocked = sum(row.fast_score is None for row in true_top)
    top_ranked_out = len(true_top) - recalled - top_blocked
    recall = recalled / len(true_top)
    catastrophic = 1.0 - recall

    pair_score = 0.0
    comparable = 0
    for left, right in combinations(scored, 2):
        true_delta = left.moris_score - right.moris_score
        if true_delta == 0.0:
            continue
        fast_delta = float(left.fast_score) - float(right.fast_score)
        comparable += 1
        if fast_delta == 0.0:
            pair_score += 0.5
        elif (true_delta > 0.0) == (fast_delta > 0.0):
            pair_score += 1.0
    pairwise = pair_score / comparable if comparable else None

    missed = [row for row in true_top if row.members not in fast_top_keys]
    moris_rank_by_team = {
        row.members: rank
        for rank, row in enumerate(moris_ranked, start=1)
    }
    best_missed = min(
        missed,
        key=lambda row: moris_rank_by_team[row.members],
        default=None,
    )

    blocker_counter: Counter[str] = Counter()
    unsupported_counter: Counter[str] = Counter()
    for row in rows:
        blocker_counter.update(row.blockers)
        unsupported_counter.update(row.unsupported)

    fast_rank_by_team = {
        row.members: rank
        for rank, row in enumerate(fast_ranked, start=1)
    }
    true_top_keys = {row.members for row in true_top}
    all_groups = sorted({group for row in rows for group in row.groups})
    group_rows: list[GroupRankingMetrics] = []
    for group in all_groups:
        members = tuple(row for row in rows if group in row.groups)
        group_scored = tuple(row for row in members if row.fast_score is not None)
        group_true_top = tuple(row for row in members if row.members in true_top_keys)
        group_recalled = sum(row.members in fast_top_keys for row in group_true_top)
        errors = [
            _rank_percentile(fast_rank_by_team[row.members], len(fast_ranked))
            - _rank_percentile(moris_rank_by_team[row.members], len(moris_ranked))
            for row in group_scored
        ]
        group_rows.append(
            GroupRankingMetrics(
                group=group,
                candidate_count=len(members),
                fast_scored_count=len(group_scored),
                blocked_count=len(members) - len(group_scored),
                top_n_count=len(group_true_top),
                top_n_recalled=group_recalled,
                top_n_recall=(
                    group_recalled / len(group_true_top)
                    if group_true_top
                    else None
                ),
                mean_rank_percentile_error=(
                    sum(errors) / len(errors)
                    if errors
                    else None
                ),
            )
        )

    return RankingValidationMetrics(
        candidate_count=len(rows),
        fast_scored_count=len(scored),
        blocked_count=len(rows) - len(scored),
        top_n=len(true_top),
        top_k=min(top_k, len(fast_ranked)),
        top_n_recalled=recalled,
        top_n_recall=recall,
        top_n_blocked=top_blocked,
        top_n_ranked_out=top_ranked_out,
        catastrophic_false_negative_rate=catastrophic,
        pairwise_accuracy=pairwise,
        comparable_pairs=comparable,
        best_missed_true_rank=(
            moris_rank_by_team[best_missed.members]
            if best_missed is not None
            else None
        ),
        best_missed_team=(best_missed.members if best_missed is not None else None),
        blocker_counts=tuple(
            sorted(blocker_counter.items(), key=lambda row: (-row[1], row[0]))
        ),
        unsupported_counts=tuple(
            sorted(unsupported_counter.items(), key=lambda row: (-row[1], row[0]))
        ),
        groups=tuple(group_rows),
    )
