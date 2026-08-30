"""Failure-driven real-Moris pair-synergy benchmark.

This benchmark reuses the already measured marginal proxy and Top-5 truth from
``benchmark_optimizer_marginal_real.py`` on the exact same engine/build fixture.
It performs only the selective pair probes justified by those recall failures;
it does not re-run the 54-team exhaustive truth or enumerate every pair.
"""

from __future__ import annotations

from itertools import combinations
from statistics import fmean
from time import perf_counter

from optimizer.constraints import BurstStructureValidator, ConstraintSet
from optimizer.evaluator import MorisEvaluator
from optimizer.synergy import PairSynergyProbe, measure_pair_probes
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

# Recorded from Actions runs 33312943457 and 33313327360. Values are the rounded
# mean deltas printed by those measured runs; the raw proxy ranks below are
# asserted so this replay cannot silently drift away from the recorded fixture.
RECORDED_MARGINALS = {
    "minimal-3": {
        "리타": 84_608_211,
        "볼륨": -129_061_821,
        "크라운": 595_372_758,
        "나가": -357_773_881,
        "홍련": 26_963_394,
        "앨리스": 62_399_299,
        "모더니아": 154_668_615,
        "레드 후드": -4_421_528,
    },
    "balanced-6": {
        "리타": 76_064_095,
        "볼륨": -53_734_747,
        "크라운": 759_897_908,
        "나가": 97_652_758,
        "홍련": 257_709_730,
        "앨리스": 238_956_586,
        "모더니아": 52_175_143,
        "레드 후드": 230_173_181,
    },
}
RECORDED_RAW_TOP5_RANKS = {
    "minimal-3": (1, 8, 22, 6, 13),
    "balanced-6": (9, 18, 7, 2, 19),
}
TRUE_TOP5 = (
    ("리타", "크라운", "홍련", "앨리스", "모더니아"),
    ("볼륨", "크라운", "홍련", "앨리스", "모더니아"),
    ("리타", "크라운", "나가", "앨리스", "레드 후드"),
    ("리타", "크라운", "홍련", "앨리스", "레드 후드"),
    ("리타", "볼륨", "크라운", "앨리스", "레드 후드"),
)

# Probe selection comes directly from the saved recall failures:
# - Crown+Naga targets the minimal-3 true #3 miss (proxy rank 22).
# - Volume+Crown is measured in two contexts because balanced-6 misses true #2
#   and #5, both containing that core. This is intentionally three probes, not a
#   scan of all 28 roster pairs.
PROBES = (
    PairSynergyProbe(
        pair=("크라운", "나가"),
        reference=("리타", "볼륨", "홍련", "앨리스", "레드 후드"),
        positions=(1, 2),
        source="minimal-3-true3",
    ),
    PairSynergyProbe(
        pair=("볼륨", "크라운"),
        reference=("리타", "나가", "홍련", "앨리스", "모더니아"),
        positions=(0, 1),
        source="balanced-6-true2",
    ),
    PairSynergyProbe(
        pair=("볼륨", "크라운"),
        reference=("리타", "나가", "홍련", "앨리스", "레드 후드"),
        positions=(1, 2),
        source="balanced-6-true5",
    ),
)


def _new_evaluator() -> MorisEvaluator:
    return MorisEvaluator.from_moris(
        engine_commit=ENGINE_COMMIT,
        account_snapshot=ACCOUNT_SNAPSHOT,
        use_cache=True,
    )


def _proxy_score(team: tuple[str, ...], marginals: dict[str, int]) -> float:
    return float(sum(marginals[name] for name in team))


def _pair_key(pair: tuple[str, str]) -> frozenset[str]:
    return frozenset(pair)


def _adjusted_score(
    team: tuple[str, ...],
    marginals: dict[str, int],
    interactions: dict[frozenset[str], float],
    *,
    alpha: float,
) -> float:
    score = _proxy_score(team, marginals)
    member_set = frozenset(team)
    for pair, delta in interactions.items():
        if pair.issubset(member_set):
            score += alpha * delta
    return score


def _ranks(ranked: list[tuple[str, ...]]) -> tuple[int, ...]:
    return tuple(ranked.index(team) + 1 for team in TRUE_TOP5)


def _recall_at(ranked: list[tuple[str, ...]], limit: int) -> float:
    selected = set(ranked[:limit])
    return sum(team in selected for team in TRUE_TOP5) / len(TRUE_TOP5)


def main() -> None:
    burst = BurstStructureValidator.from_moris()
    constraints = ConstraintSet(team_size=5, validators=(burst,))
    legal_teams = enumerate_legal_teams(ROSTER, constraints, ordered=False)
    if len(legal_teams) != 54:
        raise RuntimeError(f"recorded fixture expected 54 legal teams, got {len(legal_teams)}")

    # Assert the rounded replay still exactly reproduces the two recorded raw rank
    # vectors before using it to judge pair corrections.
    for variant, marginals in RECORDED_MARGINALS.items():
        raw = sorted(
            legal_teams,
            key=lambda team: _proxy_score(team, marginals),
            reverse=True,
        )
        observed = _ranks(raw)
        if observed != RECORDED_RAW_TOP5_RANKS[variant]:
            raise RuntimeError(
                f"recorded marginal replay drifted for {variant}: {observed}"
            )

    evaluator = _new_evaluator()
    before = evaluator.stats.simulate_calls
    t0 = perf_counter()
    observations = measure_pair_probes(
        evaluator,
        PROBES,
        legal=constraints.validate_team,
        evaluate_kwargs=EVALUATE_KWARGS,
    )
    runtime = perf_counter() - t0
    pair_calls = evaluator.stats.simulate_calls - before

    grouped: dict[frozenset[str], list[float]] = {}
    for row in observations:
        grouped.setdefault(_pair_key(row.probe.pair), []).append(row.interaction_delta)
    mean_interactions = {pair: fmean(values) for pair, values in grouped.items()}

    print("=== failure-driven real Moris pair benchmark ===")
    print(f"engine_commit={ENGINE_COMMIT}")
    print(f"account_snapshot={ACCOUNT_SNAPSHOT}")
    print(f"probe_count={len(PROBES)}")
    print(f"unique_pair_count={len(grouped)}")
    print(f"simulate_calls={pair_calls}")
    print(f"runtime_s={runtime:.6f}")
    print("all_pairs_enumerated=false")

    print("--- measured probes ---")
    for row in observations:
        print(
            f"pair={row.probe.pair} source={row.probe.source} "
            f"reference={row.probe.reference} replaced={row.probe.replaced} "
            f"baseline={row.baseline_score:.0f} first={row.first_only_score:.0f} "
            f"second={row.second_only_score:.0f} paired={row.paired_score:.0f} "
            f"interaction={row.interaction_delta:.0f}"
        )

    print("--- pair means ---")
    for pair, values in grouped.items():
        print(
            f"pair={tuple(sorted(pair))} observations={len(values)} "
            f"mean_interaction={fmean(values):.0f} min={min(values):.0f} max={max(values):.0f}"
        )

    print("--- replay ranking sensitivity ---")
    for variant, marginals in RECORDED_MARGINALS.items():
        raw = sorted(
            legal_teams,
            key=lambda team: _proxy_score(team, marginals),
            reverse=True,
        )
        print(
            f"variant={variant} alpha=0 raw_ranks={_ranks(raw)} "
            f"recall12={_recall_at(raw, 12):.6f}"
        )
        for alpha in (0.25, 0.50, 1.00):
            adjusted = sorted(
                legal_teams,
                key=lambda team: _adjusted_score(
                    team, marginals, mean_interactions, alpha=alpha
                ),
                reverse=True,
            )
            print(
                f"variant={variant} alpha={alpha:.2f} ranks={_ranks(adjusted)} "
                f"recall8={_recall_at(adjusted, 8):.6f} "
                f"recall12={_recall_at(adjusted, 12):.6f} "
                f"recall16={_recall_at(adjusted, 16):.6f}"
            )


if __name__ == "__main__":
    main()
