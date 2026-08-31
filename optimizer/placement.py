"""Score-blind ordering for bounded ordered-squad exploration.

Moris can care about squad order. Exposing every permutation is therefore safer
than pretending one canonical placement is exact, but a tight Moris-call budget
still needs a deterministic order in which those permutations are examined.

This module never assigns damage-like values and never removes a permutation. It
only reorders the complete permutation set so structurally different placements
are exposed earlier:

1. optional caller-supplied structural groups are rank-round-robin interleaved;
2. within each group, a greedy maximin Hamming order prefers placements whose
   slot assignments differ most from placements already exposed in that group.

For NIKKE automatic search, ``static_burst_priority_group_key`` can derive one
cheap grouping key from a legality object exposing ``inspect(team)`` in the same
shape as ``BurstStructureValidator``. This grouping is exploration-only. Runtime
dynamic burst overrides, positional skills, tie-breaking, and every other combat
rule still belong to Moris, so all permutations remain available eventually.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable, Sequence
from itertools import permutations

Team = tuple[str, ...]
PlacementGroupKey = Callable[[Team], Hashable]


def _hamming(left: Team, right: Team) -> int:
    if len(left) != len(right):
        raise ValueError("placement Hamming distance requires equal lengths")
    return sum(a != b for a, b in zip(left, right))


def _maximin_order(rows: Sequence[Team]) -> tuple[Team, ...]:
    """Keep the first row stable, then greedily maximize minimum slot distance.

    Ties preserve the original input order. Minimum distances are updated
    incrementally, making the work quadratic in group size rather than cubic.
    """

    ordered = tuple(rows)
    if len(ordered) <= 1:
        return ordered

    chosen: list[Team] = [ordered[0]]
    remaining: list[tuple[int, Team, int]] = [
        (index, row, _hamming(row, ordered[0]))
        for index, row in enumerate(ordered[1:], start=1)
    ]

    while remaining:
        pick_pos = max(
            range(len(remaining)),
            key=lambda pos: (remaining[pos][2], -remaining[pos][0]),
        )
        _original_index, picked, _distance = remaining.pop(pick_pos)
        chosen.append(picked)

        updated: list[tuple[int, Team, int]] = []
        for original_index, row, min_distance in remaining:
            updated.append(
                (
                    original_index,
                    row,
                    min(min_distance, _hamming(row, picked)),
                )
            )
        remaining = updated

    return tuple(chosen)


def diverse_grouped_permutation_placements(
    members: Sequence[str],
    *,
    group_key: PlacementGroupKey | None = None,
) -> tuple[Team, ...]:
    """Return every permutation once in score-blind structural-diversity order.

    ``group_key`` does not define equivalence or legality. It only determines
    exploration channels. Each channel keeps one stable first representative,
    then maximin slot diversity; channels themselves are rank-round-robin merged
    so one structural family cannot consume the whole early budget.
    """

    team = tuple(str(name) for name in members)
    if not team or len(set(team)) != len(team):
        raise ValueError("members must be non-empty and unique")

    raw = tuple(permutations(team))
    groups: OrderedDict[Hashable, list[Team]] = OrderedDict()
    for placement in raw:
        key: Hashable = None if group_key is None else group_key(placement)
        try:
            groups.setdefault(key, []).append(placement)
        except TypeError as exc:
            raise ValueError("placement group keys must be hashable") from exc

    channels = tuple(_maximin_order(rows) for rows in groups.values())
    out: list[Team] = []
    max_rank = max((len(channel) for channel in channels), default=0)
    for rank in range(max_rank):
        for channel in channels:
            if rank < len(channel):
                out.append(channel[rank])

    if len(out) != len(raw) or len(set(out)) != len(raw):
        raise AssertionError("diverse placement ordering lost or duplicated a permutation")
    return tuple(out)


def static_burst_priority_group_key(legal) -> PlacementGroupKey | None:
    """Build a static burst-priority grouping key from ``legal.inspect`` if present.

    ``BurstStructureValidator.inspect`` exposes candidates in squad input order
    for stages 1/2/3. Grouping by those ordered candidate lists therefore spreads
    different *static* burst priorities across the early placement budget.

    This is intentionally not a correctness signature. If inspection is absent,
    callers still get maximin slot diversity over one group. If runtime behavior
    changes burst stages or positional targeting matters, Moris remains final and
    later placements are still present in the returned complete permutation set.
    """

    inspect = getattr(legal, "inspect", None)
    if not callable(inspect):
        return None

    def key(team: Team) -> Hashable:
        report = inspect(team)
        eligible = getattr(report, "eligible_by_stage", None)
        if not isinstance(eligible, dict) and not hasattr(eligible, "get"):
            return ()
        return tuple(
            tuple(eligible.get(stage, ()))
            for stage in ("1", "2", "3")
        )

    return key
