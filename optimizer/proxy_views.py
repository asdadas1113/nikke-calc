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
