"""Strict Pure-vs-Meta benchmark harness under equal new Moris call counts.

The comparison objective is final non-overlapping five-team damage, not proxy
recall. Two modes must therefore run from independent evaluator/cache instances
with the same ``CacheIdentity`` and the same caller-owned SearchBudget cap.
Sharing one evaluator would let the second mode consume the first mode's cache
for free and invalidate the comparison.

This module deliberately does not decide what Pure or Meta search means. Callers
provide two runners that each receive their own fresh evaluator and SearchBudget.
The harness verifies the resulting new ``simulate()`` call counts are actually
equal before exposing a damage delta.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

from .anytime import AnytimeSearchResult
from .budget import SearchBudget
from .evaluator import CacheIdentity, MorisEvaluator

SearchRunner = Callable[[MorisEvaluator, SearchBudget], AnytimeSearchResult]
EvaluatorFactory = Callable[[], MorisEvaluator]


class InvalidSameBudgetComparison(RuntimeError):
    """Raised when a requested comparison is not call-for-call comparable."""


@dataclass(frozen=True)
class SearchStageCalls:
    marginal: int
    candidate: int
    refinement: int
    unattributed: int

    @property
    def total(self) -> int:
        return self.marginal + self.candidate + self.refinement + self.unattributed


@dataclass(frozen=True)
class SearchRunMetrics:
    mode: str
    requested_budget: int
    simulate_calls: int
    runtime_s: float
    final_damage: float | None
    evaluated_candidate_count: int
    final_team_count: int
    stage_calls: SearchStageCalls


@dataclass(frozen=True)
class SameBudgetComparison:
    identity: CacheIdentity
    pure: SearchRunMetrics
    meta: SearchRunMetrics

    @property
    def simulate_calls(self) -> int:
        return self.pure.simulate_calls

    @property
    def damage_delta(self) -> float | None:
        """Meta minus Pure final damage, only when both produced allocations."""

        if self.pure.final_damage is None or self.meta.final_damage is None:
            return None
        return self.meta.final_damage - self.pure.final_damage

    @property
    def relative_damage_delta(self) -> float | None:
        """Relative Meta-minus-Pure delta; None when Pure has no positive score."""

        delta = self.damage_delta
        if delta is None or self.pure.final_damage is None or self.pure.final_damage <= 0:
            return None
        return delta / self.pure.final_damage


def _validate_fresh_evaluator(evaluator: MorisEvaluator, *, label: str) -> CacheIdentity:
    if not evaluator.use_cache:
        raise InvalidSameBudgetComparison(
            f"{label} evaluator must use an identity-partitioned cache"
        )
    identity = evaluator.cache_identity
    if identity is None:
        raise InvalidSameBudgetComparison(f"{label} evaluator has no CacheIdentity")
    if evaluator.stats.simulate_calls != 0 or evaluator.stats.requests != 0:
        raise InvalidSameBudgetComparison(
            f"{label} evaluator must be fresh before comparison"
        )
    if evaluator.cache_size != 0:
        raise InvalidSameBudgetComparison(
            f"{label} evaluator cache must start empty"
        )
    return identity


def _metrics(
    mode: str,
    result: AnytimeSearchResult,
    evaluator: MorisEvaluator,
    *,
    requested_budget: int,
    runtime_s: float,
) -> SearchRunMetrics:
    calls = evaluator.stats.simulate_calls
    if result.budget_used != calls:
        raise InvalidSameBudgetComparison(
            f"{mode} runner used evaluator calls outside its reported anytime budget: "
            f"result={result.budget_used}, evaluator={calls}"
        )

    known = (
        result.marginal_stage.simulate_calls
        + result.candidate_stage.simulate_calls
        + result.refinement_stage.simulate_calls
    )
    if known > calls:
        raise InvalidSameBudgetComparison(
            f"{mode} stage call accounting exceeds total simulate calls"
        )
    allocation = result.allocation
    return SearchRunMetrics(
        mode=mode,
        requested_budget=requested_budget,
        simulate_calls=calls,
        runtime_s=runtime_s,
        final_damage=None if allocation is None else allocation.total_score,
        evaluated_candidate_count=len(result.evaluated_candidates),
        final_team_count=0 if allocation is None else len(allocation.teams),
        stage_calls=SearchStageCalls(
            marginal=result.marginal_stage.simulate_calls,
            candidate=result.candidate_stage.simulate_calls,
            refinement=result.refinement_stage.simulate_calls,
            unattributed=calls - known,
        ),
    )


def run_same_budget_comparison(
    pure_evaluator_factory: EvaluatorFactory,
    meta_evaluator_factory: EvaluatorFactory,
    pure_runner: SearchRunner,
    meta_runner: SearchRunner,
    *,
    simulate_call_budget: int,
    require_complete_allocations: bool = True,
) -> SameBudgetComparison:
    """Run two independent searches and reject non-comparable outcomes.

    Equal budget *caps* are not sufficient: one mode may run out of candidates and
    spend fewer actual new calls. This harness therefore requires equal observed
    ``simulate_calls`` before returning a comparison. If a caller wants exactly N
    calls, both runners should be configured with enough candidate work to exhaust
    the supplied cap.

    Fresh evaluators are required so neither mode inherits warm-cache work. Their
    caches remain independent but must carry the same engine/account identity.
    ``require_complete_allocations`` additionally requires both modes to return
    the requested final team count as encoded by their respective result objects.
    """

    if simulate_call_budget < 0:
        raise ValueError("simulate_call_budget must be non-negative")

    pure_evaluator = pure_evaluator_factory()
    meta_evaluator = meta_evaluator_factory()
    if pure_evaluator is meta_evaluator:
        raise InvalidSameBudgetComparison(
            "Pure and Meta must use independent evaluator/cache instances"
        )

    pure_identity = _validate_fresh_evaluator(pure_evaluator, label="Pure")
    meta_identity = _validate_fresh_evaluator(meta_evaluator, label="Meta")
    if pure_identity != meta_identity:
        raise InvalidSameBudgetComparison(
            "Pure and Meta CacheIdentity must match exactly"
        )

    pure_budget = SearchBudget(simulate_call_budget)
    meta_budget = SearchBudget(simulate_call_budget)

    started = perf_counter()
    pure_result = pure_runner(pure_evaluator, pure_budget)
    pure_runtime = perf_counter() - started

    started = perf_counter()
    meta_result = meta_runner(meta_evaluator, meta_budget)
    meta_runtime = perf_counter() - started

    pure_metrics = _metrics(
        "pure",
        pure_result,
        pure_evaluator,
        requested_budget=simulate_call_budget,
        runtime_s=pure_runtime,
    )
    meta_metrics = _metrics(
        "meta",
        meta_result,
        meta_evaluator,
        requested_budget=simulate_call_budget,
        runtime_s=meta_runtime,
    )

    if pure_metrics.simulate_calls != meta_metrics.simulate_calls:
        raise InvalidSameBudgetComparison(
            "Pure and Meta used different numbers of new Moris simulate() calls: "
            f"pure={pure_metrics.simulate_calls}, meta={meta_metrics.simulate_calls}"
        )

    if require_complete_allocations:
        if pure_metrics.final_damage is None or meta_metrics.final_damage is None:
            raise InvalidSameBudgetComparison(
                "both modes must produce a final allocation for damage comparison"
            )
        if pure_metrics.final_team_count != meta_metrics.final_team_count:
            raise InvalidSameBudgetComparison(
                "Pure and Meta returned different final allocation team counts"
            )

    return SameBudgetComparison(
        identity=pure_identity,
        pure=pure_metrics,
        meta=meta_metrics,
    )
