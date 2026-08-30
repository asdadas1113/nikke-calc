"""One-pass candidate selection across independent cheap proxy views.

A proxy observation can be context-sensitive enough that folding every measured
value into one scalar ranking erases useful candidates.  This module keeps the
views separate through candidate discovery: each view gets its own bounded Top-K
heap, then the selected ordered teams are unioned before expensive simulation.

The selector itself performs no Moris evaluation and does not claim that one
view is more accurate than another.  Actual simulated scores remain the source
of truth after discovery.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Callable

from .marginal import CandidateMarginalPlan, MarginalMeasurement

Team = tuple[str, ...]
TeamValidator = Callable[[Team], bool]


@dataclass(frozen=True)
class ProxyView:
    """One additive character-value interpretation used only for discovery."""

    name: str
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("proxy view name must not be empty")


@dataclass(frozen=True)
class ProxyViewHit:
    """Why one ordered team survived a particular proxy view."""

    view: str
    score: float
    rank: int


@dataclass(frozen=True)
class ProxyViewCandidate:
    """One unioned candidate plus every view that selected it."""

    members: Team
    hits: tuple[ProxyViewHit, ...]

    @property
    def source_views(self) -> tuple[str, ...]:
        return tuple(hit.view for hit in self.hits)


def build_planned_marginal_prefix_views(
    plan: CandidateMarginalPlan,
    measurement: MarginalMeasurement,
    *,
    max_depth: int | None = None,
) -> tuple[ProxyView, ...]:
    """Recover best-so-far marginal views without another simulator call.

    Planned marginal execution is depth-major: a candidate's first replacement
    slot is the earliest interpretation, later slots add alternative contexts.
    Instead of overwriting the first interpretation, this function returns one
    additive view for each measured prefix.  For prefix ``d`` a character keeps
    the best available delta among its first ``d`` planned slots.  If a later
    slot was not measured because SearchBudget ended, its earlier value simply
    carries forward.

    Scores are reconstructed only from ``measurement.evaluated_candidates`` and
    the immutable plan, so creating views costs no additional Moris evaluations.
    Missing baselines/trials remain missing rather than receiving an invented
    zero/default value.
    """

    if max_depth is not None and max_depth <= 0:
        raise ValueError("max_depth must be positive when provided")

    score_by_team = {
        item.members: float(item.simulated_score)
        for item in measurement.evaluated_candidates
        if item.simulated_score is not None
    }
    planned_depth = max((len(entry.positions) for entry in plan.entries), default=0)
    depth_limit = planned_depth if max_depth is None else min(planned_depth, max_depth)

    views: list[ProxyView] = []
    for depth in range(1, depth_limit + 1):
        values: dict[str, float] = {}
        for entry in plan.entries:
            baseline = score_by_team.get(entry.reference)
            if baseline is None:
                continue
            deltas: list[float] = []
            for index in entry.positions[:depth]:
                trial = list(entry.reference)
                trial[index] = entry.candidate
                score = score_by_team.get(tuple(trial))
                if score is not None:
                    deltas.append(score - baseline)
            if deltas:
                values[entry.candidate] = max(deltas)
        if values:
            views.append(ProxyView(name=f"marginal-prefix-{depth}", values=values))
    return tuple(views)


def select_proxy_view_candidates(
    candidate_teams: Iterable[Sequence[str]],
    views: Sequence[ProxyView],
    *,
    limit_per_view: int,
    legal: TeamValidator | None = None,
) -> tuple[ProxyViewCandidate, ...]:
    """Scan a unique ordered-team stream once and union each view's Top-K.

    The candidate stream is intentionally consumed once, so callers may pass a
    large generator rather than materializing every legal combination or
    re-enumerating it per view.  Each view scores a team only when all members
    have values in that view.  Exact score ties keep earlier input order.

    ``candidate_teams`` is expected to contain unique ordered teams.  Enforcing
    global duplicate detection here would require memory proportional to the
    full combinatorial universe, defeating the bounded-memory purpose of this
    primitive.  Final selected teams are still deduplicated across views.
    """

    if limit_per_view < 0:
        raise ValueError("limit_per_view must be non-negative")
    if limit_per_view == 0 or not views:
        return ()

    names = [view.name for view in views]
    if len(set(names)) != len(names):
        raise ValueError("proxy view names must be unique")

    heaps: list[list[tuple[float, int, Team]]] = [[] for _ in views]

    for index, raw_team in enumerate(candidate_teams):
        team = tuple(raw_team)
        if not team or len(set(team)) != len(team):
            continue
        if legal is not None and not legal(team):
            continue

        for view_index, view in enumerate(views):
            if any(member not in view.values for member in team):
                continue
            score = float(sum(view.values[member] for member in team))
            if not isfinite(score):
                continue

            # The weakest row sits at heap[0].  Earlier input order wins exact
            # score ties, hence ``-index`` is larger for earlier rows.
            row = (score, -index, team)
            heap = heaps[view_index]
            if len(heap) < limit_per_view:
                heapq.heappush(heap, row)
            elif row[:2] > heap[0][:2]:
                heapq.heapreplace(heap, row)

    union: dict[Team, list[ProxyViewHit]] = {}
    order: list[Team] = []
    for view, heap in zip(views, heaps):
        ranked = sorted(heap, key=lambda row: (row[0], row[1]), reverse=True)
        for rank, (score, _negative_index, team) in enumerate(ranked, start=1):
            if team not in union:
                union[team] = []
                order.append(team)
            union[team].append(ProxyViewHit(view=view.name, score=score, rank=rank))

    return tuple(
        ProxyViewCandidate(members=team, hits=tuple(union[team])) for team in order
    )
