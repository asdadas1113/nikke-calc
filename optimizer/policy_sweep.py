"""Compare multiple search policies under identical NEW Moris-call counts.

Search-width tuning must not be decided by intuition or by giving one policy more
simulator work. This harness generalizes the existing Pure-vs-Meta same-budget
contract to an arbitrary named policy set:

- every policy receives a fresh independent evaluator/cache;
- every evaluator must carry the same CacheIdentity;
- every policy receives the same requested SearchBudget cap;
- results are exposed only when the *observed* new simulate() call counts match;
- optional completeness checks require every policy to return the same non-zero
  final team count.

The harness does not rank policies by a heuristic. Callers can compare final Moris
damage, runtime, evaluated candidate counts, and stage call allocation directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter

from .budget import SearchBudget
from .same_budget import (
    EvaluatorFactory,
    InvalidSameBudgetComparison,
    SearchRunMetrics,
    SearchRunner,
    _metrics,
    _validate_fresh_evaluator,
)
from .evaluator import CacheIdentity


@dataclass(frozen=True)
class EqualBudgetPolicySweep:
    identity: CacheIdentity
    simulate_calls: int
    runs: tuple[SearchRunMetrics, ...]

    def by_name(self) -> dict[str, SearchRunMetrics]:
        return {row.mode: row for row in self.runs}


def run_equal_budget_policy_sweep(
    evaluator_factory: EvaluatorFactory,
    runners: Mapping[str, SearchRunner],
    *,
    simulate_call_budget: int,
    require_complete_allocations: bool = True,
) -> EqualBudgetPolicySweep:
    """Run named policies independently and reject non-comparable outcomes."""

    if simulate_call_budget < 0:
        raise ValueError("simulate_call_budget must be non-negative")
    if len(runners) < 2:
        raise ValueError("policy sweep requires at least two named runners")
    names = tuple(str(name) for name in runners)
    if any(not name.strip() for name in names):
        raise ValueError("policy names must be non-empty")
    if len(set(names)) != len(names):
        raise ValueError("policy names must be unique")

    identity: CacheIdentity | None = None
    metrics_rows: list[SearchRunMetrics] = []

    for name, runner in runners.items():
        evaluator = evaluator_factory()
        current_identity = _validate_fresh_evaluator(evaluator, label=name)
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise InvalidSameBudgetComparison(
                "all policy evaluators must use the same CacheIdentity"
            )

        budget = SearchBudget(simulate_call_budget)
        started = perf_counter()
        result = runner(evaluator, budget)
        runtime_s = perf_counter() - started
        metrics_rows.append(
            _metrics(
                name,
                result,
                evaluator,
                requested_budget=simulate_call_budget,
                runtime_s=runtime_s,
            )
        )

    if identity is None:
        raise AssertionError("policy sweep identity was not initialized")

    observed = {row.simulate_calls for row in metrics_rows}
    if len(observed) != 1:
        detail = ", ".join(
            f"{row.mode}={row.simulate_calls}" for row in metrics_rows
        )
        raise InvalidSameBudgetComparison(
            "policy variants used different numbers of new Moris simulate() calls: "
            + detail
        )
    simulate_calls = next(iter(observed))

    if require_complete_allocations:
        if any(row.final_damage is None for row in metrics_rows):
            raise InvalidSameBudgetComparison(
                "every policy must produce a final allocation for comparison"
            )
        team_counts = {row.final_team_count for row in metrics_rows}
        if len(team_counts) != 1 or next(iter(team_counts)) <= 0:
            detail = ", ".join(
                f"{row.mode}={row.final_team_count}" for row in metrics_rows
            )
            raise InvalidSameBudgetComparison(
                "policy variants returned different/incomplete final team counts: "
                + detail
            )

    return EqualBudgetPolicySweep(
        identity=identity,
        simulate_calls=simulate_calls,
        runs=tuple(metrics_rows),
    )
