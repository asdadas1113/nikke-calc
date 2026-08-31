"""Compare automatic discovery policies on one private Worker account.

This local-only benchmark tunes search widths without Meta/Cold evidence. Every
named variant shares the same account snapshot, Moris engine, boss/config,
reference squads, marginal/refinement settings, and requested call cap. The
``run_equal_budget_policy_sweep`` harness gives each variant an independent fresh
cache and rejects the comparison unless their observed NEW Moris simulate() call
counts are identical.

Only ``search.policy_variants`` changes between runs. No private Worker payload or
benchmark output is written to the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

import benchmark_optimizer_same_budget_account as base  # noqa: E402
import benchmark_optimizer_same_budget_auto_worker as auto  # noqa: E402

from optimizer import (  # noqa: E402
    BurstStructureValidator,
    MorisEvaluator,
    build_worker_account_bundle,
    run_automatic_anytime_search_round,
)
from optimizer.policy_sweep import run_equal_budget_policy_sweep  # noqa: E402


def parse_policy_variants(
    search: dict[str, Any],
    *,
    team_size: int,
):
    raw = search.get("policy_variants")
    if not isinstance(raw, dict) or len(raw) < 2:
        raise ValueError("plan.search.policy_variants must contain at least two named objects")

    out = {}
    for name, row in raw.items():
        label = str(name)
        if not label.strip():
            raise ValueError("policy variant names must be non-empty")
        if not isinstance(row, dict):
            raise ValueError(f"plan.search.policy_variants[{label!r}] must be an object")
        variant_search = dict(search)
        variant_search["automatic_discovery"] = row
        out[label] = auto.parse_discovery_policy(variant_search, team_size=team_size)
    return out


def _allocation_rows(result) -> list[dict[str, Any]]:
    return base._allocation_rows(result.search)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--engine-commit", required=True)
    ap.add_argument("--preferred-area", type=int)
    ap.add_argument("--level-mode", choices=("fixed", "sync"), default="fixed")
    ap.add_argument("--unknown-policy", choices=("error", "moris-default"), default="error")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bundle = build_worker_account_bundle(
        base.load(args.worker),
        preferred_area=args.preferred_area,
        level_mode=args.level_mode,
        unknown_policy=args.unknown_policy,
    )
    snapshot = bundle.snapshot
    if snapshot.unknown_policy == "error" and snapshot.blocking_unknowns:
        raise ValueError("strict Worker account audit failed before policy sweep")
    owned = set(snapshot.roster)

    plan = base.load(args.plan)
    config = dict(plan.get("config") or {})
    if config.get("rng_mode") not in (None, "expected"):
        raise ValueError("policy sweep requires rng_mode=expected")
    config["rng_mode"] = "expected"
    config.setdefault("immune_blocks_burst", True)
    enemy = dict(plan.get("enemy") or {})
    seed = int(plan.get("seed", 42))
    team_count = int(plan["team_count"])

    demand_row = plan.get("structural_demand")
    if not isinstance(demand_row, dict):
        raise ValueError("plan.structural_demand must be an object")
    team_size = int(demand_row["team_size"])
    if team_size * team_count > len(snapshot.roster):
        raise ValueError("owned roster is too small for requested allocation")

    search = plan.get("search")
    if not isinstance(search, dict):
        raise ValueError("plan.search must be an object")
    required_search = (
        "simulate_call_budget",
        "positions_per_candidate",
        "candidate_limit",
        "policy_variants",
    )
    missing_search = tuple(key for key in required_search if key not in search)
    if missing_search:
        raise ValueError(
            "plan.search missing explicit policy-sweep fields: " + ", ".join(missing_search)
        )

    simulate_call_budget = int(search["simulate_call_budget"])
    positions_per_candidate = int(search["positions_per_candidate"])
    candidate_limit = int(search["candidate_limit"])
    marginal_cap_raw = search.get("marginal_max_simulate_calls")
    marginal_cap = None if marginal_cap_raw is None else int(marginal_cap_raw)
    per_view_raw = search.get("proxy_view_limit_per_view")
    per_view = None if per_view_raw is None else int(per_view_raw)
    refinement_max_new = int(search.get("refinement_max_new", 0))
    refinement_positions_raw = search.get("refinement_positions")
    refinement_positions = None
    if refinement_positions_raw is not None:
        if not isinstance(refinement_positions_raw, list) or not all(
            isinstance(value, int) for value in refinement_positions_raw
        ):
            raise ValueError("plan.search.refinement_positions must be an integer list")
        refinement_positions = tuple(refinement_positions_raw)
    seed_max_per_core = int(search.get("seed_max_per_core", 1))
    policies = parse_policy_variants(search, team_size=team_size)

    refs_raw = plan.get("reference_teams")
    if not isinstance(refs_raw, list) or not refs_raw:
        raise ValueError("plan.reference_teams must be a non-empty list")
    references = tuple(
        base.team(row, f"plan.reference_teams[{i}]")
        for i, row in enumerate(refs_raw)
    )
    refinement_incoming = base.names(
        plan.get("refinement_incoming"),
        "plan.refinement_incoming",
    )
    seed_candidates_raw = plan.get("seed_candidate_teams") or []
    if not isinstance(seed_candidates_raw, list):
        raise ValueError("plan.seed_candidate_teams must be a list when provided")
    seed_candidates = tuple(
        base.team(row, f"plan.seed_candidate_teams[{i}]")
        for i, row in enumerate(seed_candidates_raw)
    )
    exact_seeds, core_seeds = base.parse_seeds(plan.get("pure_seeds"), "plan.pure_seeds")

    for label, groups in (("reference", references), ("seed_candidate", seed_candidates)):
        for index, row in enumerate(groups):
            missing = set(row) - owned
            if missing:
                raise ValueError(
                    f"{label}[{index}] contains unowned characters: {sorted(missing)}"
                )
    missing_incoming = set(refinement_incoming) - owned
    if missing_incoming:
        raise ValueError(
            "refinement_incoming contains unowned characters: "
            f"{sorted(missing_incoming)}"
        )

    validator = BurstStructureValidator.from_moris(config=config)
    for label, groups in (("reference", references), ("seed_candidate", seed_candidates)):
        for index, row in enumerate(groups):
            if not validator(row):
                raise ValueError(f"{label}[{index}] is hard-illegal: {row}")

    dry = {
        "engine_commit": args.engine_commit,
        "snapshot_id": snapshot.snapshot_id,
        "roster_count": len(snapshot.roster),
        "blocking_unknown_paths": [row.path for row in snapshot.blocking_unknowns],
        "simulate_call_budget": simulate_call_budget,
        "reference_count": len(references),
        "policy_variants": {
            name: {
                "team_size": policy.team_size,
                "single_team_beam_width": policy.single_team_beam_width,
                "single_team_global_limit": policy.single_team_global_limit,
                "single_team_per_core_limit": policy.single_team_per_core_limit,
                "allocation_team_beam_width": policy.allocation_team_beam_width,
                "allocation_team_options_per_state": policy.allocation_team_options_per_state,
                "allocation_beam_width": policy.allocation_beam_width,
                "allocation_limit": policy.allocation_limit,
                "placement_mode": policy.placement_mode.value,
            }
            for name, policy in policies.items()
        },
    }
    if args.dry_run:
        print(json.dumps(dry, ensure_ascii=False, indent=2))
        return

    evaluate_kwargs = {"config": config, "enemy": enemy, "seed": seed, "verbose": False}

    def evaluator_factory():
        return MorisEvaluator.from_moris_snapshot(
            engine_commit=args.engine_commit,
            snapshot=snapshot,
            use_cache=True,
        )

    captured = {}
    runners = {}
    for name, policy in policies.items():
        def make_runner(label=name, discovery_policy=policy):
            def runner(evaluator, budget):
                result = run_automatic_anytime_search_round(
                    evaluator,
                    budget=budget,
                    roster=snapshot.roster,
                    reference_teams=references,
                    discovery_policy=discovery_policy,
                    positions_per_candidate=positions_per_candidate,
                    candidate_limit=candidate_limit,
                    team_count=team_count,
                    legal=validator,
                    refinement_incoming=refinement_incoming,
                    refinement_positions=refinement_positions,
                    refinement_max_new=refinement_max_new,
                    marginal_max_simulate_calls=marginal_cap,
                    proxy_view_limit_per_view=per_view,
                    exact_seeds=exact_seeds,
                    core_seeds=core_seeds,
                    seed_max_per_core=seed_max_per_core,
                    seed_roster=snapshot.roster,
                    seed_candidate_teams=seed_candidates or None,
                    evaluate_kwargs=evaluate_kwargs,
                )
                captured[label] = result
                return result.search
            return runner
        runners[name] = make_runner()

    sweep = run_equal_budget_policy_sweep(
        evaluator_factory,
        runners,
        simulate_call_budget=simulate_call_budget,
        require_complete_allocations=True,
    )

    output = {
        **dry,
        "actual_equal_simulate_calls": sweep.simulate_calls,
        "runs": {
            row.mode: {
                "runtime_s": row.runtime_s,
                "final_damage": row.final_damage,
                "evaluated_candidate_count": row.evaluated_candidate_count,
                "stage_calls": row.stage_calls.__dict__,
                "allocation": _allocation_rows(captured[row.mode]),
                "discovery": auto._discovery_summary(captured[row.mode]),
            }
            for row in sweep.runs
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
