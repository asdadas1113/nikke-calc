"""Search-budget guard around the expensive Moris evaluator.

A search budget counts actual ``simulate()`` calls, not evaluator requests.
Cached evaluations therefore remain free and usable even after the new-call
budget is exhausted. This module deliberately contains no candidate-discovery
policy; it only enforces an upper bound chosen by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .evaluator import Evaluation, EvaluatorStats, MorisEvaluator


class SearchBudgetExhausted(RuntimeError):
    """Raised when a cache miss would exceed the current simulate-call budget."""


@dataclass(frozen=True)
class SearchBudget:
    """Maximum number of new Moris ``simulate()`` calls for one search session."""

    max_simulate_calls: int

    def __post_init__(self) -> None:
        if self.max_simulate_calls < 0:
            raise ValueError("max_simulate_calls must be non-negative")


class BudgetedEvaluator:
    """Evaluator facade that enforces a delta simulate-call budget.

    The budget starts when this facade is created. Existing evaluator cache
    entries remain available at zero cost, which lets an anytime search resume
    from earlier work without re-paying for already-simulated teams.

    A BudgetedEvaluator may wrap another BudgetedEvaluator. This gives a stage a
    smaller local cap while the parent still enforces the whole-search cap. Both
    layers count the same underlying cumulative ``simulate_calls`` and cached
    requests remain free through every layer.
    """

    def __init__(
        self,
        evaluator: MorisEvaluator | "BudgetedEvaluator",
        budget: SearchBudget,
    ) -> None:
        self._evaluator = evaluator
        self.budget = budget
        self._start_simulate_calls = evaluator.stats.simulate_calls

    @property
    def stats(self) -> EvaluatorStats:
        """Expose underlying cumulative stats for existing pipeline metrics."""

        return self._evaluator.stats

    @property
    def used_simulate_calls(self) -> int:
        return self._evaluator.stats.simulate_calls - self._start_simulate_calls

    @property
    def remaining_simulate_calls(self) -> int:
        return max(0, self.budget.max_simulate_calls - self.used_simulate_calls)

    @property
    def exhausted(self) -> bool:
        return self.remaining_simulate_calls == 0

    def is_cached(
        self,
        members: Sequence[str],
        *,
        characters: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        enemy: Mapping[str, Any] | None = None,
        seed: int = 42,
        verbose: bool = False,
    ) -> bool:
        """Delegate cache identity/preflight without spending local budget."""

        return self._evaluator.is_cached(
            members,
            characters=characters,
            config=config,
            enemy=enemy,
            seed=seed,
            verbose=verbose,
        )

    def can_evaluate(
        self,
        members: Sequence[str],
        *,
        characters: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        enemy: Mapping[str, Any] | None = None,
        seed: int = 42,
        verbose: bool = False,
    ) -> bool:
        """Whether this layer permits the request or it is already cached."""

        if self.remaining_simulate_calls > 0:
            return True
        return self.is_cached(
            members,
            characters=characters,
            config=config,
            enemy=enemy,
            seed=seed,
            verbose=verbose,
        )

    def evaluate(
        self,
        members: Sequence[str],
        *,
        characters: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        enemy: Mapping[str, Any] | None = None,
        seed: int = 42,
        verbose: bool = False,
    ) -> Evaluation:
        """Evaluate unless doing so would add a simulate call beyond this layer."""

        if not self.can_evaluate(
            members,
            characters=characters,
            config=config,
            enemy=enemy,
            seed=seed,
            verbose=verbose,
        ):
            raise SearchBudgetExhausted(
                "search simulate-call budget exhausted; uncached evaluation rejected"
            )
        before = self._evaluator.stats.simulate_calls
        result = self._evaluator.evaluate(
            members,
            characters=characters,
            config=config,
            enemy=enemy,
            seed=seed,
            verbose=verbose,
        )
        spent = self._evaluator.stats.simulate_calls - before
        if spent not in (0, 1):
            raise RuntimeError("one evaluator request unexpectedly used multiple simulate calls")
        if self.used_simulate_calls > self.budget.max_simulate_calls:
            raise RuntimeError("search simulate-call budget was exceeded")
        return result
