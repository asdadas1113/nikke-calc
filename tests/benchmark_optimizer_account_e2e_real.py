"""Real-Moris E2E check for normalized account snapshots.

This fixture contains no private account data.  It uses the public profile-sync
schema with synthetic build values to verify that one AccountSnapshot is applied
consistently through direct simulation, evaluator calls, marginal measurement,
one-swap refinement, and final re-evaluation.
"""

from __future__ import annotations

import copy

from calculator.timeline import simulate
from context import spec as char_spec
from optimizer import (
    AccountSyncAdapter,
    BurstStructureValidator,
    CandidateTeam,
    MorisEvaluator,
    generate_one_swap_neighbors,
    select_global_allocation,
)
from optimizer.marginal import measure_marginals

ENGINE = "fb2fd9157aa14499daf6b9f185beb685d4393f90"
TEAM = ("리타", "크라운", "홍련", "앨리스", "모더니아")
ROSTER = TEAM + ("나가",)
CONFIG = {"duration": 30.0, "rng_mode": "expected", "immune_blocks_burst": True}
ENEMY = {"def": 31784}
SEED = 42
EQUIP_KEYS = (
    "atk_pct",
    "element_bonus",
    "max_ammo_pct",
    "crit_rate",
    "crit_dmg",
    "charge_speed_pct",
    "charge_dmg_pct",
    "accuracy_pct",
    "def_pct",
)


def equipment(level: int | None) -> dict:
    if level is None:
        return {part: {"tier": "없음"} for part in ("머리", "몸통", "팔", "다리")}
    return {part: {"level": level} for part in ("머리", "몸통", "팔", "다리")}


def entry(*, invested: bool = True) -> dict:
    return {
        "breakthrough": 3,
        "core_enhancement": 0,
        "affinity": 30 if invested else 1,
        "skill_levels": {"1": 10, "2": 10, "3": 10} if invested else {"1": 1, "2": 1, "3": 1},
        "equipment": equipment(5 if invested else None),
        "equip_skills": {
            key: ([] if key in ("max_ammo_pct", "charge_speed_pct") else 0.0)
            for key in EQUIP_KEYS
        },
        "collection_stage": "SR15" if invested else "없음",
    }


def sync_payload(*, weak_alice: bool) -> dict:
    chars = {name: entry() for name in ROSTER}
    if weak_alice:
        chars["앨리스"] = entry(invested=False)
    return {
        "_meta": {
            "name": "synthetic-weak-alice" if weak_alice else "synthetic-invested",
            "area": 83,
            "fetched_at": "2026-08-30T23:00:00+09:00",
            "source": "synthetic profile-sync E2E fixture",
        },
        "_account": {
            "synchro_level": 400,
            "console": {
                "common_level": 1,
                "class_level": {"화력형": 1, "방어형": 1, "지원형": 1},
                "company_level": {
                    "엘리시온": 1,
                    "미실리스": 1,
                    "테트라": 1,
                    "필그림": 1,
                    "어브노말": 1,
                },
            },
            "console_warnings": [],
            "cubes": {},
        },
        "chars": chars,
    }


def direct_score(snapshot, team: tuple[str, ...]) -> float:
    profile = snapshot.to_growth_profile()
    squad = char_spec.build_squad(list(team), profile=profile)
    cfg = char_spec.build_config(squad, copy.deepcopy(CONFIG))
    result = simulate(
        squad,
        config=cfg,
        enemy=copy.deepcopy(ENEMY),
        seed=SEED,
        verbose=False,
    )
    return float(result.squad_total)


def run_case(*, weak_alice: bool) -> dict:
    snapshot = AccountSyncAdapter.normalize(sync_payload(weak_alice=weak_alice))
    validator = BurstStructureValidator.from_moris()
    kwargs = {"config": CONFIG, "enemy": ENEMY, "seed": SEED, "verbose": False}

    evaluator = MorisEvaluator.from_moris_snapshot(
        engine_commit=ENGINE,
        snapshot=snapshot,
    )
    direct = direct_score(snapshot, TEAM)
    candidate = evaluator.evaluate(TEAM, **kwargs)
    if candidate.score != direct:
        raise AssertionError(f"direct/evaluator mismatch: {direct} != {candidate.score}")

    marginal = measure_marginals(
        evaluator,
        ("나가",),
        (TEAM,),
        legal=validator,
        evaluate_kwargs=kwargs,
    )["나가"]

    neighbors = generate_one_swap_neighbors(
        (TEAM,),
        snapshot.roster,
        legal=validator,
        seen=(TEAM,),
        positions=(4,),
        max_new=1,
    )
    if len(neighbors) != 1 or neighbors[0].incoming != "나가":
        raise AssertionError(f"unexpected one-swap neighbor: {neighbors}")
    neighbor_eval = evaluator.evaluate(neighbors[0].members, **kwargs)

    pool = [
        CandidateTeam(TEAM, proxy_score=0.0, simulated_score=candidate.score, source="snapshot-candidate"),
        CandidateTeam(
            neighbors[0].members,
            proxy_score=0.0,
            simulated_score=neighbor_eval.score,
            source="snapshot-refine",
        ),
    ]
    allocation = select_global_allocation(pool, team_count=1)
    if allocation is None:
        raise AssertionError("one-team allocation unexpectedly failed")
    final_team = allocation.teams[0].members

    # Fresh evaluator: final scoring must rebuild from the exact same account snapshot,
    # not inherit a candidate-stage character dict or cache entry.
    final_evaluator = MorisEvaluator.from_moris_snapshot(
        engine_commit=ENGINE,
        snapshot=snapshot,
        use_cache=False,
    )
    final_eval = final_evaluator.evaluate(final_team, **kwargs)
    if final_eval.score != allocation.total_score:
        raise AssertionError(
            f"allocation/final snapshot mismatch: {allocation.total_score} != {final_eval.score}"
        )

    return {
        "snapshot_id": snapshot.snapshot_id,
        "direct_score": direct,
        "candidate_score": candidate.score,
        "marginal_mean": marginal.mean_delta,
        "marginal_best": marginal.best_delta,
        "neighbor": neighbors[0].members,
        "neighbor_score": neighbor_eval.score,
        "final_team": final_team,
        "final_score": final_eval.score,
        "optimizer_simulate_calls": evaluator.stats.simulate_calls,
        "final_simulate_calls": final_evaluator.stats.simulate_calls,
        "notes": snapshot.notes(),
    }


def main() -> None:
    strong = run_case(weak_alice=False)
    weak = run_case(weak_alice=True)

    if strong["snapshot_id"] == weak["snapshot_id"]:
        raise AssertionError("different account builds produced the same snapshot identity")
    if not strong["candidate_score"] > weak["candidate_score"]:
        raise AssertionError("weaker Alice build did not reduce candidate/full-team score")
    if not strong["neighbor_score"] > weak["neighbor_score"]:
        raise AssertionError("weaker Alice build did not propagate into refinement scoring")
    if strong["marginal_mean"] == weak["marginal_mean"]:
        raise AssertionError("account build change did not propagate into marginal measurement")

    print("=== normalized AccountSnapshot real-Moris E2E ===")
    print(f"engine_commit={ENGINE}")
    for label, row in (("invested", strong), ("weak_alice", weak)):
        print(f"--- {label} ---")
        for key, value in row.items():
            print(f"{key}={value}")
    print(f"candidate_delta={strong['candidate_score'] - weak['candidate_score']}")
    print(f"neighbor_delta={strong['neighbor_score'] - weak['neighbor_score']}")
    print(f"marginal_mean_delta={strong['marginal_mean'] - weak['marginal_mean']}")


if __name__ == "__main__":
    main()
