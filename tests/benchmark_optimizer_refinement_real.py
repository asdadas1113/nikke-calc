"""Failure-driven real-Moris benchmark for bounded one-swap refinement.

This replays the already-measured 12-candidate pools from the first real-Moris
fixture, chooses the best *actually simulated* seeds, and evaluates only unseen
one-member neighbors. The fixture keeps its original canonical placement
convention; production refinement defaults to preserving the replaced slot.
"""

from __future__ import annotations

import argparse
from time import perf_counter

from optimizer.constraints import BurstStructureValidator, ConstraintSet
from optimizer.evaluator import MorisEvaluator
from optimizer.refinement import generate_one_swap_neighbors

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
EVALUATE_KWARGS = {
    "config": {"duration": 180},
    "enemy": {"def": 31_784, "code": "", "core_px": 0.0, "has_parts": False},
    "seed": 42,
    "verbose": False,
}

TRUE_TOP5 = (
    (("리타", "크라운", "홍련", "앨리스", "모더니아"), 1_785_817_889),
    (("볼륨", "크라운", "홍련", "앨리스", "모더니아"), 1_656_756_068),
    (("리타", "크라운", "나가", "앨리스", "레드 후드"), 1_559_674_086),
    (("리타", "크라운", "홍련", "앨리스", "레드 후드"), 1_439_349_151),
    (("리타", "볼륨", "크라운", "앨리스", "레드 후드"), 1_435_571_126),
)

REPLAY = {
    "minimal-3": (
        (("리타", "크라운", "홍련", "앨리스", "모더니아"), 1_785_817_889),
        (("리타", "크라운", "앨리스", "모더니아", "레드 후드"), 1_335_687_731),
        (("리타", "크라운", "홍련", "모더니아", "레드 후드"), 1_325_247_612),
        (("크라운", "홍련", "앨리스", "모더니아", "레드 후드"), 976_899_725),
        (("리타", "볼륨", "크라운", "앨리스", "모더니아"), 1_286_978_575),
        (("리타", "크라운", "홍련", "앨리스", "레드 후드"), 1_439_349_151),
        (("리타", "볼륨", "크라운", "홍련", "모더니아"), 1_284_508_424),
        (("볼륨", "크라운", "홍련", "앨리스", "모더니아"), 1_656_756_068),
        (("리타", "볼륨", "크라운", "모더니아", "레드 후드"), 1_233_499_261),
        (("볼륨", "크라운", "앨리스", "모더니아", "레드 후드"), 1_247_357_676),
        (("볼륨", "크라운", "홍련", "모더니아", "레드 후드"), 1_255_674_488),
        (("리타", "볼륨", "크라운", "홍련", "앨리스"), 1_433_013_393),
    ),
    "balanced-6": (
        (("크라운", "나가", "홍련", "앨리스", "레드 후드"), 846_547_887),
        (("리타", "크라운", "홍련", "앨리스", "레드 후드"), 1_439_349_151),
        (("크라운", "홍련", "앨리스", "모더니아", "레드 후드"), 976_899_725),
        (("볼륨", "크라운", "홍련", "앨리스", "레드 후드"), 1_332_844_789),
        (("리타", "크라운", "나가", "홍련", "앨리스"), 1_428_045_824),
        (("리타", "크라운", "나가", "홍련", "레드 후드"), 1_347_165_816),
        (("리타", "크라운", "나가", "앨리스", "레드 후드"), 1_559_674_086),
        (("크라운", "나가", "홍련", "모더니아", "레드 후드"), 1_010_135_959),
        (("리타", "크라운", "홍련", "앨리스", "모더니아"), 1_785_817_889),
        (("크라운", "나가", "앨리스", "모더니아", "레드 후드"), 1_086_361_246),
        (("리타", "크라운", "홍련", "모더니아", "레드 후드"), 1_325_247_612),
        (("리타", "크라운", "앨리스", "모더니아", "레드 후드"), 1_335_687_731),
    ),
}


def canonical_fixture_placement(team):
    return tuple(sorted(team, key=ORDER.__getitem__))


def new_evaluator() -> MorisEvaluator:
    return MorisEvaluator.from_moris(
        engine_commit=ENGINE_COMMIT,
        account_snapshot=ACCOUNT_SNAPSHOT,
        use_cache=True,
    )


def main(variant: str) -> None:
    replay = REPLAY[variant]
    selected_scores = dict(replay)
    selected = tuple(selected_scores)
    seeds = tuple(
        team for team, _ in sorted(replay, key=lambda row: row[1], reverse=True)[:3]
    )

    burst = BurstStructureValidator.from_moris()
    constraints = ConstraintSet(team_size=5, validators=(burst,))
    truth_keys = {team for team, _ in TRUE_TOP5}
    initial_recall = len(truth_keys & set(selected)) / len(truth_keys)

    neighborhoods = {}
    for seed_count in (1, 2, 3):
        neighborhoods[seed_count] = generate_one_swap_neighbors(
            seeds[:seed_count],
            ROSTER,
            legal=constraints.validate_team,
            seen=selected,
            placement_resolver=canonical_fixture_placement,
        )

    all_rows = neighborhoods[3]
    evaluator = new_evaluator()
    t0 = perf_counter()
    measured = {
        row.members: evaluator.evaluate(row.members, **EVALUATE_KWARGS).score
        for row in all_rows
    }
    runtime_s = perf_counter() - t0

    # The replay scores came from the same exact engine/build fixture. Any newly
    # recovered true-Top5 team must reproduce its saved score exactly.
    expected_truth = dict(TRUE_TOP5)
    for team, expected in expected_truth.items():
        if team in measured and measured[team] != expected:
            raise RuntimeError(
                f"refinement fixture drift for {team}: measured={measured[team]} expected={expected}"
            )

    print("=== bounded one-swap real Moris refinement benchmark ===")
    print(f"engine_commit={ENGINE_COMMIT}")
    print(f"account_snapshot={ACCOUNT_SNAPSHOT}")
    print(f"reference_variant={variant}")
    print("scope=replay 12 already-simulated candidates; one canonical fixture placement")
    print("production_default_order=preserve replaced slot; benchmark resolver=canonical roster order")
    print(f"initial_candidate_count={len(selected)}")
    print(f"initial_top5_recall={initial_recall:.6f}")
    print(f"seed_order={seeds}")
    print(f"new_simulate_calls={evaluator.stats.simulate_calls}")
    print(f"new_runtime_s={runtime_s:.6f}")

    for seed_count in (1, 2, 3):
        rows = neighborhoods[seed_count]
        new_keys = {row.members for row in rows}
        union_keys = set(selected) | new_keys
        recall = len(truth_keys & union_keys) / len(truth_keys)
        recovered = tuple(team for team, _ in TRUE_TOP5 if team in new_keys and team not in selected_scores)
        print(
            f"seed_count={seed_count} new_neighbors={len(rows)} "
            f"union_top5_recall={recall:.6f} recovered={recovered}"
        )

    combined_scores = dict(selected_scores)
    combined_scores.update(measured)
    final_rank = sorted(combined_scores, key=combined_scores.get, reverse=True)
    final_top5 = tuple(final_rank[:5])
    final_recall = len(truth_keys & set(final_top5)) / len(truth_keys)
    print(f"evaluated_union_count={len(combined_scores)}")
    print(f"final_evaluated_top5_recall={final_recall:.6f}")
    print(f"final_evaluated_top5={final_top5}")

    print("--- newly measured true-Top5 recoveries ---")
    for team, expected in TRUE_TOP5:
        if team in measured and team not in selected_scores:
            print(f"team={team} score={measured[team]:.0f} expected={expected}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-variant", choices=tuple(REPLAY), required=True)
    args = parser.parse_args()
    main(args.reference_variant)
