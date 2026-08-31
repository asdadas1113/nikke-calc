"""Bounded Moris-backed reference discovery for unordered external compositions.

Public Solo Raid sources can prove that five characters were used together while
leaving squad slot order uncertain. Marginal probes still need an ordered Moris
squad, so silently picking one permutation would introduce an arbitrary hidden
assumption. This module instead explores a small, caller-bounded placement prefix
with no strength heuristic, then lets actual Moris damage choose the reference.

The placement prefix balances member×slot coverage. Search metadata only decides
which placements are inspected; no external rank, damage, usage, or synergy value
is added to Moris scores. If the new-call budget cannot give every viable source
at least one placement, discovery fails before simulation rather than favoring an
earlier source by input order.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import permutations

from .budget import BudgetedEvaluator, SearchBudget, SearchBudgetExhausted
from .evaluator import MorisEvaluator

Team = tuple[str, ...]
TeamValidator = Callable[[Team], bool]


@dataclass(frozen=True)
class ReferenceComposition:
    members: Team
    source: str
    order_known: bool = False

    def __post_init__(self) -> None:
        if not self.members or len(set(self.members)) != len(self.members):
            raise ValueError("reference composition must contain unique members")
        if not self.source:
            raise ValueError("reference composition source must be non-empty")


@dataclass(frozen=True)
class EvaluatedReferencePlacement:
    members: Team
    score: float
    source: str
    placement_rank: int


@dataclass(frozen=True)
class ReferenceDiscoveryResult:
    selected_references: tuple[Team, ...]
    evaluated: tuple[EvaluatedReferencePlacement, ...]
    unfulfilled_sources: tuple[str, ...]
    simulate_calls: int


def balanced_placement_order(members: Sequence[str]) -> tuple[Team, ...]:
    """Return every permutation in deterministic member×slot-balanced order.

    For five members there are only 120 cheap tuples. At each step we choose the
    remaining permutation that minimizes the sum of squared member-slot exposure
    counts after adding it. This strongly prefers placements covering new slots
    before repeating already-observed member-slot pairs, but contains no combat
    strength information.
    """

    team = tuple(str(name) for name in members)
    if not team or len(set(team)) != len(team):
        raise ValueError("members must contain unique names")

    remaining = list(permutations(team))
    index = {name: i for i, name in enumerate(team)}
    counts = [[0 for _slot in team] for _member in team]
    out: list[Team] = []

    while remaining:
        best_index = 0
        best_key = None
        for i, perm in enumerate(remaining):
            penalty = 0
            max_count = 0
            for slot, name in enumerate(perm):
                after = counts[index[name]][slot] + 1
                penalty += after * after
                max_count = max(max_count, after)
            key = (max_count, penalty, tuple(index[name] for name in perm))
            if best_key is None or key < best_key:
                best_key = key
                best_index = i
        chosen = remaining.pop(best_index)
        out.append(chosen)
        for slot, name in enumerate(chosen):
            counts[index[name]][slot] += 1

    return tuple(out)


def _placement_channel(
    composition: ReferenceComposition,
    *,
    legal: TeamValidator | None,
    max_per_composition: int,
) -> tuple[Team, ...]:
    if max_per_composition <= 0:
        return ()
    placements = (
        (composition.members,)
        if composition.order_known
        else balanced_placement_order(composition.members)
    )
    out: list[Team] = []
    for team in placements:
        if legal is not None and not legal(team):
            continue
        out.append(team)
        if len(out) >= max_per_composition:
            break
    return tuple(out)


def discover_reference_placements(
    evaluator: MorisEvaluator,
    compositions: Sequence[ReferenceComposition],
    *,
    budget: SearchBudget,
    max_per_composition: int,
    legal: TeamValidator | None = None,
    evaluate_kwargs: dict | None = None,
) -> ReferenceDiscoveryResult:
    """Evaluate placement channels fairly and keep each composition's best Moris row.

    Compositions are rank-round-robin scheduled: every viable source's first legal
    placement is considered before any source's second placement. Before spending
    calls, the function verifies that the budget can pay every *uncached* first
    placement. If not, it raises rather than letting input order decide which
    public composition receives the only look.

    Empty channels caused by hard legality remain visible as unfulfilled sources.
    Cached first placements cost no budget and count toward the fairness guarantee.
    """

    if max_per_composition < 0:
        raise ValueError("max_per_composition must be non-negative")
    sources = [row.source for row in compositions]
    if len(set(sources)) != len(sources):
        raise ValueError("reference composition sources must be unique")

    channels = tuple(
        _placement_channel(
            composition,
            legal=legal,
            max_per_composition=max_per_composition,
        )
        for composition in compositions
    )
    kwargs = dict(evaluate_kwargs or {})
    first_placements = tuple(channel[0] for channel in channels if channel)
    uncached_first = sum(
        not evaluator.is_cached(team, **kwargs)
        for team in first_placements
    )
    if budget.max_simulate_calls < uncached_first:
        raise ValueError(
            "reference discovery budget cannot give every viable composition one "
            f"placement: needs {uncached_first} new calls, budget is "
            f"{budget.max_simulate_calls}"
        )

    budgeted = BudgetedEvaluator(evaluator, budget)
    evaluated: list[EvaluatedReferencePlacement] = []
    best_by_source: dict[str, EvaluatedReferencePlacement] = {}
    max_rank = max((len(channel) for channel in channels), default=0)

    for rank in range(max_rank):
        for composition, channel in zip(compositions, channels):
            if rank >= len(channel):
                continue
            team = channel[rank]
            try:
                result = budgeted.evaluate(team, **kwargs)
            except SearchBudgetExhausted:
                continue
            row = EvaluatedReferencePlacement(
                members=team,
                score=float(result.score),
                source=composition.source,
                placement_rank=rank + 1,
            )
            evaluated.append(row)
            previous = best_by_source.get(composition.source)
            if previous is None or row.score > previous.score:
                best_by_source[composition.source] = row

    selected = tuple(
        best_by_source[row.source].members
        for row in compositions
        if row.source in best_by_source
    )
    unfulfilled = tuple(
        row.source for row in compositions if row.source not in best_by_source
    )
    return ReferenceDiscoveryResult(
        selected_references=selected,
        evaluated=tuple(evaluated),
        unfulfilled_sources=unfulfilled,
        simulate_calls=budgeted.used_simulate_calls,
    )
