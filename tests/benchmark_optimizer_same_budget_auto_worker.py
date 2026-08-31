"""Pure-vs-Meta real-account benchmark with automatic multi-view candidates.

Unlike ``benchmark_optimizer_same_budget_account.py`` this runner does not need a
hand-enumerated roster-wide ``candidate_teams`` list. It consumes one local
anonymous Worker payload, explicit reference squads, explicit search widths, and
meta evidence; then both Pure and Meta use the same AutomaticDiscoveryPolicy.

All numeric search constants remain plan inputs. Moris remains the only final
score source, and the strict same-budget harness still requires equal actual NEW
simulate() calls from independent caches.
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

from optimizer import (  # noqa: E402
    AutomaticDiscoveryPolicy,
    AutomaticPlacementMode,
    BurstStructureValidator,
    MorisEvaluator,
    StructuralDemand,
    build_burst_role_map,
    build_worker_account_bundle,
    derive_overload_piece_evidence,
    prepare_meta_guided_search_roster,
    run_automatic_anytime_search_round,
)
from optimizer.meta_bounds_input import parse_bounded_meta_evidence  # noqa: E402
from optimizer.same_budget import run_same_budget_comparison  # noqa: E402


def parse_discovery_policy(search: dict[str, Any], *, team_size: int) -> AutomaticDiscoveryPolicy:
    row = search.get("automatic_discovery")
    if not isinstance(row, dict):
        raise ValueError("plan.search.automatic_discovery must be an object")
    try:
        placement_mode = AutomaticPlacementMode(str(row["placement_mode"]))
    except (KeyError, ValueError) as exc:
        raise ValueError(
            "plan.search.automatic_discovery.placement_mode must be canonical-only "
            "or all-permutations"
        ) from exc
    required = (
        "single_team_beam_width",
        "single_team_global_limit",
        "single_team_per_core_limit",
        "allocation_team_beam_width",
        "allocation_team_options_per_state",
        "allocation_beam_width",
        "allocation_limit",
    )
    missing = tuple(name for name in required if name not in row)
    if missing:
        raise ValueError(
            "plan.search.automatic_discovery missing explicit fields: " + ", ".join(missing)
        )
    return AutomaticDiscoveryPolicy(
        team_size=team_size,
        single_team_beam_width=int(row["single_team_beam_width"]),
        single_team_global_limit=int(row["single_team_global_limit"]),
        single_team_per_core_limit=int(row["single_team_per_core_limit"]),
        allocation_team_beam_width=int(row["allocation_team_beam_width"]),
        allocation_team_options_per_state=int(row["allocation_team_options_per_state"]),
        allocation_beam_width=int(row["allocation_beam_width"]),
        allocation_limit=int(row["allocation_limit"]),
        placement_mode=placement_mode,
    )


def _discovery_summary(result) -> dict[str, Any]:
    per_view = []
    ordinary_expanded = 0
    allocation_expanded = 0
    ordinary_rejected = 0
    allocation_rejected = 0
    for name, bundle in result.discovery.bundles:
        ordinary_expanded += bundle.ordinary.expanded_states
        allocation_expanded += bundle.allocation.expanded_states
        ordinary_rejected += bundle.ordinary.rejected_illegal
        allocation_rejected += bundle.allocation.rejected_illegal
        per_view.append(
            {
                "name": name,
                "ordinary_candidate_count": len(bundle.ordinary.candidates),
                "ordinary_expanded_states": bundle.ordinary.expanded_states,
                "ordinary_rejected_illegal": bundle.ordinary.rejected_illegal,
                "allocation_count": len(bundle.allocation.allocations),
                "allocation_candidate_count": len(bundle.allocation.candidates),
                "allocation_expanded_states": bundle.allocation.expanded_states,
                "allocation_rejected_illegal": bundle.allocation.rejected_illegal,
            }
        )
    return {
        "source_views": list(result.discovery.source_views),
        "skipped_views": [
            {"name": row.name, "missing_member_count": len(row.missing_members)}
            for row in result.discovery.skipped_views
        ],
        "ordinary_candidate_count": len(result.discovery.ordinary_teams),
        "protected_channel_count": len(result.discovery.protected_channels),
        "protected_team_count": len(result.discovery.protected_teams),
        "candidate_evaluation_order_count": len(result.search.candidate_evaluation_order),
        "cheap_work": {
            "ordinary_expanded_states": ordinary_expanded,
            "allocation_expanded_states": allocation_expanded,
            "total_expanded_states": ordinary_expanded + allocation_expanded,
            "ordinary_rejected_illegal": ordinary_rejected,
            "allocation_rejected_illegal": allocation_rejected,
            "total_rejected_illegal": ordinary_rejected + allocation_rejected,
        },
        "views": per_view,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--meta", type=Path, required=True)
    ap.add_argument("--engine-commit", required=True)
    ap.add_argument("--preferred-area", type=int)
    ap.add_argument("--level-mode", choices=("fixed", "sync"), default="fixed")
    ap.add_argument("--unknown-policy", choices=("error", "moris-default"), default="error")
    ap.add_argument("--evaluation-batch-size", type=int)
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
        raise ValueError("strict Worker account audit failed before benchmark")
    owned = set(snapshot.roster)

    plan = base.load(args.plan)
    meta = parse_bounded_meta_evidence(
        base.load(args.meta),
        roster=snapshot.roster,
    )
    config = dict(plan.get("config") or {})
    if config.get("rng_mode") not in (None, "expected"):
        raise ValueError("same-budget benchmark requires rng_mode=expected")
    config["rng_mode"] = "expected"
    config.setdefault("immune_blocks_burst", True)
    enemy = dict(plan.get("enemy") or {})
    seed = int(plan.get("seed", 42))
    team_count = int(plan["team_count"])

    search = plan.get("search")
    if not isinstance(search, dict):
        raise ValueError("plan.search must be an object")
    simulate_call_budget = int(search["simulate_call_budget"])
    evaluation_batch_size = int(
        args.evaluation_batch_size
        if args.evaluation_batch_size is not None
        else search.get("evaluation_batch_size", 1)
    )
    if evaluation_batch_size <= 0:
        raise ValueError("evaluation_batch_size must be positive")
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
            isinstance(x, int) for x in refinement_positions_raw
        ):
            raise ValueError("plan.search.refinement_positions must be an integer list")
        refinement_positions = tuple(refinement_positions_raw)
    seed_max_per_core = int(search.get("seed_max_per_core", 1))

    demand_row = plan.get("structural_demand")
    if not isinstance(demand_row, dict):
        raise ValueError("plan.structural_demand must be an object")
    required_roles = base.names(
        demand_row.get("required_roles"),
        "plan.structural_demand.required_roles",
    )
    team_size = int(demand_row["team_size"])
    demand = StructuralDemand(
        team_count=team_count,
        team_size=team_size,
        required_roles=required_roles,
    )
    discovery_policy = parse_discovery_policy(search, team_size=team_size)

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

    for label, groups in (
        ("reference", references),
        ("seed_candidate", seed_candidates),
    ):
        for i, row in enumerate(groups):
            missing = set(row) - owned
            if missing:
                raise ValueError(f"{label}[{i}] contains unowned characters: {sorted(missing)}")
    missing_incoming = set(refinement_incoming) - owned
    if missing_incoming:
        raise ValueError(f"refinement_incoming contains unowned characters: {sorted(missing_incoming)}")

    pure_exact, pure_core = base.parse_seeds(plan.get("pure_seeds"), "plan.pure_seeds")
    meta_exact, meta_core = base.parse_seeds(plan.get("meta_seeds"), "plan.meta_seeds")

    validator = BurstStructureValidator.from_moris(config=config)
    for label, groups in (
        ("reference", references),
        ("seed_candidate", seed_candidates),
    ):
        for i, row in enumerate(groups):
            if not validator(row):
                raise ValueError(f"{label}[{i}] is hard-illegal: {row}")

    overload = derive_overload_piece_evidence(bundle.profile_payload, bundle.raw_sidecar)
    roles = build_burst_role_map(validator, snapshot.roster)
    meta_prepared = prepare_meta_guided_search_roster(
        snapshot.roster,
        meta.snapshots,
        meta.epochs,
        overload,
        roles,
        demand,
        schedule=meta.schedule,
        completed_through=meta.completed_through,
        policy=meta.policy,
        restoration_batch_size=meta.restoration_batch_size,
        cold_exploration_limit=meta.cold_exploration_limit,
        protected_names=meta.protected_names,
    )
    if not meta_prepared.prepared.structurally_feasible:
        raise ValueError("Meta-guided roster remains structurally infeasible after Cold restoration")

    pure_roster = tuple(snapshot.roster)
    meta_roster = tuple(meta_prepared.search_roster)
    pure_allowed = set(pure_roster)
    meta_allowed = set(meta_roster)
    pure_refs = base._filter_teams(references, pure_allowed)
    meta_refs = base._filter_teams(references, meta_allowed)
    pure_incoming = tuple(name for name in refinement_incoming if name in pure_allowed)
    meta_incoming = tuple(name for name in refinement_incoming if name in meta_allowed)
    pure_seed_candidates = base._filter_teams(seed_candidates, pure_allowed)
    # Meta seed-only hypotheses are allowed to inspect still-Cold owned characters
    # only when the caller supplied those bounded candidate teams explicitly.
    meta_seed_candidates = seed_candidates

    if not pure_refs or not meta_refs:
        raise ValueError("both Pure and Meta require at least one surviving reference team")

    dry = {
        "engine_commit": args.engine_commit,
        "snapshot_id": snapshot.snapshot_id,
        "roster_count": len(snapshot.roster),
        "blocking_unknown_paths": [row.path for row in snapshot.blocking_unknowns],
        "simulate_call_budget": simulate_call_budget,
        "evaluation_batch_size": evaluation_batch_size,
        "automatic_discovery": {
            "team_size": discovery_policy.team_size,
            "single_team_beam_width": discovery_policy.single_team_beam_width,
            "single_team_global_limit": discovery_policy.single_team_global_limit,
            "single_team_per_core_limit": discovery_policy.single_team_per_core_limit,
            "allocation_team_beam_width": discovery_policy.allocation_team_beam_width,
            "allocation_team_options_per_state": discovery_policy.allocation_team_options_per_state,
            "allocation_beam_width": discovery_policy.allocation_beam_width,
            "allocation_limit": discovery_policy.allocation_limit,
            "placement_mode": discovery_policy.placement_mode.value,
        },
        "pure_search_roster_count": len(pure_roster),
        "meta_search_roster_count": len(meta_roster),
        "meta_initial_primary": list(meta_prepared.prepared.initial_partition.primary),
        "meta_initial_cold": list(meta_prepared.prepared.initial_partition.cold),
        "meta_restored": list(meta_prepared.prepared.restored),
        "meta_explored_cold": list(meta_prepared.explored_cold),
        "meta_still_deferred_cold": list(meta_prepared.still_deferred_cold),
        "pure_reference_count": len(pure_refs),
        "meta_reference_count": len(meta_refs),
        "recall": None,
        "recall_reason": "production roster has no exhaustive oracle",
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

    captured: dict[str, Any] = {}

    def run_mode(
        label: str,
        roster: tuple[str, ...],
        refs: tuple[tuple[str, ...], ...],
        incoming: tuple[str, ...],
        exact_seeds,
        core_seeds,
        seed_candidates_for_mode: tuple[tuple[str, ...], ...],
        *,
        seed_roster: tuple[str, ...],
    ):
        def runner(evaluator, budget):
            result = run_automatic_anytime_search_round(
                evaluator,
                budget=budget,
                roster=roster,
                reference_teams=refs,
                discovery_policy=discovery_policy,
                positions_per_candidate=positions_per_candidate,
                candidate_limit=candidate_limit,
                team_count=team_count,
                legal=validator,
                refinement_incoming=incoming,
                refinement_positions=refinement_positions,
                refinement_max_new=refinement_max_new,
                marginal_max_simulate_calls=marginal_cap,
                proxy_view_limit_per_view=per_view,
                exact_seeds=exact_seeds,
                core_seeds=core_seeds,
                seed_max_per_core=seed_max_per_core,
                seed_roster=seed_roster,
                seed_candidate_teams=seed_candidates_for_mode or None,
                evaluate_kwargs=evaluate_kwargs,
                evaluation_batch_size=evaluation_batch_size,
            )
            captured[label] = result
            return result.search
        return runner

    pure_runner = run_mode(
        "pure",
        pure_roster,
        pure_refs,
        pure_incoming,
        pure_exact,
        pure_core,
        pure_seed_candidates,
        seed_roster=pure_roster,
    )
    meta_runner = run_mode(
        "meta",
        meta_roster,
        meta_refs,
        meta_incoming,
        meta_exact,
        meta_core,
        meta_seed_candidates,
        seed_roster=tuple(snapshot.roster),
    )

    comparison = run_same_budget_comparison(
        evaluator_factory,
        evaluator_factory,
        pure_runner,
        meta_runner,
        simulate_call_budget=simulate_call_budget,
        require_complete_allocations=True,
    )

    output = {
        **dry,
        "actual_equal_simulate_calls": comparison.simulate_calls,
        "pure": {
            "runtime_s": comparison.pure.runtime_s,
            "simulate_s": comparison.pure.simulate_s,
            "batch_requests": comparison.pure.batch_requests,
            "batch_items": comparison.pure.batch_items,
            "max_batch_size": comparison.pure.max_batch_size,
            "final_damage": comparison.pure.final_damage,
            "evaluated_candidate_count": comparison.pure.evaluated_candidate_count,
            "stage_calls": comparison.pure.stage_calls.__dict__,
            "allocation": base._allocation_rows(captured["pure"].search),
            "discovery": _discovery_summary(captured["pure"]),
            "unfulfilled_exact_seeds": [
                list(row.members) for row in captured["pure"].search.seed_selection.unfulfilled_exact
            ],
            "unfulfilled_core_seeds": [
                list(row.members) for row in captured["pure"].search.seed_selection.unfulfilled_cores
            ],
        },
        "meta": {
            "runtime_s": comparison.meta.runtime_s,
            "simulate_s": comparison.meta.simulate_s,
            "batch_requests": comparison.meta.batch_requests,
            "batch_items": comparison.meta.batch_items,
            "max_batch_size": comparison.meta.max_batch_size,
            "final_damage": comparison.meta.final_damage,
            "evaluated_candidate_count": comparison.meta.evaluated_candidate_count,
            "stage_calls": comparison.meta.stage_calls.__dict__,
            "allocation": base._allocation_rows(captured["meta"].search),
            "discovery": _discovery_summary(captured["meta"]),
            "unfulfilled_exact_seeds": [
                list(row.members) for row in captured["meta"].search.seed_selection.unfulfilled_exact
            ],
            "unfulfilled_core_seeds": [
                list(row.members) for row in captured["meta"].search.seed_selection.unfulfilled_cores
            ],
        },
        "meta_minus_pure_damage": comparison.damage_delta,
        "meta_minus_pure_relative": comparison.relative_damage_delta,
        "false_deferred": None,
        "false_deferred_reason": "unknown without exhaustive or stronger oracle",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
