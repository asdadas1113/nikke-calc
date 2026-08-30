"""Cheap hard constraints applied before any expensive simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

TeamValidator = Callable[[tuple[str, ...]], bool]


@dataclass(frozen=True)
class ConstraintSet:
    """Optimizer-side hard constraints.

    Burst/cooldown semantics stay pluggable rather than being reimplemented here;
    a Moris-backed validator can be added once its canonical metadata mapping is
    wired.  This keeps the calculator engine the source of truth.
    """

    team_size: int = 5
    include: frozenset[str] = field(default_factory=frozenset)
    exclude: frozenset[str] = field(default_factory=frozenset)
    validators: tuple[TeamValidator, ...] = ()

    def validate_team(self, members: Sequence[str]) -> bool:
        team = tuple(members)
        member_set = set(team)
        if len(team) != self.team_size or len(member_set) != len(team):
            return False
        if not self.include.issubset(member_set):
            return False
        if self.exclude.intersection(member_set):
            return False
        return all(validator(team) for validator in self.validators)


def teams_are_disjoint(teams: Iterable[Sequence[str]]) -> bool:
    used: set[str] = set()
    for team in teams:
        ordered = tuple(team)
        members = set(ordered)
        if len(members) != len(ordered) or used.intersection(members):
            return False
        used.update(members)
    return True
