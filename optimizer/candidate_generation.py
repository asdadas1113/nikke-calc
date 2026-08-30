"""Simulation-free bounded candidate generation from measured marginal evidence.

The optimizer cannot enumerate every 5-member roster combination through Moris.
This module provides a deliberately small primitive that uses already-measured
per-character marginal values only to decide *where to look*.

No generated proxy value changes Moris damage or final allocation. Beam width,
output limit, required-member cores, and placement expansion are all caller-owned.
The primitive makes no claim that its output contains the global optimum.
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


def _identity_placement(members: Team) -> tuple[Team, ...]:
    return (members,)


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

    emitted: list[GeneratedCandidate] = []
    seen: set[Team] = set()
    rejected_illegal = 0
    for membership, proxy_score in states:
        if not required_set <= set(membership):
            raise AssertionError("beam lost required members")
        for raw in placement_expander(membership):
            team = tuple(str(name) for name in raw)
            if len(team) != team_size or len(set(team)) != team_size or set(team) != set(membership):
                raise ValueError("placement_expander must return permutations of the membership team")
            if team in seen:
                continue
            if legal is not None and not legal(team):
                rejected_illegal += 1
                continue
            seen.add(team)
            emitted.append(
                GeneratedCandidate(
                    members=team,
                    proxy_score=float(proxy_score),
                    source=source,
                    required_members=required_members,
                )
            )
            if len(emitted) >= limit:
                return tuple(emitted), expanded, rejected_illegal

    return tuple(emitted), expanded, rejected_illegal


def _interleave_channels(
    channels: Sequence[Sequence[GeneratedCandidate]],
) -> tuple[GeneratedCandidate, ...]:
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
    """Generate a bounded team universe without Moris calls.

    One global additive beam is always available when ``global_limit > 0``.
    Optional ``required_cores`` run independent beams with those members fixed,
    then all channels are rank-round-robin unioned so global proxy candidates do
    not automatically consume the entire generated universe before core coverage.

    This is discovery only. ``proxy_score`` is the sum of the supplied character
    scores and is returned for diagnostics; callers remain free to recompute other
    proxy views before actual Moris evaluation.
    """

    names = tuple(str(name) for name in roster)
    if not names or len(set(names)) != len(names):
        raise ValueError("roster must contain unique members")
    if team_size <= 0:
        raise ValueError("team_size must be positive")
    if team_size > len(names):
        raise ValueError("team_size cannot exceed roster size")
    if beam_width <= 0:
        raise ValueError("beam_width must be positive")
    if global_limit < 0 or per_core_limit < 0:
        raise ValueError("candidate limits must be non-negative")

    missing_scores = tuple(name for name in names if name not in score_by_character)
    if missing_scores:
        raise ValueError(f"missing character proxy scores: {missing_scores}")

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
