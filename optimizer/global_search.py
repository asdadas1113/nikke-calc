"""Global no-overlap allocation over an already evaluated candidate pool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .candidates import CandidateTeam


@dataclass(frozen=True)
class Allocation:
    total_score: float
    teams: tuple[CandidateTeam, ...]
    explored_nodes: int


def select_global_allocation(
    candidates: Iterable[CandidateTeam],
    *,
    team_count: int = 5,
    require_simulated: bool = True,
) -> Allocation | None:
    """Exactly solve weighted set packing *within the candidate pool*.

    This guarantees the best no-overlap allocation among supplied candidates,
    not among every legal NIKKE squad.  Candidate generation remains heuristic.
    """
    if team_count <= 0:
        raise ValueError("team_count must be positive")

    pool = list(candidates)
    if require_simulated:
        pool = [item for item in pool if item.simulated_score is not None]
    pool.sort(key=lambda item: item.score, reverse=True)
    if len(pool) < team_count:
        return None

    names = sorted({name for item in pool for name in item.members})
    bits = {name: 1 << index for index, name in enumerate(names)}
    masks = [sum(bits[name] for name in item.members) for item in pool]

    best_total = float("-inf")
    best_indices: tuple[int, ...] | None = None
    explored = 0

    def visit(start: int, chosen: tuple[int, ...], used: int, total: float) -> None:
        nonlocal best_total, best_indices, explored
        explored += 1
        need = team_count - len(chosen)
        if need == 0:
            if total > best_total:
                best_total = total
                best_indices = chosen
            return
        if len(pool) - start < need:
            return

        # Safe optimistic bound: ignore overlap and take the next `need` scores.
        optimistic = total + sum(item.score for item in pool[start : start + need])
        if optimistic <= best_total:
            return

        for index in range(start, len(pool)):
            if len(pool) - index < need:
                break
            if masks[index] & used:
                continue
            next_total = total + pool[index].score
            if need > 1:
                remaining_scores = [
                    pool[j].score
                    for j in range(index + 1, len(pool))
                    if not (masks[j] & (used | masks[index]))
                ]
                if len(remaining_scores) < need - 1:
                    continue
                branch_bound = next_total + sum(remaining_scores[: need - 1])
                if branch_bound <= best_total:
                    continue
            visit(index + 1, chosen + (index,), used | masks[index], next_total)

    visit(0, (), 0, 0.0)
    if best_indices is None:
        return None
    return Allocation(
        total_score=best_total,
        teams=tuple(pool[index] for index in best_indices),
        explored_nodes=explored,
    )
