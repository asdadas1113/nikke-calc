"""Small real-Moris benchmark for the first marginal/proxy experiment.

This is intentionally NOT a unit test and is not discovered by the normal
``test_optimizer_*.py`` CI pattern. Run it explicitly when benchmarking.

The search space is deliberately scoped to one team and one canonical placement
order per 5-character combination. It is therefore exhaustive only inside that
fixed-order fixture; it must not be reported as exhaustive ordered NIKKE truth.
"""

from __future__ import annotations

from time import perf_counter

from optimizer.candidates import CandidateTeam, select_diverse
from optimizer.constraints import BurstStructureValidator, ConstraintSet
from optimizer.evaluator import MorisEvaluator
from optimizer.marginal import measure_marginals
from optimizer.validation import enumerate_legal_teams, run_exhaustive_validation

ENGINE_COMMIT = "fb2fd9157aa14499daf6b9f185beb685d4393f90"
ACCOUNT_SNAPSHOT = "benchmark-default-build-2026-08-30"

# Combination order is the placement convention for this fixture. We do not try
# all 5! placements; that limitation is printed and must stay in benchmark docs.
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

# Three legal references, arranged so every roster member is absent from at least
# one reference and can therefore receive at least one substitution observation.
REFERENCE_TEAMS = (
    ("리타", "크라운", "홍련", "앨리스", "모더니아"),
    ("볼륨", "나가", "홍련", "앨리스", "레드 후드"),
    ("리타", "볼륨", "나가", "모더니아", "레드 후드"),
)

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
TOP_N = 5


def _new_evaluator() -> MorisEvaluator:
    return MorisEvaluator.from_moris(
        engine_commit=ENGINE_COMMIT,
        account_snapshot=ACCOUNT_SNAPSHOT,
        use_cache=True,
    )


def main() -> None:
    burst = BurstStructureValidator.from_moris()
    constraints = ConstraintSet(team_size=5, validators=(burst,))

    for reference in REFERENCE_TEAMS:
        report = burst.inspect(reference)
        if not report.legal:
            raise RuntimeError(
                f"benchmark reference is burst-illegal: {reference} missing={report.missing_stages}"
            )

    legal_teams = enumerate_legal_teams(ROSTER, constraints, ordered=False)
    if not legal_teams:
        raise RuntimeError("benchmark fixture produced no legal teams")

    proxy_evaluator = _new_evaluator()
    t0 = perf_counter()
    marginals = measure_marginals(
        proxy_evaluator,
        ROSTER,
        REFERENCE_TEAMS,
        legal=constraints.validate_team,
        evaluate_kwargs=EVALUATE_KWARGS,
    )
    marginal_runtime = perf_counter() - t0

    missing = [name for name in ROSTER if name not in marginals]
    if missing:
        raise RuntimeError(f"marginal fixture failed to observe: {missing}")

    def proxy_score(team: tuple[str, ...]) -> float:
        return sum(marginals[name].mean_delta for name in team)

    def select_raw_top(items):
        return sorted(items, key=lambda item: item.proxy_score, reverse=True)[:CANDIDATE_LIMIT]

    truth_evaluator = _new_evaluator()
    candidate_evaluator = _new_evaluator()
    metrics = run_exhaustive_validation(
        legal_teams,
        true_score=lambda team: truth_evaluator.evaluate(team, **EVALUATE_KWARGS).score,
        proxy_score=proxy_score,
        select_candidates=select_raw_top,
        optimizer_score=lambda team: candidate_evaluator.evaluate(team, **EVALUATE_KWARGS).score,
        team_count=1,
        top_n=TOP_N,
        ground_truth_call_count=lambda: truth_evaluator.stats.simulate_calls,
        optimizer_call_count=lambda: candidate_evaluator.stats.simulate_calls,
    )

    # Re-read through the truth evaluator cache for diagnostics. These are cache
    # hits and do not increase the measured exhaustive simulate-call count.
    truth_scores = {
        team: truth_evaluator.evaluate(team, **EVALUATE_KWARGS).score
        for team in legal_teams
    }
    true_rank = sorted(legal_teams, key=lambda team: truth_scores[team], reverse=True)
    proxy_rank = sorted(legal_teams, key=proxy_score, reverse=True)

    proxy_candidates = [
        CandidateTeam(team, proxy_score(team), source="marginal-mean")
        for team in legal_teams
    ]
    diverse = select_diverse(proxy_candidates, CANDIDATE_LIMIT, similarity_penalty=0.20)
    diverse_keys = {item.members for item in diverse}
    optimum_team = true_rank[0]
    top_keys = set(true_rank[:TOP_N])
    diverse_top_recall = len(top_keys & diverse_keys) / len(top_keys)
    diverse_optimum_survival = optimum_team in diverse_keys

    raw_selected = set(proxy_rank[:CANDIDATE_LIMIT])
    total_optimizer_calls = (
        proxy_evaluator.stats.simulate_calls + candidate_evaluator.stats.simulate_calls
    )

    print("=== real Moris marginal/proxy benchmark ===")
    print(f"engine_commit={ENGINE_COMMIT}")
    print(f"account_snapshot={ACCOUNT_SNAPSHOT}")
    print(f"roster={ROSTER}")
    print("scope=single-team; one canonical placement per unordered 5-member combination")
    print("ordered_ground_truth=false (full ordered 5! placement space NOT tested)")
    print(f"duration_s={EVALUATE_KWARGS['config']['duration']}")
    print(f"enemy_def={EVALUATE_KWARGS['enemy']['def']}")
    print("rng_mode=expected")
    print(f"seed={EVALUATE_KWARGS['seed']}")
    print(f"legal_team_count={metrics.legal_team_count}")
    print(f"candidate_limit={CANDIDATE_LIMIT}")
    print(f"marginal_simulate_calls={proxy_evaluator.stats.simulate_calls}")
    print(f"marginal_runtime_s={marginal_runtime:.6f}")
    print(f"exhaustive_simulate_calls={metrics.exhaustive_evaluator_calls}")
    print(f"exhaustive_runtime_s={metrics.exhaustive_runtime_s:.6f}")
    print(f"selected_candidate_simulate_calls={metrics.optimizer_evaluator_calls}")
    print(f"selected_candidate_runtime_s={metrics.optimizer_runtime_s:.6f}")
    print(f"total_optimizer_simulate_calls={total_optimizer_calls}")
    print(f"true_optimum_survival={metrics.true_optimum_survival:.6f}")
    print(f"top_{TOP_N}_recall={metrics.top_n_recall:.6f}")
    print(f"final_to_optimum={metrics.final_to_optimum:.9f}")
    print(f"exhaustive_optimum={metrics.exhaustive_optimum:.0f}")
    print(f"final_score={metrics.final_score:.0f}")
    print(f"true_optimum_team={optimum_team}")
    print(f"proxy_rank_of_true_optimum={proxy_rank.index(optimum_team) + 1}")
    print(f"raw_selected_contains_optimum={optimum_team in raw_selected}")
    print(f"diverse12_contains_optimum={diverse_optimum_survival}")
    print(f"diverse12_top_{TOP_N}_recall={diverse_top_recall:.6f}")

    print("--- marginal values (mean_delta / best_delta / observations) ---")
    for name in ROSTER:
        mv = marginals[name]
        print(
            f"{name}: mean={mv.mean_delta:.0f} best={mv.best_delta:.0f} "
            f"n={len(mv.observations)}"
        )

    print("--- true top 5 ---")
    for rank, team in enumerate(true_rank[:5], 1):
        print(
            f"true#{rank}: score={truth_scores[team]:.0f} "
            f"proxy_rank={proxy_rank.index(team) + 1} team={team}"
        )

    print("--- proxy top 12 ---")
    for rank, team in enumerate(proxy_rank[:CANDIDATE_LIMIT], 1):
        print(
            f"proxy#{rank}: proxy={proxy_score(team):.0f} "
            f"true_rank={true_rank.index(team) + 1} true={truth_scores[team]:.0f} team={team}"
        )


if __name__ == "__main__":
    main()
