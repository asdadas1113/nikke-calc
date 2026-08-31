"""Small real-Moris benchmark for marginal/proxy experiments.

This is intentionally NOT a unit test and is not discovered by the normal
``test_optimizer_*.py`` CI pattern. Run it explicitly when benchmarking.

The search space is deliberately scoped to one team and one canonical placement
order per 5-character combination. It is therefore exhaustive only inside that
fixed-order fixture; it must not be reported as exhaustive ordered NIKKE truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
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

REFERENCE_VARIANTS = {
    # First measured fixture: economical coverage, but most characters receive
    # only one marginal observation.
    "minimal-3": (
        ("리타", "크라운", "홍련", "앨리스", "모더니아"),
        ("볼륨", "나가", "홍련", "앨리스", "레드 후드"),
        ("리타", "볼륨", "나가", "모더니아", "레드 후드"),
    ),
    # Follow-up fixture: every character is absent from at least two references,
    # so each marginal is observed in multiple contexts.
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
TOP_N = 5
TARGET_BURST_INTERVAL_S = 20.0


def _new_evaluator() -> MorisEvaluator:
    return MorisEvaluator.from_moris(
        engine_commit=ENGINE_COMMIT,
        account_snapshot=ACCOUNT_SNAPSHOT,
        use_cache=True,
    )


def _load_burst_cooldowns() -> dict[str, float | None]:
    """Read only the static cooldown diagnostic used by the benchmark RoleFit.

    This does not decide legality and is intentionally benchmark-local until the
    experiment shows whether the signal is useful enough to promote into optimizer
    production code.
    """
    root = Path(__file__).resolve().parent.parent
    with open(root / "data" / "parsed_nikke.json", encoding="utf-8") as handle:
        parsed = json.load(handle)
    return {
        name: (float(row["burst_cooldown"]) if row.get("burst_cooldown") is not None else None)
        for name, row in parsed.items()
    }


def _burst_cycle_deficit(
    team: tuple[str, ...],
    burst: BurstStructureValidator,
    cooldowns: dict[str, float | None],
) -> float | None:
    """Cheap soft estimate of 20-second burst-stage supply.

    For each static stage, a 20 s unit supplies one full use per target interval
    and a 40 s unit supplies half. Two 40 s candidates therefore cover one stage
    at the cheap proxy level. Stage-A candidates are present in each static bucket
    exactly as the current Moris validator reports them; this deliberately remains
    an approximation and is never used as a hard constraint.

    Uncertain/dynamic/explicit-sequence cases return None so this cheap heuristic
    cannot penalize a structure that static inspection does not understand.
    """
    report = burst.inspect(team)
    if not report.fully_resolved:
        return None

    deficits: list[float] = []
    for stage in ("1", "2", "3"):
        supply = 0.0
        for name in report.eligible_by_stage[stage]:
            cooldown = cooldowns.get(name)
            if cooldown is None or cooldown <= 0:
                return None
            supply += TARGET_BURST_INTERVAL_S / cooldown
        deficits.append(max(0.0, 1.0 - supply))
    return sum(deficits) / len(deficits)


def _role_bucket_select(
    proxy_rank: list[tuple[str, ...]],
    deficits: dict[tuple[str, ...], float | None],
    *,
    limit: int,
    fit_fraction: float,
) -> list[tuple[str, ...]]:
    """Reserve part of a shortlist for estimated 20 s-capable teams.

    The remaining slots are filled from the unrestricted raw marginal ranking, so
    slow/unusual teams are preserved instead of being hard-pruned.
    """
    fit = [team for team in proxy_rank if deficits[team] == 0.0]
    reserve = min(limit, int(round(limit * fit_fraction)), len(fit))
    selected = list(fit[:reserve])
    seen = set(selected)
    for team in proxy_rank:
        if team in seen:
            continue
        selected.append(team)
        seen.add(team)
        if len(selected) >= limit:
            break
    return selected


def main(reference_variant: str) -> None:
    reference_teams = REFERENCE_VARIANTS[reference_variant]
    min_observations = 2 if reference_variant == "balanced-6" else 1

    burst = BurstStructureValidator.from_moris()
    cooldowns = _load_burst_cooldowns()
    constraints = ConstraintSet(team_size=5, validators=(burst,))

    for reference in reference_teams:
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
        reference_teams,
        legal=constraints.validate_team,
        evaluate_kwargs=EVALUATE_KWARGS,
    )
    marginal_runtime = perf_counter() - t0

    missing = [name for name in ROSTER if name not in marginals]
    if missing:
        raise RuntimeError(f"marginal fixture failed to observe: {missing}")
    under_observed = [
        name
        for name in ROSTER
        if len(marginals[name].observations) < min_observations
    ]
    if under_observed:
        raise RuntimeError(
            f"{reference_variant} reference fixture under-observed: {under_observed}"
        )

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

    deficits = {
        team: _burst_cycle_deficit(team, burst, cooldowns)
        for team in legal_teams
    }
    # Diagnostic upper bound: how far can this structural feature move teams if it
    # is allowed to dominate raw marginal ranking? This is not the production rule.
    role_first_rank = sorted(
        legal_teams,
        key=lambda team: (
            deficits[team] is None,
            deficits[team] if deficits[team] is not None else 0.0,
            -proxy_score(team),
        ),
    )

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
    print(f"reference_variant={reference_variant}")
    print(f"reference_count={len(reference_teams)}")
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

    print("--- candidate limit / true Top-5 recall ---")
    for limit in (8, 12, 16, 20, 24):
        selected = set(proxy_rank[: min(limit, len(proxy_rank))])
        recall = len(top_keys & selected) / len(top_keys)
        print(f"raw limit={limit}: top_{TOP_N}_recall={recall:.6f}")
        for fraction in (0.50, 0.75):
            role_selected = set(
                _role_bucket_select(
                    proxy_rank,
                    deficits,
                    limit=min(limit, len(proxy_rank)),
                    fit_fraction=fraction,
                )
            )
            role_recall = len(top_keys & role_selected) / len(top_keys)
            print(
                f"role_bucket fraction={fraction:.2f} limit={limit}: "
                f"top_{TOP_N}_recall={role_recall:.6f}"
            )

    print("--- true top 5 structural diagnostics ---")
    for rank, team in enumerate(true_rank[:5], 1):
        deficit = deficits[team]
        deficit_text = "unknown" if deficit is None else f"{deficit:.6f}"
        print(
            f"true#{rank}: score={truth_scores[team]:.0f} "
            f"proxy_rank={proxy_rank.index(team) + 1} "
            f"role_first_rank={role_first_rank.index(team) + 1} "
            f"burst_cycle_deficit={deficit_text} team={team}"
        )

    print("--- marginal values (mean_delta / best_delta / observations) ---")
    for name in ROSTER:
        mv = marginals[name]
        print(
            f"{name}: mean={mv.mean_delta:.0f} best={mv.best_delta:.0f} "
            f"n={len(mv.observations)}"
        )

    print("--- proxy top 12 ---")
    for rank, team in enumerate(proxy_rank[:CANDIDATE_LIMIT], 1):
        deficit = deficits[team]
        deficit_text = "unknown" if deficit is None else f"{deficit:.6f}"
        print(
            f"proxy#{rank}: proxy={proxy_score(team):.0f} "
            f"true_rank={true_rank.index(team) + 1} true={truth_scores[team]:.0f} "
            f"burst_cycle_deficit={deficit_text} team={team}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference-variant",
        choices=tuple(REFERENCE_VARIANTS),
        default="minimal-3",
    )
    args = parser.parse_args()
    main(args.reference_variant)
