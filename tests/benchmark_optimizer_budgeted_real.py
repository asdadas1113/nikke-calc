"""Real-Moris benchmark for candidate-specific marginal budget + one-swap recovery.

This is intentionally NOT a unit test. It reuses the saved 8-character public
fixture so the new near-linear marginal policy can be compared with the earlier
all-context measurements without using any private account payload.

Scope remains one canonical placement per unordered 5-member combination for the
truth set. Marginal probes preserve their reference-slot order; selected proxy
teams and refinement neighbors use the fixture's canonical roster order.
"""

from __future__ import annotations

import argparse
from collections import Counter
from time import perf_counter

from context import spec as char_spec
from optimizer.candidates import CandidateTeam
from optimizer.constraints import BurstStructureValidator, ConstraintSet
from optimizer.evaluator import MorisEvaluator
from optimizer.marginal import (
    measure_planned_marginals_with_candidates,
    plan_candidate_specific_marginals,
)
from optimizer.refinement import generate_one_swap_neighbors
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
CANDIDATE_LIMIT = 12
POSITIONS_PER_CANDIDATE = 2
MAX_REFINEMENT_SEEDS = 5
TRUE_TOP5 = (
    (("리타", "크라운", "홍련", "앨리스", "모더니아"), 1_785_817_889),
    (("볼륨", "크라운", "홍련", "앨리스", "모더니아"), 1_656_756_068),
    (("리타", "크라운", "나가", "앨리스", "레드 후드"), 1_559_674_086),
    (("리타", "크라운", "홍련", "앨리스", "레드 후드"), 1_439_349_151),
    (("리타", "볼륨", "크라운", "앨리스", "레드 후드"), 1_435_571_126),
)


def canonical_fixture_placement(team):
    return tuple(sorted(team, key=ORDER.__getitem__))


def same_burst_first(candidate, reference, index, replaced):
    """Cheap structural slot priority used only by this benchmark policy.

    Prefer replacing the same static burst stage, but do not prohibit other
    stages; hard legality still decides which trials are possible.
    """

    candidate_stage = char_spec.burst_stage(candidate)
    replaced_stage = char_spec.burst_stage(replaced)
    same = (
        candidate_stage == "A"
        or replaced_stage == "A"
        or candidate_stage == replaced_stage
    )
    return (0 if same else 1, index)


def new_evaluator() -> MorisEvaluator:
    return MorisEvaluator.from_moris(
        engine_commit=ENGINE_COMMIT,
        account_snapshot=ACCOUNT_SNAPSHOT,
        use_cache=True,
    )


def recall_of(keys: set[tuple[str, ...]]) -> float:
    truth = {team for team, _score in TRUE_TOP5}
    return len(truth & keys) / len(truth)


def main(reference_variant: str) -> None:
    references = REFERENCE_VARIANTS[reference_variant]
    burst = BurstStructureValidator.from_moris()
    constraints = ConstraintSet(team_size=5, validators=(burst,))
    legal_teams = enumerate_legal_teams(ROSTER, constraints, ordered=False)

    plan = plan_candidate_specific_marginals(
        ROSTER,
        references,
        positions_per_candidate=POSITIONS_PER_CANDIDATE,
        legal=constraints,
        position_priority=same_burst_first,
    )
    if plan.unplanned_candidates:
        raise RuntimeError(f"candidate-specific plan missed: {plan.unplanned_candidates}")

    evaluator = new_evaluator()
    t0 = perf_counter()
    measured = measure_planned_marginals_with_candidates(
        evaluator,
        plan,
        evaluate_kwargs=EVALUATE_KWARGS,
    )
    marginal_wall_s = perf_counter() - t0
    if measured.unobserved_candidates or measured.budget_exhausted:
        raise RuntimeError(
            "planned marginal measurement unexpectedly incomplete: "
            f"unobserved={measured.unobserved_candidates} "
            f"budget_exhausted={measured.budget_exhausted}"
        )
    missing = [name for name in ROSTER if name not in measured.values]
    if missing:
        raise RuntimeError(f"planned marginal values missing: {missing}")

    marginal_calls = evaluator.stats.simulate_calls

    def proxy_score(team: tuple[str, ...]) -> float:
        return sum(measured.values[name].mean_delta for name in team)

    proxy_rank = sorted(legal_teams, key=proxy_score, reverse=True)
    selected = proxy_rank[:CANDIDATE_LIMIT]

    # Reuse every actual marginal/reference sim as an evaluated candidate. Then
    # ask for the proxy top-12 through the SAME evaluator; overlap becomes cache
    # hits, so candidate_extra_calls is the true incremental simulation cost.
    candidate_map: dict[tuple[str, ...], CandidateTeam] = {
        item.members: item for item in measured.evaluated_candidates
    }
    before_candidates = evaluator.stats.simulate_calls
    for team in selected:
        result = evaluator.evaluate(team, **EVALUATE_KWARGS)
        candidate_map[team] = CandidateTeam(
            members=team,
            proxy_score=proxy_score(team),
            simulated_score=result.score,
            source="proxy-top",
        )
    candidate_extra_calls = evaluator.stats.simulate_calls - before_candidates
    selected_overlap = CANDIDATE_LIMIT - candidate_extra_calls

    initial_keys = set(candidate_map)
    initial_recall = recall_of(initial_keys)
    actual_seed_order = tuple(
        item.members
        for item in sorted(candidate_map.values(), key=lambda item: item.score, reverse=True)
    )

    print("=== candidate-specific marginal + one-swap real Moris benchmark ===")
    print(f"engine_commit={ENGINE_COMMIT}")
    print(f"reference_variant={reference_variant}")
    print("truth_scope=one canonical roster-order placement per unordered 5-member team")
    print("marginal_probe_order=reference slot; proxy/refine placement=canonical roster order")
    print(f"reference_count={len(references)}")
    print(f"used_reference_count={len(plan.used_reference_teams)}")
    print(f"reference_loads={dict(Counter(entry.reference for entry in plan.entries))}")
    print(f"planned_probes={plan.planned_probe_count}")
    print(f"marginal_calls={marginal_calls}")
    print(f"marginal_wall_s={marginal_wall_s:.6f}")
    print(f"candidate_limit={CANDIDATE_LIMIT}")
    print(f"candidate_extra_calls={candidate_extra_calls}")
    print(f"selected_overlap_with_marginal_cache={selected_overlap}")
    print(f"initial_evaluated_count={len(candidate_map)}")
    print(f"initial_top5_survival_recall={initial_recall:.6f}")
    print(f"cumulative_calls_before_refine={evaluator.stats.simulate_calls}")

    evaluated_keys = set(candidate_map)
    for seed_index, seed in enumerate(actual_seed_order[:MAX_REFINEMENT_SEEDS], start=1):
        neighbors = generate_one_swap_neighbors(
            (seed,),
            ROSTER,
            legal=constraints,
            seen=evaluated_keys,
            placement_resolver=canonical_fixture_placement,
        )
        before = evaluator.stats.simulate_calls
        for row in neighbors:
            result = evaluator.evaluate(row.members, **EVALUATE_KWARGS)
            candidate_map[row.members] = CandidateTeam(
                members=row.members,
                proxy_score=0.0,
                simulated_score=result.score,
                source="one-swap-refine",
            )
            evaluated_keys.add(row.members)
        incremental = evaluator.stats.simulate_calls - before
        print(
            f"seed_count={seed_index} seed={seed} "
            f"incremental_calls={incremental} "
            f"cumulative_calls={evaluator.stats.simulate_calls} "
            f"top5_survival_recall={recall_of(evaluated_keys):.6f}"
        )

    ranked_actual = sorted(candidate_map.values(), key=lambda item: item.score, reverse=True)
    ranked_keys = {item.members for item in ranked_actual[:5]}
    print(f"final_evaluated_count={len(candidate_map)}")
    print(f"final_top5_rank_recall={recall_of(ranked_keys):.6f}")
    print(f"final_best_team={ranked_actual[0].members}")
    print(f"final_best_score={ranked_actual[0].score:.0f}")

    expected = dict(TRUE_TOP5)
    for team, score in expected.items():
        item = candidate_map.get(team)
        if item is not None and item.score != score:
            raise RuntimeError(
                f"fixture drift for {team}: measured={item.score} expected={score}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference-variant",
        choices=tuple(REFERENCE_VARIANTS),
        required=True,
    )
    args = parser.parse_args()
    main(args.reference_variant)
