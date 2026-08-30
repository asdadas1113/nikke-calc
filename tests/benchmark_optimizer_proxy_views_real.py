"""Real-Moris benchmark for preserving divergent marginal proxy views.

The full two-slot candidate-specific marginal plan is measured once.  From those
same simulator results this benchmark constructs two discovery views:

- first: the first planned replacement-slot delta;
- best-two: the larger delta across the first two planned slots.

Top-K is selected independently in each view with a single candidate-universe
scan, unioned, then evaluated with the same MorisEvaluator so marginal overlap is
cache-reused.  This tests candidate survival/diversity, not a new damage model.
"""

from __future__ import annotations

from context import spec as char_spec
from optimizer.constraints import BurstStructureValidator, ConstraintSet
from optimizer.evaluator import MorisEvaluator
from optimizer.marginal import (
    measure_planned_marginals_with_candidates,
    plan_candidate_specific_marginals,
)
from optimizer.proxy_views import ProxyView, select_proxy_view_candidates
from optimizer.validation import enumerate_legal_teams

ENGINE_COMMIT = "fb2fd9157aa14499daf6b9f185beb685d4393f90"
ACCOUNT_SNAPSHOT = "benchmark-default-build-2026-08-30"
ROSTER = (
    "리타", "볼륨", "크라운", "나가", "홍련", "앨리스", "모더니아", "레드 후드"
)
REFERENCE_VARIANTS = {
    "minimal-3": (
        ("리타", "크라운", "홍련", "앨리스", "모더니아"),
        ("볼륨", "나가", "홍련", "앨리스", "레드 후드"),
        ("리타", "볼륨", "나가", "모더니아", "레드 후드"),
    ),
    "balanced-6": (
        ("리타", "크라운", "나가", "앨리스", "모더니아"),
        ("볼륨", "나가", "홍련", "모더니아", "레드 후드"),
        ("리타", "볼륨", "홍련", "앨리스", "레드 후드"),
        ("리타", "볼륨", "크라운", "홍련", "모더니아"),
        ("리타", "크라운", "나가", "홍련", "레드 후드"),
        ("볼륨", "크라운", "앨리스", "모더니아", "레드 후드"),
    ),
}
EVALUATE_KWARGS = {
    "config": {"duration": 180},
    "enemy": {"def": 31_784, "code": "", "core_px": 0.0, "has_parts": False},
    "seed": 42,
    "verbose": False,
}
TRUE_TOP5 = (
    ("리타", "크라운", "홍련", "앨리스", "모더니아"),
    ("볼륨", "크라운", "홍련", "앨리스", "모더니아"),
    ("리타", "크라운", "나가", "앨리스", "레드 후드"),
    ("리타", "크라운", "홍련", "앨리스", "레드 후드"),
    ("리타", "볼륨", "크라운", "앨리스", "레드 후드"),
)
TRUE_TOP5_SET = set(TRUE_TOP5)


def same_burst_first(candidate, reference, index, replaced):
    candidate_stage = char_spec.burst_stage(candidate)
    replaced_stage = char_spec.burst_stage(replaced)
    same = candidate_stage == "A" or replaced_stage == "A" or candidate_stage == replaced_stage
    return (0 if same else 1, index)


def view_values(plan, score_map):
    first = {}
    best_two = {}
    for entry in plan.entries:
        baseline = score_map[entry.reference]
        deltas = []
        for index in entry.positions:
            trial = list(entry.reference)
            trial[index] = entry.candidate
            deltas.append(score_map[tuple(trial)] - baseline)
        if not deltas:
            continue
        first[entry.candidate] = deltas[0]
        best_two[entry.candidate] = max(deltas[:2])
    return first, best_two


def run_variant(name, references, constraints, legal_teams):
    plan = plan_candidate_specific_marginals(
        ROSTER,
        references,
        positions_per_candidate=2,
        legal=constraints,
        position_priority=same_burst_first,
    )
    evaluator = MorisEvaluator.from_moris(
        engine_commit=ENGINE_COMMIT,
        account_snapshot=ACCOUNT_SNAPSHOT,
        use_cache=True,
    )
    measured = measure_planned_marginals_with_candidates(
        evaluator,
        plan,
        evaluate_kwargs=EVALUATE_KWARGS,
    )
    if not measured.plan_complete:
        raise RuntimeError("two-probe marginal plan did not complete")

    score_map = {item.members: item.simulated_score for item in measured.evaluated_candidates}
    first, best_two = view_values(plan, score_map)
    marginal_calls = evaluator.stats.simulate_calls

    print(f"=== {name} multi-view candidate union ===")
    print(f"marginal_calls={marginal_calls}")
    for limit in (8, 10, 12):
        selected = select_proxy_view_candidates(
            iter(legal_teams),
            (ProxyView("first", first), ProxyView("best-two", best_two)),
            limit_per_view=limit,
            legal=constraints,
        )
        keys = {item.members for item in selected}
        survival_recall = len(keys & TRUE_TOP5_SET) / 5
        overlap_both = sum(len(item.hits) > 1 for item in selected)

        before = evaluator.stats.simulate_calls
        actual = []
        for item in selected:
            result = evaluator.evaluate(item.members, **EVALUATE_KWARGS)
            actual.append((item.members, result.score))
        extra = evaluator.stats.simulate_calls - before
        actual.sort(key=lambda row: row[1], reverse=True)
        actual_top5 = {team for team, _score in actual[:5]}
        rank_recall = len(actual_top5 & TRUE_TOP5_SET) / 5

        print(
            f"limit_per_view={limit} union={len(selected)} both_views={overlap_both} "
            f"survival_recall={survival_recall:.1f} candidate_extra_calls={extra} "
            f"cache_reuse={len(selected)-extra} actual_top5_recall={rank_recall:.1f}"
        )


if __name__ == "__main__":
    burst = BurstStructureValidator.from_moris()
    constraints = ConstraintSet(team_size=5, validators=(burst,))
    legal_teams = enumerate_legal_teams(ROSTER, constraints, ordered=False)
    for variant, references in REFERENCE_VARIANTS.items():
        run_variant(variant, references, constraints, legal_teams)
