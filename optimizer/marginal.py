"""Reference-team marginal measurements for cheap proxy construction."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Callable, Iterable, Sequence

from .candidates import CandidateTeam
from .evaluator import MorisEvaluator

TeamLegal = Callable[[tuple[str, ...]], bool]


@dataclass(frozen=True)
class MarginalObservation:
    candidate: str
    reference: tuple[str, ...]
    replaced: str
    baseline_score: float
    trial_score: float

    @property
    def delta(self) -> float:
        return self.trial_score - self.baseline_score


@dataclass(frozen=True)
class MarginalValue:
    candidate: str
    mean_delta: float
    best_delta: float
    observations: tuple[MarginalObservation, ...]


@dataclass(frozen=True)
class MarginalMeasurement:
    """Marginal values plus every ordered team already measured by Moris.

    ``evaluated_candidates`` contains reference baselines and all legal one-slot
    trials actually requested from the evaluator. They are safe to feed into
    the evaluated candidate pool when the same evaluator/account/config is
    retained: subsequent evaluation becomes a cache hit instead of another
    expensive ``simulate()`` call.
    """

    values: dict[str, MarginalValue]
    evaluated_candidates: tuple[CandidateTeam, ...]


def measure_marginals_with_candidates(
    evaluator: MorisEvaluator,
    roster: Iterable[str],
    reference_teams: Iterable[Sequence[str]],
    *,
    legal: TeamLegal | None = None,
    evaluate_kwargs: dict | None = None,
) -> MarginalMeasurement:
    """Measure marginals and retain every already-simulated ordered team.

    This does not change which substitutions are evaluated. It only stops
    throwing away their simulator scores after marginal deltas are computed.
    Ordered placement is preserved exactly and duplicate ordered teams are
    emitted once.
    """

    kwargs = dict(evaluate_kwargs or {})
    refs = [tuple(team) for team in reference_teams]
    measured: dict[tuple[str, ...], CandidateTeam] = {}

    def evaluate(team: tuple[str, ...], source: str) -> float:
        result = evaluator.evaluate(team, **kwargs)
        measured.setdefault(
            team,
            CandidateTeam(
                members=team,
                proxy_score=result.score,
                simulated_score=result.score,
                source=source,
            ),
        )
        return result.score

    baselines = {team: evaluate(team, "marginal-reference") for team in refs}
    observations: dict[str, list[MarginalObservation]] = {name: [] for name in roster}

    for candidate in observations:
        for reference in refs:
            if candidate in reference:
                continue
            best: MarginalObservation | None = None
            for index, replaced in enumerate(reference):
                trial = list(reference)
                trial[index] = candidate
                trial_tuple = tuple(trial)
                if len(set(trial_tuple)) != len(trial_tuple):
                    continue
                if legal is not None and not legal(trial_tuple):
                    continue
                score = evaluate(trial_tuple, "marginal-trial")
                obs = MarginalObservation(
                    candidate, reference, replaced, baselines[reference], score
                )
                if best is None or obs.delta > best.delta:
                    best = obs
            if best is not None:
                observations[candidate].append(best)

    values: dict[str, MarginalValue] = {}
    for candidate, rows in observations.items():
        if not rows:
            continue
        deltas = [row.delta for row in rows]
        values[candidate] = MarginalValue(
            candidate=candidate,
            mean_delta=fmean(deltas),
            best_delta=max(deltas),
            observations=tuple(rows),
        )
    return MarginalMeasurement(values=values, evaluated_candidates=tuple(measured.values()))


def measure_marginals(
    evaluator: MorisEvaluator,
    roster: Iterable[str],
    reference_teams: Iterable[Sequence[str]],
    *,
    legal: TeamLegal | None = None,
    evaluate_kwargs: dict | None = None,
) -> dict[str, MarginalValue]:
    """Measure best one-for-one substitution value on several references.

    Backward-compatible value-only wrapper. New orchestration that wants to
    reuse already-simulated marginal teams should call
    :func:`measure_marginals_with_candidates`.
    """

    return measure_marginals_with_candidates(
        evaluator,
        roster,
        reference_teams,
        legal=legal,
        evaluate_kwargs=evaluate_kwargs,
    ).values
