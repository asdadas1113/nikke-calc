"""Local candidate refinement around already-promising simulated squads."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

Team = tuple[str, ...]
TeamValidator = Callable[[Team], bool]
PlacementResolver = Callable[[Team], Sequence[str]]


@dataclass(frozen=True)
class OneSwapNeighbor:
    """One member-set change from a parent squad.

    ``position`` records the parent slot that was replaced before an optional
    placement resolver ran. The final ordered ``members`` remain authoritative:
    Moris placement order matters and callers must not sort/deduplicate it away.
    """

    members: Team
    parent: Team
    position: int
    outgoing: str
    incoming: str

    def __post_init__(self) -> None:
        if len(self.members) != len(self.parent):
            raise ValueError("refinement neighbor must keep team size")
        if len(set(self.members)) != len(self.members):
            raise ValueError("refinement neighbor members must be unique")
        if not 0 <= self.position < len(self.parent):
            raise ValueError("refinement position is out of range")
        if self.parent[self.position] != self.outgoing:
            raise ValueError("outgoing member must match the parent replacement slot")
        if self.incoming in self.parent:
            raise ValueError("incoming member must be absent from the parent")
        if set(self.parent) - set(self.members) != {self.outgoing}:
            raise ValueError("neighbor must remove exactly the outgoing member")
        if set(self.members) - set(self.parent) != {self.incoming}:
            raise ValueError("neighbor must add exactly the incoming member")


def generate_one_swap_neighbors(
    seeds: Iterable[Sequence[str]],
    roster: Sequence[str],
    *,
    legal: TeamValidator | None = None,
    seen: Iterable[Sequence[str]] = (),
    positions: Sequence[int] | None = None,
    placement_resolver: PlacementResolver | None = None,
    max_new: int | None = None,
) -> list[OneSwapNeighbor]:
    """Generate deterministic one-member swap neighbors under a hard budget.

    This primitive intentionally does not decide *which* seeds, positions, or
    incoming characters are strategically important. Callers should order and
    restrict those inputs using already-measured scores, bottleneck analysis, or
    another explicit policy. That keeps this layer from silently becoming a
    broad ``roster x slots`` brute-force search.

    By default the replaced member keeps its slot. A placement resolver may
    deliberately reorder the resulting squad; this is useful for benchmark
    fixtures with a canonical placement convention. The final ordered tuple is
    used for ``seen``/deduplication because NIKKE placement order can affect the
    simulator result.
    """

    roster_order = tuple(roster)
    if len(set(roster_order)) != len(roster_order):
        raise ValueError("roster members must be unique")
    if max_new is not None and max_new < 0:
        raise ValueError("max_new must be non-negative or None")
    if max_new == 0:
        return []

    seen_keys = {tuple(team) for team in seen}
    emitted: set[Team] = set()
    result: list[OneSwapNeighbor] = []

    for raw_seed in seeds:
        parent = tuple(raw_seed)
        if not parent or len(set(parent)) != len(parent):
            raise ValueError("seed members must be non-empty and unique")

        chosen_positions = tuple(range(len(parent))) if positions is None else tuple(positions)
        for position in chosen_positions:
            if not 0 <= position < len(parent):
                raise ValueError("refinement position is out of range")

            outgoing = parent[position]
            for incoming in roster_order:
                if incoming in parent:
                    continue

                raw_members = list(parent)
                raw_members[position] = incoming
                members = tuple(raw_members)
                if placement_resolver is not None:
                    members = tuple(placement_resolver(members))

                if len(members) != len(parent) or len(set(members)) != len(members):
                    raise ValueError("placement_resolver must preserve unique team membership")
                if set(members) != set(raw_members):
                    raise ValueError("placement_resolver must not change team membership")
                if members in seen_keys or members in emitted:
                    continue
                if legal is not None and not legal(members):
                    continue

                result.append(
                    OneSwapNeighbor(
                        members=members,
                        parent=parent,
                        position=position,
                        outgoing=outgoing,
                        incoming=incoming,
                    )
                )
                emitted.add(members)
                if max_new is not None and len(result) >= max_new:
                    return result

    return result
