"""Candidate representation and cheap diversity-preserving filtering."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable


@dataclass(frozen=True)
class CandidateTeam:
    members: tuple[str, ...]
    proxy_score: float
    simulated_score: float | None = None
    source: str = "proxy"

    def __post_init__(self) -> None:
        if not self.members or len(set(self.members)) != len(self.members):
            raise ValueError("candidate members must be non-empty and unique")

    @property
    def score(self) -> float:
        return self.simulated_score if self.simulated_score is not None else self.proxy_score

    @property
    def member_set(self) -> frozenset[str]:
        return frozenset(self.members)

    def with_simulated_score(self, score: float) -> "CandidateTeam":
        return replace(self, simulated_score=float(score))


def jaccard_similarity(a: CandidateTeam, b: CandidateTeam) -> float:
    union = a.member_set | b.member_set
    return len(a.member_set & b.member_set) / len(union) if union else 1.0


def select_diverse(
    candidates: Iterable[CandidateTeam],
    limit: int,
    *,
    similarity_penalty: float = 0.20,
) -> list[CandidateTeam]:
    """Keep strong proxy candidates without filling the pool with near-clones.

    Proxy scores are min-max normalized before applying a Jaccard penalty, so the
    diversity weight is independent of the damage-score scale.
    """
    if limit <= 0:
        return []
    pool = sorted(candidates, key=lambda item: item.proxy_score, reverse=True)
    if len(pool) <= limit:
        return pool

    low = min(item.proxy_score for item in pool)
    high = max(item.proxy_score for item in pool)
    span = high - low

    def strength(item: CandidateTeam) -> float:
        return 1.0 if span == 0 else (item.proxy_score - low) / span

    selected = [pool.pop(0)]
    while pool and len(selected) < limit:
        best_index = max(
            range(len(pool)),
            key=lambda index: (
                strength(pool[index])
                - similarity_penalty
                * max(jaccard_similarity(pool[index], chosen) for chosen in selected),
                pool[index].proxy_score,
            ),
        )
        selected.append(pool.pop(best_index))
    return selected
