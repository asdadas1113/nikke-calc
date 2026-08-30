"""Reference-team marginal measurements for cheap proxy construction."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Callable, Iterable, Sequence

from .budget import SearchBudgetExhausted
from .candidates import CandidateTeam
from .evaluator import MorisEvaluator

TeamLegal = Callable[[tuple[str, ...]], bool]
PositionPriority = Callable[[str, tuple[str, ...], int, str], object]


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
class CandidateMarginalPlanEntry:
    """One candidate measured in one chosen reference context.

    ``positions`` is an ordered list of reference slots to probe. The planner is
    intentionally score-blind: callers may supply a cheap structural priority,
    but actual Moris results never influence which context/slots enter the plan.
    """

    candidate: str
    reference: tuple[str, ...]
    positions: tuple[int, ...]


@dataclass(frozen=True)
class CandidateMarginalPlan:
    """Deterministic candidate-specific marginal work plan.

    Each planned candidate uses at most one reference team. Reference assignment
    is load-balanced using only hard legality and input order, so the plan is
    reproducible without oracle damage scores. ``unplanned_candidates`` records
    characters for which no legal one-slot substitution exists in any reference.
    """

    reference_teams: tuple[tuple[str, ...], ...]
    entries: tuple[CandidateMarginalPlanEntry, ...]
    unplanned_candidates: tuple[str, ...] = ()

    @property
    def planned_probe_count(self) -> int:
        return sum(len(entry.positions) for entry in self.entries)

    @property
    def used_reference_teams(self) -> tuple[tuple[str, ...], ...]:
        used = {entry.reference for entry in self.entries}
        return tuple(reference for reference in self.reference_teams if reference in used)


@dataclass(frozen=True)
class MarginalMeasurement:
    """Marginal values plus every ordered team already measured by Moris.

    ``evaluated_candidates`` contains reference baselines and all legal one-slot
    trials actually requested from the evaluator. They are safe to feed into
    the evaluated candidate pool when the same evaluator/account/config is
    retained: subsequent evaluation becomes a cache hit instead of another
    expensive ``simulate()`` call.

    The planning fields are populated by budget-aware planned measurement and
    stay at their compatibility defaults for the legacy all-context path.
    """

    values: dict[str, MarginalValue]
    evaluated_candidates: tuple[CandidateTeam, ...]
    planned_probe_count: int | None = None
    evaluated_probe_count: int | None = None
    budget_exhausted: bool = False
    unobserved_candidates: tuple[str, ...] = ()

    @property
    def plan_complete(self) -> bool | None:
        if self.planned_probe_count is None or self.evaluated_probe_count is None:
            return None
        return (
            not self.budget_exhausted
            and self.evaluated_probe_count == self.planned_probe_count
            and not self.unobserved_candidates
        )


def _normalize_references(reference_teams: Iterable[Sequence[str]]) -> tuple[tuple[str, ...], ...]:
    refs: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for raw in reference_teams:
        team = tuple(raw)
        if not team or len(set(team)) != len(team):
            raise ValueError("reference teams must be non-empty with unique members")
        if team in seen:
            continue
        seen.add(team)
        refs.append(team)
    if not refs:
        raise ValueError("reference_teams must not be empty")
    return tuple(refs)


def plan_candidate_specific_marginals(
    roster: Iterable[str],
    reference_teams: Iterable[Sequence[str]],
    *,
    positions_per_candidate: int = 2,
    legal: TeamLegal | None = None,
    position_priority: PositionPriority | None = None,
) -> CandidateMarginalPlan:
    """Build a score-blind, near-linear marginal probe plan.

    For each roster character, choose exactly one reference team that does not
    already contain it and has at least one legal one-slot substitution. Eligible
    references are assigned to the currently least-loaded context, with original
    reference order as a deterministic tie-break. Within that context, legal
    replacement slots are ordered by ``position_priority`` (then slot index) and
    capped by ``positions_per_candidate``.

    The default slot order is simply left-to-right. NIKKE-specific experiments
    can prefer same-burst or other structural slots by passing a callback without
    baking that heuristic into this generic measurement layer.
    """

    if positions_per_candidate <= 0:
        raise ValueError("positions_per_candidate must be positive")
    names = tuple(roster)
    if len(set(names)) != len(names):
        raise ValueError("roster members must be unique")
    refs = _normalize_references(reference_teams)
    loads = [0] * len(refs)
    entries: list[CandidateMarginalPlanEntry] = []
    unplanned: list[str] = []

    for candidate in names:
        options: list[tuple[int, tuple[int, ...]]] = []
        for ref_index, reference in enumerate(refs):
            if candidate in reference:
                continue
            legal_positions: list[int] = []
            for index, replaced in enumerate(reference):
                trial = list(reference)
                trial[index] = candidate
                trial_tuple = tuple(trial)
                if len(set(trial_tuple)) != len(trial_tuple):
                    continue
                if legal is not None and not legal(trial_tuple):
                    continue
                legal_positions.append(index)
            if not legal_positions:
                continue
            if position_priority is not None:
                legal_positions.sort(
                    key=lambda index: (
                        position_priority(candidate, reference, index, reference[index]),
                        index,
                    )
                )
            options.append((ref_index, tuple(legal_positions[:positions_per_candidate])))

        if not options:
            unplanned.append(candidate)
            continue

        ref_index, positions = min(options, key=lambda row: (loads[row[0]], row[0]))
        loads[ref_index] += 1
        entries.append(
            CandidateMarginalPlanEntry(
                candidate=candidate,
                reference=refs[ref_index],
                positions=positions,
            )
        )

    return CandidateMarginalPlan(
        reference_teams=refs,
        entries=tuple(entries),
        unplanned_candidates=tuple(unplanned),
    )


def _values_from_rows(
    observations: dict[str, list[MarginalObservation]],
) -> dict[str, MarginalValue]:
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
    return values


def measure_planned_marginals_with_candidates(
    evaluator: MorisEvaluator,
    plan: CandidateMarginalPlan,
    *,
    evaluate_kwargs: dict | None = None,
) -> MarginalMeasurement:
    """Execute a candidate-specific plan, stopping cleanly at SearchBudget.

    Reference baselines are attempted first. Probe depth is then round-robin:
    every candidate's first slot is attempted before any candidate's second slot.
    Therefore increasing a simulate-call budget extends the same deterministic
    work prefix rather than changing earlier choices, which is useful for anytime
    search modes.

    If a ``BudgetedEvaluator`` rejects an uncached request, later requests are
    still attempted so pre-existing cache hits remain reusable at zero cost. The
    returned measurement explicitly reports incomplete coverage instead of
    inventing values for unmeasured candidates.
    """

    kwargs = dict(evaluate_kwargs or {})
    measured: dict[tuple[str, ...], CandidateTeam] = {}
    baselines: dict[tuple[str, ...], float] = {}
    best_by_context: dict[tuple[str, tuple[str, ...]], MarginalObservation] = {}
    evaluated_probes = 0
    budget_exhausted = False

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

    for reference in plan.used_reference_teams:
        try:
            baselines[reference] = evaluate(reference, "marginal-reference")
        except SearchBudgetExhausted:
            budget_exhausted = True

    max_depth = max((len(entry.positions) for entry in plan.entries), default=0)
    for depth in range(max_depth):
        for entry in plan.entries:
            if depth >= len(entry.positions) or entry.reference not in baselines:
                continue
            index = entry.positions[depth]
            trial = list(entry.reference)
            replaced = trial[index]
            trial[index] = entry.candidate
            trial_tuple = tuple(trial)
            try:
                score = evaluate(trial_tuple, "marginal-trial")
            except SearchBudgetExhausted:
                budget_exhausted = True
                continue
            evaluated_probes += 1
            obs = MarginalObservation(
                candidate=entry.candidate,
                reference=entry.reference,
                replaced=replaced,
                baseline_score=baselines[entry.reference],
                trial_score=score,
            )
            context = (entry.candidate, entry.reference)
            previous = best_by_context.get(context)
            if previous is None or obs.delta > previous.delta:
                best_by_context[context] = obs

    observations: dict[str, list[MarginalObservation]] = {
        entry.candidate: [] for entry in plan.entries
    }
    for (candidate, _reference), obs in best_by_context.items():
        observations[candidate].append(obs)

    unobserved = list(plan.unplanned_candidates)
    unobserved.extend(
        entry.candidate
        for entry in plan.entries
        if not observations.get(entry.candidate)
    )
    return MarginalMeasurement(
        values=_values_from_rows(observations),
        evaluated_candidates=tuple(measured.values()),
        planned_probe_count=plan.planned_probe_count,
        evaluated_probe_count=evaluated_probes,
        budget_exhausted=budget_exhausted,
        unobserved_candidates=tuple(dict.fromkeys(unobserved)),
    )


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
    refs = list(_normalize_references(reference_teams))
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

    return MarginalMeasurement(
        values=_values_from_rows(observations),
        evaluated_candidates=tuple(measured.values()),
    )


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
