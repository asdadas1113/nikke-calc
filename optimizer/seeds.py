"""Explicit candidate-protection seeds for budgeted roster search.

Seeds may protect a known full composition or a partial member core from being
missed by proxy discovery.  They never alter Moris damage, hard legality, or the
final allocator score.  Their only job is to nominate already-existing candidate
teams for at least one real evaluator look when the caller grants seed budget.

This module deliberately does not invent roster-wide combinations.  Exact seeds
name one ordered team directly.  Core seeds filter a caller-supplied candidate
universe so the surrounding members continue to come from the normal account-
specific discovery path rather than from a hidden "famous comp" heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

Team = tuple[str, ...]
TeamValidator = Callable[[Team], bool]


@dataclass(frozen=True)
class ExactCompSeed:
    """One explicitly sourced ordered composition to protect for evaluation."""

    members: Team
    source: str = "exact-comp"

    def __post_init__(self) -> None:
        if not self.members or len(set(self.members)) != len(self.members):
            raise ValueError("exact seed members must be non-empty and unique")
        if not self.source.strip():
            raise ValueError("seed source must be non-empty")


@dataclass(frozen=True)
class CoreSeed:
    """A partial member relationship that should be preserved during discovery.

    ``members`` are membership constraints only; they do not impose placement or
    attach a strength bonus.  Ordered candidate identity remains authoritative
    once a caller-supplied candidate team matches the core.
    """

    members: tuple[str, ...]
    source: str = "core"

    def __post_init__(self) -> None:
        if len(self.members) < 2 or len(set(self.members)) != len(self.members):
            raise ValueError("core seed must contain at least two unique members")
        if not self.source.strip():
            raise ValueError("seed source must be non-empty")


@dataclass(frozen=True)
class SeedCandidate:
    members: Team
    seed_source: str
    seed_kind: str


@dataclass(frozen=True)
class SeedSelection:
    candidates: tuple[SeedCandidate, ...]
    unfulfilled_exact: tuple[ExactCompSeed, ...]
    unfulfilled_cores: tuple[CoreSeed, ...]


def select_seed_candidates(
    candidate_teams: Iterable[Sequence[str]],
    *,
    exact_seeds: Sequence[ExactCompSeed] = (),
    core_seeds: Sequence[CoreSeed] = (),
    roster: Sequence[str] | None = None,
    legal: TeamValidator | None = None,
    max_per_core: int = 1,
) -> SeedSelection:
    """Protect explicit seed hypotheses without creating a hidden team generator.

    Exact compositions are considered directly when all members are owned and
    legal.  Core seeds only select from ``candidate_teams`` in their existing
    deterministic order; this keeps the remaining slots account-specific and
    caller-owned.  Duplicate ordered teams are emitted once even if multiple
    seeds nominate them.

    ``unfulfilled_*`` is diagnostic rather than a hard failure.  An exact seed can
    be unavailable because the account does not own every member or the team is
    hard-illegal; a core can be unavailable because no supplied candidate matches
    it.  Search orchestration may surface these separately from budget exhaustion.
    """

    if max_per_core < 0:
        raise ValueError("max_per_core must be non-negative")

    universe: list[Team] = []
    universe_seen: set[Team] = set()
    for raw in candidate_teams:
        team = tuple(str(name) for name in raw)
        if not team or len(set(team)) != len(team):
            raise ValueError("candidate teams must be non-empty with unique members")
        if team not in universe_seen:
            universe.append(team)
            universe_seen.add(team)

    owned = None if roster is None else frozenset(str(name) for name in roster)
    emitted: set[Team] = set()
    selected: list[SeedCandidate] = []
    missing_exact: list[ExactCompSeed] = []
    missing_core: list[CoreSeed] = []

    for seed in exact_seeds:
        team = tuple(seed.members)
        if owned is not None and not set(team) <= owned:
            missing_exact.append(seed)
            continue
        if legal is not None and not legal(team):
            missing_exact.append(seed)
            continue
        if team not in emitted:
            selected.append(SeedCandidate(team, seed.source, "exact"))
            emitted.add(team)

    for seed in core_seeds:
        if owned is not None and not set(seed.members) <= owned:
            missing_core.append(seed)
            continue
        if max_per_core == 0:
            missing_core.append(seed)
            continue
        core = set(seed.members)
        matched = 0
        for team in universe:
            if not core <= set(team):
                continue
            if legal is not None and not legal(team):
                continue
            matched += 1
            if team not in emitted:
                selected.append(SeedCandidate(team, seed.source, "core"))
                emitted.add(team)
            if matched >= max_per_core:
                break
        if matched == 0:
            missing_core.append(seed)

    return SeedSelection(
        candidates=tuple(selected),
        unfulfilled_exact=tuple(missing_exact),
        unfulfilled_cores=tuple(missing_core),
    )
