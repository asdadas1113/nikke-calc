"""Simulation-free bounded candidate generation from measured marginal evidence.

The optimizer cannot enumerate every 5-member roster combination through Moris.
This module provides small, explicit beam primitives that use already-measured
per-character marginal values only to decide *where to look*.

No generated proxy value changes Moris damage or final allocation. Beam widths,
output limits, required-member cores, allocation depth, and placement expansion
are all caller-owned. The primitives make no claim that their output contains the
global optimum.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

Team = tuple[str, ...]
TeamValidator = Callable[[Team], bool]
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
    """One cheap non-overlapping multi-team path, never a final answer."""

    teams: tuple[Team, ...]
    proxy_total: float


@dataclass(frozen=True)
class AllocationCandidateGenerationResult:
    """Candidate union protected by bounded multi-team proxy search."""

    candidates: tuple[GeneratedCandidate, ...]
    allocations: tuple[GeneratedProxyAllocation, ...]
    expanded_states: int
    rejected_illegal: int

    @property
    def teams(self) -> tuple[Team, ...]:
        return tuple(row.members for row in self.candidates)


def _identity_placement(members: Team) -> tuple[Team, ...]:
    return (members,)


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
) -> tuple[tuple[GeneratedCandidate, ...], int, int]:
    if len(required_members) > team_size:
        return (), 0, 0

    index = {name: i for i, name in enumerate(roster)}
    required_set = frozenset(required_members)
    required_canonical = tuple(sorted(required_set, key=index.__getitem__))
    start_score = sum(float(score_by_character[name]) for name in required_canonical)
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
                candidate_score = score + float(score_by_character[name])
                previous = next_by_members.get(combined)
                if previous is None or candidate_score > previous:
                    next_by_members[combined] = candidate_score

        ranked = sorted(
            next_by_members.items(),
            key=lambda row: (-row[1], tuple(index[name] for name in row[0])),
        )
        states = [(members, score) for members, score in ranked[:beam_width]]

    placement_channels: list[tuple[GeneratedCandidate, ...]] = []
    rejected_illegal = 0
    for membership, proxy_score in states:
        if not required_set <= set(membership):
            raise AssertionError("beam lost required members")
        local: list[GeneratedCandidate] = []
        local_seen: set[Team] = set()
        for raw in placement_expander(membership):
            team = tuple(str(name) for name in raw)
            if len(team) != team_size or len(set(team)) != team_size or set(team) != set(membership):
                raise ValueError("placement_expander must return permutations of the membership team")
            if team in local_seen:
                continue
            local_seen.add(team)
            if legal is not None and not legal(team):
                rejected_illegal += 1
                continue
            local.append(
                GeneratedCandidate(
                    members=team,
                    proxy_score=float(proxy_score),
                    source=source,
                    required_members=required_members,
                )
            )
        if local:
            placement_channels.append(tuple(local))

    # A membership with many ordered variants must not consume the whole output
    # before the next membership gets one look. Placement variants therefore use
    # the same rank-round-robin rule as other discovery channels.
    emitted = _interleave_channels(placement_channels)
    return emitted[:limit], expanded, rejected_illegal


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
) -> CandidateGenerationResult:
    """Generate a bounded single-team universe without Moris calls.

    One global additive beam is available when ``global_limit > 0``. Optional
    ``required_cores`` run independent beams with those members fixed, then all
    channels are rank-round-robin unioned. This is discovery only; proxy scores
    are diagnostics and do not alter final Moris selection.
    """

    names = _validate_inputs(roster, score_by_character, team_size=team_size)
    if beam_width <= 0:
        raise ValueError("beam_width must be positive")
    if global_limit < 0 or per_core_limit < 0:
        raise ValueError("candidate limits must be non-negative")

    placement = placement_expander or _identity_placement
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
) -> AllocationCandidateGenerationResult:
    """Protect candidate teams from bounded non-overlap proxy allocations.

    Single-team Top-K can over-concentrate on the same high-proxy characters and
    leave the exact five-team allocator with too little disjoint supply. This
    primitive instead builds partial *allocations*. Each state chooses one legal
    team from the remaining roster, removes those members, and keeps only a
    caller-bounded number of highest additive-total states before the next team.

    The objective remains only the transparent sum of supplied character proxy
    values. There is no diversity bonus, meta bonus, or final-score modification.
    Returned allocations are search-coverage hypotheses; every final candidate
    still requires Moris evaluation later.
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
        return AllocationCandidateGenerationResult((), (), 0, 0)

    placement = placement_expander or _identity_placement
    # (teams, used members, additive total). Team order is construction order only;
    # final Solo Raid allocation itself is an unordered set of squads.
    states: list[tuple[tuple[Team, ...], frozenset[str], float]] = [
        ((), frozenset(), 0.0)
    ]
    expanded = 0
    rejected = 0

    for depth in range(team_count):
        remaining_team_slots = team_count - depth
        next_by_partition: dict[
            tuple[Team, ...], tuple[tuple[Team, ...], frozenset[str], float]
        ] = {}
        for teams, used, total in states:
            remaining = tuple(name for name in names if name not in used)
            if len(remaining) < team_size * remaining_team_slots:
                continue
            options, work, bad = _beam_channel(
                remaining,
                score_by_character,
                team_size=team_size,
                beam_width=team_beam_width,
                limit=team_options_per_state,
                required_members=(),
                source="additive-allocation-beam",
                legal=legal,
                placement_expander=placement,
            )
            expanded += work
            rejected += bad
            for option in options:
                members = frozenset(option.members)
                if members & used:
                    raise AssertionError("allocation beam emitted overlapping team")
                new_teams = teams + (option.members,)
                new_used = used | members
                new_total = total + option.proxy_score
                # Selecting the same squads in a different construction order is
                # the same allocation. Ordered identity inside each squad remains.
                signature = tuple(sorted(new_teams))
                previous = next_by_partition.get(signature)
                if previous is None or new_total > previous[2]:
                    next_by_partition[signature] = (new_teams, new_used, new_total)

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

    channels: list[tuple[GeneratedCandidate, ...]] = []
    for index, allocation in enumerate(allocations):
        channels.append(
            tuple(
                GeneratedCandidate(
                    members=team,
                    proxy_score=sum(float(score_by_character[name]) for name in team),
                    source=f"additive-allocation-beam:{index}",
                    required_members=(),
                )
                for team in allocation.teams
            )
        )

    return AllocationCandidateGenerationResult(
        candidates=_interleave_channels(channels),
        allocations=allocations,
        expanded_states=expanded,
        rejected_illegal=rejected,
    )
