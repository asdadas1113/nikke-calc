"""Reference-team marginal measurements for cheap proxy construction."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Callable, Iterable, Sequence

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


def measure_marginals(
    evaluator: MorisEvaluator,
    roster: Iterable[str],
    reference_teams: Iterable[Sequence[str]],
    *,
    legal: TeamLegal | None = None,
    evaluate_kwargs: dict | None = None,
) -> dict[str, MarginalValue]:
    """Measure best one-for-one substitution value on several references.

    This is intentionally simple: it is a measurement primitive, not candidate
    generation policy.  Later stages can restrict replaceable slots or select
    only promising candidates before calling it.
    """
    kwargs = dict(evaluate_kwargs or {})
    refs = [tuple(team) for team in reference_teams]
    baselines = {team: evaluator.evaluate(team, **kwargs).score for team in refs}
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
                score = evaluator.evaluate(trial_tuple, **kwargs).score
                obs = MarginalObservation(
                    candidate, reference, replaced, baselines[reference], score
                )
                if best is None or obs.delta > best.delta:
                    best = obs
            if best is not None:
                observations[candidate].append(best)

    out: dict[str, MarginalValue] = {}
    for candidate, rows in observations.items():
        if not rows:
            continue
        deltas = [row.delta for row in rows]
        out[candidate] = MarginalValue(
            candidate=candidate,
            mean_delta=fmean(deltas),
            best_delta=max(deltas),
            observations=tuple(rows),
        )
    return out
