"""Real-Moris replay benchmark for low-budget marginal measurement priority.

Each reference variant first measures the complete fixed one-probe plan once with
Moris. Priority policies are then replayed from that exact score table under
smaller SearchBudget values. Reordering never changes reference assignment or
replacement slots, so the comparison isolates measurement order only.

This is a benchmark, not a unit test. The 8-character fixture and Top-5 truth are
the same canonical-placement scope used by the earlier marginal/refinement work.
"""

from __future__ import annotations

from collections import Counter, deque
from types import SimpleNamespace

from context import spec as char_spec
from optimizer.budget import BudgetedEvaluator, SearchBudget
from optimizer.constraints import BurstStructureValidator, ConstraintSet
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.marginal import (
    measure_planned_marginals_with_candidates,
    plan_candidate_specific_marginals,
)
from optimizer.priority import reorder_candidate_marginal_plan
from optimizer.validation import enumerate_legal_teams

ENGINE_COMMIT = "fb2fd9157aa14499daf6b9f185beb685d4393f90"
ACCOUNT_SNAPSHOT = "benchmark-default-build-2026-08-30"
ROSTER = (
    "리타",
    "볼륨",
    "크라운",
    "나가",
    "홍련",
    "앨리스",
    "모더니아",
    "레드 후드",
)
ORDER = {name: index for index, name in enumerate(ROSTER)}
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
    "enemy": {
        "def": 31_784,
        "code": "",
        "core_px": 0.0,
        "has_parts": False,
    },
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
CANDIDATE_LIMIT = 12


def same_burst_first(candidate, reference, index, replaced):
    candidate_stage = char_spec.burst_stage(candidate)
    replaced_stage = char_spec.burst_stage(replaced)
    same = (
        candidate_stage == "A"
        or replaced_stage == "A"
        or candidate_stage == replaced_stage
    )
    return (0 if same else 1, index)


def new_real_evaluator() -> MorisEvaluator:
    return MorisEvaluator.from_moris(
        engine_commit=ENGINE_COMMIT,
        account_snapshot=ACCOUNT_SNAPSHOT,
        use_cache=True,
    )


def new_table_evaluator(scores, identity_suffix: str) -> MorisEvaluator:
    table = {tuple(team): float(score) for team, score in scores.items()}

    def build_squad(names, characters):
        return tuple(names)

    def build_config(squad, config):
        return dict(config)

    def simulate(squad, **kwargs):
        return SimpleNamespace(squad_total=table[tuple(squad)])

    return MorisEvaluator(
        build_squad,
        build_config,
        simulate,
        cache_identity=CacheIdentity("replay", identity_suffix),
    )


def reference_undercoverage_order(plan):
    counts = Counter()
    for reference in plan.reference_teams:
        counts.update(reference)
    return tuple(
        sorted(
            (entry.candidate for entry in plan.entries),
            key=lambda name: (counts[name], ORDER[name]),
        )
    )


def reference_overcoverage_order(plan):
    counts = Counter()
    for reference in plan.reference_teams:
        counts.update(reference)
    return tuple(
        sorted(
            (entry.candidate for entry in plan.entries),
            key=lambda name: (-counts[name], ORDER[name]),
        )
    )


def legal_frequency_order(plan, legal_teams):
    counts = Counter(name for team in legal_teams for name in team)
    return tuple(
        sorted(
            (entry.candidate for entry in plan.entries),
            key=lambda name: (-counts[name], ORDER[name]),
        )
    )


def burst_round_robin_order(plan):
    stage_order = ("1", "2", "3", "A")
    buckets = {stage: deque() for stage in stage_order}
    extras = deque()
    for entry in plan.entries:
        stage = char_spec.burst_stage(entry.candidate)
        if stage in buckets:
            buckets[stage].append(entry.candidate)
        else:
            extras.append(entry.candidate)
    result = []
    while any(buckets[stage] for stage in stage_order):
        for stage in stage_order:
            if buckets[stage]:
                result.append(buckets[stage].popleft())
    result.extend(extras)
    return tuple(result)


def policy_orders(plan, legal_teams):
    return {
        "input": tuple(entry.candidate for entry in plan.entries),
        "reference-undercovered": reference_undercoverage_order(plan),
        "reference-overcovered": reference_overcoverage_order(plan),
        "legal-frequency": legal_frequency_order(plan, legal_teams),
        "burst-round-robin": burst_round_robin_order(plan),
    }


def proxy_metrics(measurement, legal_teams):
    observed = set(measurement.values)
    unlocked = [team for team in legal_teams if set(team) <= observed]
    unlock_truth = TRUE_TOP5_SET & set(unlocked)

    def proxy_score(team):
        return sum(measurement.values[name].mean_delta for name in team)

    ranked = sorted(unlocked, key=proxy_score, reverse=True)
    selected = set(ranked[:CANDIDATE_LIMIT])
    selected_truth = TRUE_TOP5_SET & selected
    true_ranks = []
    rank_by_team = {team: index + 1 for index, team in enumerate(ranked)}
    for team in TRUE_TOP5:
        true_ranks.append(rank_by_team.get(team))
    return {
        "observed": len(observed),
        "unlocked": len(unlocked),
        "unlock_recall": len(unlock_truth) / 5,
        "proxy_recall": len(selected_truth) / 5,
        "optimum_unlocked": TRUE_TOP5[0] in unlock_truth,
        "true_ranks": tuple(true_ranks),
    }


def run_variant(name, references, constraints, legal_teams):
    base_plan = plan_candidate_specific_marginals(
        ROSTER,
        references,
        positions_per_candidate=1,
        legal=constraints,
        position_priority=same_burst_first,
    )
    if base_plan.unplanned_candidates:
        raise RuntimeError(f"unplanned candidates: {base_plan.unplanned_candidates}")

    real = new_real_evaluator()
    full = measure_planned_marginals_with_candidates(
        real,
        base_plan,
        evaluate_kwargs=EVALUATE_KWARGS,
    )
    if not full.plan_complete:
        raise RuntimeError("full real-Moris plan did not complete")
    score_table = {
        item.members: item.simulated_score for item in full.evaluated_candidates
    }
    baseline_calls = len(base_plan.used_reference_teams)
    total_calls = baseline_calls + base_plan.planned_probe_count
    policies = policy_orders(base_plan, legal_teams)

    print(f"=== {name} ===")
    print(f"real_moris_calls={real.stats.simulate_calls}")
    print(f"baseline_calls={baseline_calls}")
    print(f"full_plan_calls={total_calls}")
    for policy, order in policies.items():
        print(f"policy={policy} order={order}")
        for budget in range(baseline_calls + 5, total_calls + 1):
            replay_plan = reorder_candidate_marginal_plan(base_plan, order)
            evaluator = new_table_evaluator(score_table, f"{name}-{policy}-{budget}")
            budgeted = BudgetedEvaluator(evaluator, SearchBudget(budget))
            measurement = measure_planned_marginals_with_candidates(
                budgeted,
                replay_plan,
                evaluate_kwargs=EVALUATE_KWARGS,
            )
            metrics = proxy_metrics(measurement, legal_teams)
            print(
                f" budget={budget} used={budgeted.used_simulate_calls} "
                f"observed={metrics['observed']} unlocked={metrics['unlocked']} "
                f"unlock_recall={metrics['unlock_recall']:.1f} "
                f"proxy_top12_recall={metrics['proxy_recall']:.1f} "
                f"optimum_unlocked={metrics['optimum_unlocked']} "
                f"true_top5_proxy_ranks={metrics['true_ranks']}"
            )


if __name__ == "__main__":
    burst = BurstStructureValidator.from_moris()
    constraints = ConstraintSet(team_size=5, validators=(burst,))
    legal_teams = enumerate_legal_teams(ROSTER, constraints, ordered=False)
    for variant, references in REFERENCE_VARIANTS.items():
        run_variant(variant, references, constraints, legal_teams)
