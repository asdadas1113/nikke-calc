"""Simulation-free bounded candidate generation from measured marginal evidence.

The optimizer cannot enumerate every roster composition through Moris. This
module provides explicit beam primitives that use already-measured per-character
marginal values only to decide *where to look*.

Membership search and ordered placement are deliberately separate. Moris may care
about squad order, so a cheap allocation beam never pretends one arbitrary order
is the membership's true score. It first searches unordered membership sets, then
expands each selected membership through a caller-supplied placement iterator.

No generated proxy value changes Moris damage or final allocation. Beam widths,
output limits, required cores, allocation depth, and placement enumeration are all
caller-owned. The primitives make no claim that their output contains the global
optimum.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import permutations

Team = tuple[str, ...]
TeamValidator = Callable[[Team], bool]
PartialTeamViability = Callable[[Team, tuple[str, ...]], bool]
PlacementExpander = Callable[[Team], Iterable[Sequence[str]]]


@dataclass(frozen=True)
class GeneratedCandidate:
    members: Team
    proxy_score: float
    source: str
    required_members: tuple[str, ...]


@dataclass(frozen=True)
class CandidateGenerationResult:
    candidates: tuple[GeneratedCandidate, ...]
    expanded_states: int
    rejected_illegal: int
    unfulfilled_required: tuple[tuple[str, ...], ...]

    @property
    def teams(self) -> tuple[Team, ...]:
        return tuple(row.members for row in self.candidates)


@dataclass(frozen=True)
class GeneratedProxyAllocation:
    """One cheap non-overlapping membership path, never a final answer."""

    teams: tuple[Team, ...]
    proxy_total: float


@dataclass(frozen=True)
class AllocationCandidateGenerationResult:
    """Candidate placements protected by bounded multi-team membership search."""

    candidates: tuple[GeneratedCandidate, ...]
    candidate_channels: tuple[tuple[GeneratedCandidate, ...], ...]
    allocations: tuple[GeneratedProxyAllocation, ...]
    expanded_states: int
    rejected_illegal: int

    @property
    def teams(self) -> tuple[Team, ...]:
        return tuple(row.members for row in self.candidates)


def identity_placement(members: Team) -> tuple[Team, ...]:
    """One stable placement in the membership's canonical roster order."""

    return (members,)


def all_permutation_placements(members: Team) -> Iterable[Team]:
    """Enumerate every ordered placement with no strength assumption.

    For a five-member squad this is at most 120 cheap tuples. Callers still decide
    how many placement candidates receive expensive Moris evaluations.
    """

    return permutations(members)


def _interleave_channels(
    channels: Sequence[Sequence[GeneratedCandidate]],
) -> tuple[GeneratedCandidate, ...]:
    """Rank-round-robin bounded channels while deduplicating ordered teams."""

    seen: set[Team] = set()
    out: list[GeneratedCandidate] = []
    max_rank = max((len(channel) for channel in channels), default=0)
    for rank in range(max_rank):
        for channel in channels:
            if rank >= len(channel):
                continue
            row = channel[rank]
            if row.members in seen:
                continue
            seen.add(row.members)
            out.append(row)
    return tuple(out)


def _validate_inputs(
    roster: Sequence[str],
    score_by_character: Mapping[str, float],
    *,
    team_size: int,
) -> tuple[str, ...]:
    names = tuple(str(name) for name in roster)
    if not names or len(set(names)) != len(names):
        raise ValueError("roster must contain unique members")
    if team_size <= 0:
        raise ValueError("team_size must be positive")
    if team_size > len(names):
        raise ValueError("team_size cannot exceed roster size")
    missing_scores = tuple(name for name in names if name not in score_by_character)
    if missing_scores:
        raise ValueError(f"missing character proxy scores: {missing_scores}")
    return names


def _membership_beam(
    roster: tuple[str, ...],
    score_by_character: Mapping[str, float],
    *,
    team_size: int,
    beam_width: int,
    required_members: tuple[str, ...] = (),
    partial_viable: PartialTeamViability | None = None,
) -> tuple[tuple[tuple[Team, float], ...], int]:
    """Return top additive membership states without choosing squad order."""

    if len(required_members) > team_size:
        return (), 0
    index = {name: i for i, name in enumerate(roster)}
    required_set = frozenset(required_members)
    required_canonical = tuple(sorted(required_set, key=index.__getitem__))
    start_score = sum(float(score_by_character[name]) for name in required_canonical)
    if partial_viable is not None and not partial_viable(required_canonical, roster):
        return (), 0
    states: list[tuple[Team, float]] = [(required_canonical, start_score)]
    expanded = 0

    while states and len(states[0][0]) < team_size:
        next_by_members: dict[Team, float] = {}
        for members, score in states:
            selected = set(members)
            for name in roster:
                if name in selected:
                    continue
                expanded += 1
                combined = tuple(sorted((*members, name), key=index.__getitem__))
                if partial_viable is not None and not partial_viable(combined, roster):
                    continue
                candidate_score = score + float(score_by_character[name])
                previous = next_by_members.get(combined)
                if previous is None or candidate_score > previous:
                    next_by_members[combined] = candidate_score

        ranked = sorted(
            next_by_members.items(),
            key=lambda row: (-row[1], tuple(index[name] for name in row[0])),
        )
        states = [(members, score) for members, score in ranked[:beam_width]]

    return tuple(states), expanded


def _placement_channel(
    membership: Team,
    proxy_score: float,
    *,
    source: str,
    required_members: tuple[str, ...],
    legal: TeamValidator | None,
    placement_expander: PlacementExpander,
) -> tuple[tuple[GeneratedCandidate, ...], int]:
    """Expand one membership into legal ordered candidates in stable order."""

    local: list[GeneratedCandidate] = []
    seen: set[Team] = set()
    rejected = 0
    member_set = set(membership)
    for raw in placement_expander(membership):
        team = tuple(str(name) for name in raw)
        if (
            len(team) != len(membership)
            or len(set(team)) != len(membership)
            or set(team) != member_set
        ):
            raise ValueError("placement_expander must return permutations of the membership team")
        if team in seen:
            continue
        seen.add(team)
        if legal is not None and not legal(team):
            rejected += 1
            continue
        local.append(
            GeneratedCandidate(
                members=team,
                proxy_score=float(proxy_score),
                source=source,
                required_members=required_members,
            )
        )
    return tuple(local), rejected


def _beam_channel(
    roster: tuple[str, ...],
    score_by_character: Mapping[str, float],
    *,
    team_size: int,
    beam_width: int,
    limit: int,
    required_members: tuple[str, ...],
    source: str,
    legal: TeamValidator | None,
    placement_expander: PlacementExpander,
    partial_viable: PartialTeamViability | None = None,
) -> tuple[tuple[GeneratedCandidate, ...], int, int]:
    memberships, expanded = _membership_beam(
        roster,
        score_by_character,
        team_size=team_size,
        beam_width=beam_width,
        required_members=required_members,
        partial_viable=partial_viable,
    )
    channels: list[tuple[GeneratedCandidate, ...]] = []
    rejected = 0
    required_set = set(required_members)
    for membership, proxy_score in memberships:
        if not required_set <= set(membership):
            raise AssertionError("beam lost required members")
        channel, bad = _placement_channel(
            membership,
            proxy_score,
            source=source,
            required_members=required_members,
            legal=legal,
            placement_expander=placement_expander,
        )
        rejected += bad
        if channel:
            channels.append(channel)
    return _interleave_channels(channels)[:limit], expanded, rejected


def generate_additive_beam_candidates(
    roster: Sequence[str],
    score_by_character: Mapping[str, float],
    *,
    team_size: int,
    beam_width: int,
    global_limit: int,
    required_cores: Sequence[Sequence[str]] = (),
    per_core_limit: int = 0,
    legal: TeamValidator | None = None,
    placement_expander: PlacementExpander | None = None,
    partial_viable: PartialTeamViability | None = None,
) -> CandidateGenerationResult:
    """Generate a bounded single-team universe without Moris calls.

    One global additive beam is available when ``global_limit > 0``. Optional
    ``required_cores`` run independent beams with those members fixed, then all
    channels are rank-round-robin unioned. Placement variants are also
    rank-round-robin across membership teams so one membership cannot consume the
    whole output merely because it has many permutations.
    """

    names = _validate_inputs(roster, score_by_character, team_size=team_size)
    if beam_width <= 0:
        raise ValueError("beam_width must be positive")
    if global_limit < 0 or per_core_limit < 0:
        raise ValueError("candidate limits must be non-negative")

    placement = placement_expander or identity_placement
    index = {name: i for i, name in enumerate(names)}
    normalized_cores: list[tuple[str, ...]] = []
    for raw in required_cores:
        core = tuple(str(name) for name in raw)
        if not core or len(set(core)) != len(core):
            raise ValueError("required cores must contain unique members")
        unknown = tuple(name for name in core if name not in index)
        if unknown:
            raise ValueError(f"required core contains names outside roster: {unknown}")
        normalized_cores.append(tuple(sorted(core, key=index.__getitem__)))

    channels: list[tuple[GeneratedCandidate, ...]] = []
    expanded = 0
    rejected = 0
    if global_limit:
        channel, work, bad = _beam_channel(
            names,
            score_by_character,
            team_size=team_size,
            beam_width=beam_width,
            limit=global_limit,
            required_members=(),
            source="additive-beam:global",
            legal=legal,
            placement_expander=placement,
            partial_viable=partial_viable,
        )
        channels.append(channel)
        expanded += work
        rejected += bad

    unfulfilled: list[tuple[str, ...]] = []
    for core in normalized_cores:
        if per_core_limit == 0:
            unfulfilled.append(core)
            continue
        channel, work, bad = _beam_channel(
            names,
            score_by_character,
            team_size=team_size,
            beam_width=beam_width,
            limit=per_core_limit,
            required_members=core,
            source="additive-beam:core",
            legal=legal,
            placement_expander=placement,
            partial_viable=partial_viable,
        )
        expanded += work
        rejected += bad
        if channel:
            channels.append(channel)
        else:
            unfulfilled.append(core)

    return CandidateGenerationResult(
        candidates=_interleave_channels(channels),
        expanded_states=expanded,
        rejected_illegal=rejected,
        unfulfilled_required=tuple(unfulfilled),
    )


def generate_additive_allocation_beam_candidates(
    roster: Sequence[str],
    score_by_character: Mapping[str, float],
    *,
    team_size: int,
    team_count: int,
    team_beam_width: int,
    team_options_per_state: int,
    allocation_beam_width: int,
    allocation_limit: int,
    legal: TeamValidator | None = None,
    placement_expander: PlacementExpander | None = None,
    partial_viable: PartialTeamViability | None = None,
) -> AllocationCandidateGenerationResult:
    """Protect ordered candidates from bounded non-overlap membership allocations.

    Single-team Top-K can over-concentrate on the same high-proxy characters and
    leave the exact five-team allocator with too little disjoint supply. This
    primitive instead builds partial *membership allocations*. Each state chooses
    one membership team from the remaining roster and removes those characters.

    Ordered squad variants do not consume allocation-beam width. A membership is
    viable when the supplied placement iterator yields at least one hard-legal
    order. Once top membership allocations are selected, every viable ordered
    placement for their memberships is exposed in separate channels. Callers can
    therefore evaluate first placements across many memberships before spending a
    second call on another order of the same membership.

    The proxy objective is only the transparent sum of supplied character values.
    There is no diversity bonus, meta bonus, or final-score modification.
    """

    names = _validate_inputs(roster, score_by_character, team_size=team_size)
    if team_count <= 0:
        raise ValueError("team_count must be positive")
    if team_size * team_count > len(names):
        raise ValueError("roster is too small for requested non-overlapping teams")
    if team_beam_width <= 0 or team_options_per_state <= 0 or allocation_beam_width <= 0:
        raise ValueError("beam widths and team options must be positive")
    if allocation_limit < 0:
        raise ValueError("allocation_limit must be non-negative")
    if allocation_limit == 0:
        return AllocationCandidateGenerationResult((), (), (), 0, 0)

    placement = placement_expander or identity_placement
    index = {name: i for i, name in enumerate(names)}
    placement_cache: dict[Team, tuple[GeneratedCandidate, ...]] = {}
    rejected_cache: dict[Team, int] = {}

    def placements_for(membership: Team, proxy_score: float) -> tuple[GeneratedCandidate, ...]:
        if membership not in placement_cache:
            channel, bad = _placement_channel(
                membership,
                proxy_score,
                source="additive-allocation-beam",
                required_members=(),
                legal=legal,
                placement_expander=placement,
            )
            placement_cache[membership] = channel
            rejected_cache[membership] = bad
        return placement_cache[membership]

    # (membership teams, used members, additive total). Membership team tuples are
    # always canonical in original roster order; construction order is not part of
    # allocation identity.
    states: list[tuple[tuple[Team, ...], frozenset[str], float]] = [
        ((), frozenset(), 0.0)
    ]
    expanded = 0

    for depth in range(team_count):
        remaining_team_slots = team_count - depth
        next_by_partition: dict[
            tuple[Team, ...], tuple[tuple[Team, ...], frozenset[str], float]
        ] = {}
        for teams, used, total in states:
            remaining = tuple(name for name in names if name not in used)
            if len(remaining) < team_size * remaining_team_slots:
                continue
            memberships, work = _membership_beam(
                remaining,
                score_by_character,
                team_size=team_size,
                beam_width=team_beam_width,
                partial_viable=partial_viable,
            )
            expanded += work

            viable = 0
            for raw_membership, proxy_score in memberships:
                # Re-canonicalize against the full roster so the same membership
                # has one cache/signature identity across residual states.
                membership = tuple(sorted(raw_membership, key=index.__getitem__))
                if not placements_for(membership, proxy_score):
                    continue
                viable += 1
                members = frozenset(membership)
                if members & used:
                    raise AssertionError("allocation beam emitted overlapping membership")
                new_teams = teams + (membership,)
                new_used = used | members
                new_total = total + float(proxy_score)
                signature = tuple(sorted(new_teams))
                previous = next_by_partition.get(signature)
                if previous is None or new_total > previous[2]:
                    next_by_partition[signature] = (new_teams, new_used, new_total)
                if viable >= team_options_per_state:
                    break

        ranked = sorted(
            next_by_partition.values(),
            key=lambda row: (-row[2], tuple(sorted(row[0]))),
        )
        states = ranked[:allocation_beam_width]
        if not states:
            break

    complete = [row for row in states if len(row[0]) == team_count]
    complete.sort(key=lambda row: (-row[2], tuple(sorted(row[0]))))
    complete = complete[:allocation_limit]
    allocations = tuple(
        GeneratedProxyAllocation(teams=teams, proxy_total=float(total))
        for teams, _used, total in complete
    )

    selected_memberships: list[Team] = []
    seen_memberships: set[Team] = set()
    for allocation in allocations:
        for membership in allocation.teams:
            if membership in seen_memberships:
                continue
            seen_memberships.add(membership)
            selected_memberships.append(membership)

    candidate_channels = tuple(
        placement_cache[membership]
        for membership in selected_memberships
        if placement_cache.get(membership)
    )
    rejected = sum(rejected_cache.values())
    return AllocationCandidateGenerationResult(
        candidates=_interleave_channels(candidate_channels),
        candidate_channels=candidate_channels,
        allocations=allocations,
        expanded_states=expanded,
        rejected_illegal=rejected,
    )
