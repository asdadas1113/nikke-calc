"""Selective pair/core interaction probes for proxy refinement.

This module deliberately does not enumerate character pairs. Callers must choose
specific pair probes from an observed recall failure, a known skill interaction,
or another explicit hypothesis. The expensive Moris evaluator is then used only
for those probes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .evaluator import MorisEvaluator

TeamLegal = Callable[[tuple[str, ...]], bool]


@dataclass(frozen=True)
class PairSynergyProbe:
    """One four-point interaction measurement around a fixed reference team.

    ``pair[0]`` replaces ``positions[0]`` and ``pair[1]`` replaces
    ``positions[1]``. Reversing the placement is a separate explicit probe; this
    matters because NIKKE squad order can affect operation.
    """

    pair: tuple[str, str]
    reference: tuple[str, ...]
    positions: tuple[int, int]
    source: str = "failure"

    def __post_init__(self) -> None:
        if len(self.pair) != 2 or self.pair[0] == self.pair[1]:
            raise ValueError("pair must contain two distinct characters")
        if not self.reference or len(set(self.reference)) != len(self.reference):
            raise ValueError("reference must contain unique members")
        if any(name in self.reference for name in self.pair):
            raise ValueError("pair members must be absent from the reference")
        if len(self.positions) != 2 or self.positions[0] == self.positions[1]:
            raise ValueError("positions must contain two distinct indices")
        if any(index < 0 or index >= len(self.reference) for index in self.positions):
            raise ValueError("probe position is outside the reference team")

    @property
    def replaced(self) -> tuple[str, str]:
        return (
            self.reference[self.positions[0]],
            self.reference[self.positions[1]],
        )

    def first_only(self) -> tuple[str, ...]:
        trial = list(self.reference)
        trial[self.positions[0]] = self.pair[0]
        return tuple(trial)

    def second_only(self) -> tuple[str, ...]:
        trial = list(self.reference)
        trial[self.positions[1]] = self.pair[1]
        return tuple(trial)

    def paired(self) -> tuple[str, ...]:
        trial = list(self.reference)
        trial[self.positions[0]] = self.pair[0]
        trial[self.positions[1]] = self.pair[1]
        return tuple(trial)


@dataclass(frozen=True)
class PairSynergyObservation:
    probe: PairSynergyProbe
    baseline_score: float
    first_only_score: float
    second_only_score: float
    paired_score: float

    @property
    def interaction_delta(self) -> float:
        """Second-order interaction after subtracting both single replacements."""
        return (
            self.paired_score
            - self.first_only_score
            - self.second_only_score
            + self.baseline_score
        )


def measure_pair_probes(
    evaluator: MorisEvaluator,
    probes: Iterable[PairSynergyProbe],
    *,
    legal: TeamLegal | None = None,
    evaluate_kwargs: dict | None = None,
) -> tuple[PairSynergyObservation, ...]:
    """Evaluate only explicitly supplied four-point interaction probes.

    For reference ``R`` and replacements ``A``/``B`` the measured interaction is::

        D(R+A+B) - D(R+A) - D(R+B) + D(R)

    The four squads use the exact same reference slots, so the residual is not
    contaminated by choosing a different best replacement position for each
    character. Evaluator caching naturally shares duplicate baseline/single teams
    across probes.

    A supplied probe that violates the caller's hard legality predicate raises an
    error instead of being silently skipped: probes are intentionally scarce and
    hypothesis-driven, so an invalid hypothesis should be visible.
    """
    kwargs = dict(evaluate_kwargs or {})
    observations: list[PairSynergyObservation] = []

    for probe in probes:
        variants = (
            probe.reference,
            probe.first_only(),
            probe.second_only(),
            probe.paired(),
        )
        for team in variants:
            if len(set(team)) != len(team):
                raise ValueError(f"probe creates duplicate members: {team}")
            if legal is not None and not legal(team):
                raise ValueError(f"probe creates an illegal team: {team}")

        baseline, first, second, paired = (
            evaluator.evaluate(team, **kwargs).score for team in variants
        )
        observations.append(
            PairSynergyObservation(
                probe=probe,
                baseline_score=float(baseline),
                first_only_score=float(first),
                second_only_score=float(second),
                paired_score=float(paired),
            )
        )

    return tuple(observations)
