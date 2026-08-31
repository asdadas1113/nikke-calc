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

from .candidate_generation import generate_additive_beam_candidates
from .marginal import plan_candidate_specific_marginals

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



def _coverage_from_reference(
    roster: Sequence[str],
    unplanned: frozenset[str],
    reference: Team,
    *,
    legal: TeamValidator,
) -> frozenset[str]:
    """Characters that gain at least one legal one-slot marginal context."""

    covered: set[str] = set()
    reference_set = set(reference)
    for candidate in unplanned:
        if candidate in reference_set:
            continue
        for index in range(len(reference)):
            trial = list(reference)
            trial[index] = candidate
            trial_team = tuple(trial)
            if len(set(trial_team)) != len(trial_team):
                continue
            if legal(trial_team):
                covered.add(candidate)
                break
    return frozenset(covered)


def _rotated_rosters(roster: tuple[str, ...], *, max_rotations: int) -> tuple[tuple[str, ...], ...]:
    """Deterministic score-blind order variants for structural beam diversity."""

    if max_rotations <= 0:
        raise ValueError("max_rotations must be positive")
    n = len(roster)
    if n == 0:
        return ()
    count = min(max_rotations, n)
    offsets = []
    for i in range(count):
        offset = (i * n) // count
        if offset not in offsets:
            offsets.append(offset)
    variants = [roster[offset:] + roster[:offset] for offset in offsets]
    reversed_roster = tuple(reversed(roster))
    for i in range(min(count, max(0, max_rotations - len(variants)))):
        offset = (i * n) // max(1, count)
        row = reversed_roster[offset:] + reversed_roster[:offset]
        if row not in variants:
            variants.append(row)
    return tuple(variants[:max_rotations])


def ensure_marginal_reference_coverage(
    roster: Sequence[str],
    references: Sequence[Sequence[str]],
    *,
    positions_per_candidate: int,
    team_size: int,
    legal: TeamValidator,
    partial_viable: Callable[[Team, tuple[str, ...]], bool] | None = None,
    beam_width: int = 96,
    candidates_per_rotation: int = 12,
    max_rotations: int = 12,
) -> tuple[tuple[Team, ...], tuple[Team, ...]]:
    """Add score-blind structural references until every plannable member has context.

    Existing/public references stay first.  Missing marginal coverage is repaired
    with a bounded structural candidate pool; no Moris damage, usage, OL, level,
    combat power, or other strength signal is consulted.  Candidate generation
    prefers already-covered members so new references tend to *exclude* currently
    unplanned characters, then the selected reference maximizes newly-covered
    marginal contexts and minimizes membership overlap with existing references.

    The function validates the final result through the canonical marginal planner.
    If bounded structural generation cannot repair all candidates it fails closed
    rather than assigning proxy values to unobserved characters.
    """

    names = tuple(str(name) for name in roster)
    if not names or len(set(names)) != len(names):
        raise ValueError("roster must contain unique members")
    if team_size <= 0 or team_size > len(names):
        raise ValueError("team_size must be positive and no larger than roster")
    if positions_per_candidate <= 0:
        raise ValueError("positions_per_candidate must be positive")
    if beam_width <= 0 or candidates_per_rotation <= 0 or max_rotations <= 0:
        raise ValueError("reference coverage beam bounds must be positive")

    refs: list[Team] = []
    membership_seen: set[frozenset[str]] = set()
    for raw in references:
        team = tuple(str(name) for name in raw)
        if len(team) != team_size or len(set(team)) != team_size:
            raise ValueError("reference teams must match team_size with unique members")
        if not legal(team):
            raise ValueError(f"reference team is hard-illegal: {team}")
        membership = frozenset(team)
        if membership in membership_seen:
            continue
        membership_seen.add(membership)
        refs.append(team)

    added: list[Team] = []
    initial_plan = (
        plan_candidate_specific_marginals(
            names, refs, positions_per_candidate=positions_per_candidate, legal=legal
        )
        if refs
        else None
    )
    unplanned = frozenset(names if initial_plan is None else initial_plan.unplanned_candidates)
    if not unplanned:
        return tuple(refs), ()

    stable_index = {name: i for i, name in enumerate(names)}
    rotations = _rotated_rosters(names, max_rotations=max_rotations)

    while unplanned:
        # This synthetic score is coverage-only: already-covered members score 1,
        # currently unplanned members 0.  It therefore favors references that
        # leave unplanned characters outside the team, giving them probe context.
        score = {name: (0.0 if name in unplanned else 1.0) for name in names}
        pool: dict[frozenset[str], Team] = {}
        for rotated in rotations:
            generated = generate_additive_beam_candidates(
                rotated,
                score,
                team_size=team_size,
                beam_width=beam_width,
                global_limit=candidates_per_rotation,
                legal=legal,
                partial_viable=partial_viable,
            )
            for row in generated.teams:
                membership = frozenset(row)
                if membership in membership_seen or membership in pool:
                    continue
                # Canonicalize only for deterministic tie-breaking; legality was
                # already checked and this fallback has no combat-order claim.
                canonical = tuple(sorted(membership, key=stable_index.__getitem__))
                if legal(canonical):
                    pool[membership] = canonical

        best: Team | None = None
        best_coverage: frozenset[str] = frozenset()
        best_key = None
        for membership, team in pool.items():
            coverage = _coverage_from_reference(names, unplanned, team, legal=legal)
            if not coverage:
                continue
            overlaps = [len(membership & frozenset(ref)) for ref in refs]
            max_overlap = max(overlaps, default=0)
            total_overlap = sum(overlaps)
            key = (
                -len(coverage),
                max_overlap,
                total_overlap,
                tuple(stable_index[name] for name in team),
            )
            if best_key is None or key < best_key:
                best_key = key
                best = team
                best_coverage = coverage

        if best is None:
            raise ValueError(
                "cannot construct bounded score-blind legal reference coverage for: "
                + ", ".join(name for name in names if name in unplanned)
            )

        refs.append(best)
        added.append(best)
        membership_seen.add(frozenset(best))
        unplanned = frozenset(name for name in unplanned if name not in best_coverage)

    final_plan = plan_candidate_specific_marginals(
        names, refs, positions_per_candidate=positions_per_candidate, legal=legal
    )
    if final_plan.unplanned_candidates:
        raise RuntimeError(
            "reference coverage bookkeeping disagrees with canonical marginal planner: "
            + ", ".join(final_plan.unplanned_candidates)
        )
    return tuple(refs), tuple(added)

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
