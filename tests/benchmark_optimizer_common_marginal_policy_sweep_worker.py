"""Tune automatic discovery widths after one shared real-account marginal phase.

This benchmark isolates discovery policy from the dominant repeated Moris cost:

1. normalize one private anonymous Worker account;
2. build one score-blind marginal plan and measure it exactly once;
3. reconstruct the same independent ProxyViews for every policy variant;
4. generate each variant's ordinary/protected candidates with zero Moris calls;
5. give every variant a fresh evaluator and exactly the same number of NEW
   candidate-team Moris calls;
6. combine those rows with the shared already-measured marginal candidate pool;
7. run the same exact non-overlapping allocation over actual Moris scores.

Refinement and external seeds are intentionally absent. This runner answers only
whether a wider/alternate cheap discovery policy buys better evaluated-pool recall
for the same post-marginal Moris-call budget. The shared marginal cost, common-pool
baseline, cheap expansion work, and policy-specific candidate calls are reported
separately. Private Worker data and output remain local-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

import benchmark_optimizer_policy_sweep_worker as sweep_parser  # noqa: E402
import benchmark_optimizer_same_budget_account as base  # noqa: E402

from optimizer import (  # noqa: E402
    BudgetedEvaluator,
    BurstStructureValidator,
    CandidateTeam,
    MorisEvaluator,
    SearchBudget,
    all_permutation_placements,
    build_planned_marginal_prefix_views,
    build_worker_account_bundle,
    generate_multi_view_candidate_discovery,
    identity_placement,
    measure_planned_marginals_with_candidates,
    plan_candidate_specific_marginals,
    select_global_allocation,
    select_proxy_view_candidates,
)
from optimizer.automatic_search import AutomaticPlacementMode  # noqa: E402


Team = tuple[str, ...]


@dataclass(frozen=True)
class PolicyRun:
    name: str
    candidate_simulate_calls: int
    runtime_s: float
    final_damage: float
    final_team_count: int
    evaluated_candidate_count: int
    stream_count: int
    ordinary_candidate_count: int
    protected_team_count: int
    cheap_expanded_states: int
    allocation: tuple[tuple[Team, float], ...]


def _interleave_team_channels(*channels: tuple[Team, ...]) -> tuple[Team, ...]:
    seen: set[Team] = set()
    out: list[Team] = []
    max_rank = max((len(channel) for channel in channels), default=0)
    for rank in range(max_rank):
        for channel in channels:
            if rank >= len(channel):
                continue
            team = channel[rank]
            if team in seen:
                continue
            seen.add(team)
            out.append(team)
    return tuple(out)


def _placement_expander(mode: AutomaticPlacementMode):
    if mode is AutomaticPlacementMode.CANONICAL_ONLY:
        return identity_placement
    if mode is AutomaticPlacementMode.ALL_PERMUTATIONS:
        return all_permutation_placements
    raise ValueError(f"unsupported placement mode: {mode}")


def _common_candidate_map(measurement) -> dict[Team, CandidateTeam]:
    out: dict[Team, CandidateTeam] = {}
    for row in measurement.evaluated_candidates:
        if row.simulated_score is None:
            raise ValueError("shared marginal candidate lacks actual Moris score")
        out.setdefault(tuple(row.members), row)
    return out


def _allocation_rows(allocation) -> tuple[tuple[Team, float], ...]:
    if allocation is None:
        return ()
    return tuple((tuple(row.members), float(row.score)) for row in allocation.teams)


def run_policy_after_common_marginal(
    evaluator: MorisEvaluator,
    *,
    name: str,
    policy,
    roster: tuple[str, ...],
    plan,
    measurement,
    candidate_call_budget: int,
    proxy_view_limit_per_view: int,
    team_count: int,
    legal: BurstStructureValidator,
    evaluate_kwargs: dict[str, Any],
) -> PolicyRun:
    """Evaluate one cheap discovery policy from immutable shared marginal evidence."""

    if candidate_call_budget < 0:
        raise ValueError("candidate_call_budget must be non-negative")
    if proxy_view_limit_per_view <= 0:
        raise ValueError("proxy_view_limit_per_view must be positive")
    if evaluator.stats.simulate_calls or evaluator.cache_size:
        raise ValueError("policy evaluator must start with a fresh empty cache")

    views = build_planned_marginal_prefix_views(plan, measurement)
    partial_viable = lambda partial, available: legal.can_complete(
        partial,
        available,
        team_size=policy.team_size,
    )

    started = perf_counter()
    discovery = generate_multi_view_candidate_discovery(
        roster,
        views,
        team_size=policy.team_size,
        team_count=team_count,
        single_team_beam_width=policy.single_team_beam_width,
        single_team_global_limit=policy.single_team_global_limit,
        required_cores=(),
        single_team_per_core_limit=policy.single_team_per_core_limit,
        allocation_team_beam_width=policy.allocation_team_beam_width,
        allocation_team_options_per_state=policy.allocation_team_options_per_state,
        allocation_beam_width=policy.allocation_beam_width,
        allocation_limit=policy.allocation_limit,
        legal=legal,
        placement_expander=_placement_expander(policy.placement_mode),
        partial_viable=partial_viable,
    )
    proxy_rows = select_proxy_view_candidates(
        discovery.ordinary_teams,
        views,
        limit_per_view=proxy_view_limit_per_view,
        legal=legal,
    )
    proxy_teams = tuple(row.members for row in proxy_rows)
    candidate_stream = _interleave_team_channels(
        discovery.protected_teams,
        proxy_teams,
    )

    candidates = _common_candidate_map(measurement)
    for team in candidate_stream:
        if evaluator.stats.simulate_calls >= candidate_call_budget:
            break
        if team in candidates:
            continue
        result = evaluator.evaluate(team, **evaluate_kwargs)
        candidates[team] = CandidateTeam(
            members=team,
            proxy_score=0.0,
            simulated_score=result.score,
            source=f"common-marginal-policy:{name}",
        )

    used = evaluator.stats.simulate_calls
    if used != candidate_call_budget:
        raise ValueError(
            f"policy {name!r} could spend only {used}/{candidate_call_budget} "
            "new candidate Moris calls; widen discovery or lower the comparison budget"
        )

    allocation = select_global_allocation(
        candidates.values(),
        team_count=team_count,
        require_simulated=True,
    )
    if allocation is None or len(allocation.teams) != team_count:
        raise ValueError(
            f"policy {name!r} did not produce a complete {team_count}-team allocation"
        )
    runtime_s = perf_counter() - started
    cheap_expanded = sum(
        bundle.ordinary.expanded_states + bundle.allocation.expanded_states
        for _view, bundle in discovery.bundles
    )
    return PolicyRun(
        name=name,
        candidate_simulate_calls=used,
        runtime_s=runtime_s,
        final_damage=float(allocation.total_score),
        final_team_count=len(allocation.teams),
        evaluated_candidate_count=len(candidates),
        stream_count=len(candidate_stream),
        ordinary_candidate_count=len(discovery.ordinary_teams),
        protected_team_count=len(discovery.protected_teams),
        cheap_expanded_states=cheap_expanded,
        allocation=_allocation_rows(allocation),
    )


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
        raise ValueError("strict Worker account audit failed before common-marginal sweep")

    plan_payload = base.load(args.plan)
    config = dict(plan_payload.get("config") or {})
    if config.get("rng_mode") not in (None, "expected"):
        raise ValueError("common-marginal sweep requires rng_mode=expected")
    config["rng_mode"] = "expected"
    config.setdefault("immune_blocks_burst", True)
    enemy = dict(plan_payload.get("enemy") or {})
    seed = int(plan_payload.get("seed", 42))
    team_count = int(plan_payload["team_count"])

    demand = plan_payload.get("structural_demand")
    if not isinstance(demand, dict):
        raise ValueError("plan.structural_demand must be an object")
    team_size = int(demand["team_size"])
    if team_size * team_count > len(snapshot.roster):
        raise ValueError("owned roster is too small for requested allocation")

    search = plan_payload.get("search")
    if not isinstance(search, dict):
        raise ValueError("plan.search must be an object")
    required = (
        "common_marginal_simulate_call_budget",
        "candidate_simulate_call_budget",
        "positions_per_candidate",
        "proxy_view_limit_per_view",
        "policy_variants",
    )
    missing = tuple(key for key in required if key not in search)
    if missing:
        raise ValueError(
            "plan.search missing common-marginal sweep fields: " + ", ".join(missing)
        )
    common_marginal_budget = int(search["common_marginal_simulate_call_budget"])
    candidate_call_budget = int(search["candidate_simulate_call_budget"])
    positions_per_candidate = int(search["positions_per_candidate"])
    proxy_view_limit_per_view = int(search["proxy_view_limit_per_view"])
    policies = sweep_parser.parse_policy_variants(search, team_size=team_size)

    refs_raw = plan_payload.get("reference_teams")
    if not isinstance(refs_raw, list) or not refs_raw:
        raise ValueError("plan.reference_teams must be a non-empty list")
    references = tuple(
        base.team(row, f"plan.reference_teams[{index}]")
        for index, row in enumerate(refs_raw)
    )
    owned = set(snapshot.roster)
    for index, team in enumerate(references):
        missing_owned = set(team) - owned
        if missing_owned:
            raise ValueError(
                f"reference[{index}] contains unowned characters: {sorted(missing_owned)}"
            )

    validator = BurstStructureValidator.from_moris(config=config)
    for index, team in enumerate(references):
        if not validator(team):
            raise ValueError(f"reference[{index}] is hard-illegal: {team}")

    marginal_plan = plan_candidate_specific_marginals(
        snapshot.roster,
        references,
        positions_per_candidate=positions_per_candidate,
        legal=validator,
    )
    if marginal_plan.unplanned_candidates:
        raise ValueError(
            "common marginal plan left unplanned roster members: "
            f"{marginal_plan.unplanned_candidates}"
        )

    dry = {
        "engine_commit": args.engine_commit,
        "snapshot_id": snapshot.snapshot_id,
        "roster_count": len(snapshot.roster),
        "reference_count": len(references),
        "planned_probe_count": marginal_plan.planned_probe_count,
        "used_reference_count": len(marginal_plan.used_reference_teams),
        "common_marginal_simulate_call_budget": common_marginal_budget,
        "candidate_simulate_call_budget_per_policy": candidate_call_budget,
        "proxy_view_limit_per_view": proxy_view_limit_per_view,
        "policy_names": list(policies),
        "refinement": "excluded",
        "external_seeds": "excluded",
    }
    if args.dry_run:
        print(json.dumps(dry, ensure_ascii=False, indent=2))
        return

    evaluate_kwargs = {
        "config": config,
        "enemy": enemy,
        "seed": seed,
        "verbose": False,
    }
    common_evaluator = MorisEvaluator.from_moris_snapshot(
        engine_commit=args.engine_commit,
        snapshot=snapshot,
        use_cache=True,
    )
    common_started = perf_counter()
    measurement = measure_planned_marginals_with_candidates(
        BudgetedEvaluator(common_evaluator, SearchBudget(common_marginal_budget)),
        marginal_plan,
        evaluate_kwargs=evaluate_kwargs,
    )
    common_runtime_s = perf_counter() - common_started
    if measurement.plan_complete is not True:
        raise ValueError(
            "common marginal budget did not complete the fixed plan; "
            f"unobserved={measurement.unobserved_candidates}"
        )
    if set(measurement.values) != set(snapshot.roster):
        missing_values = set(snapshot.roster) - set(measurement.values)
        raise ValueError(f"common marginal measurement missed roster members: {sorted(missing_values)}")

    common_candidates = _common_candidate_map(measurement)
    common_allocation = select_global_allocation(
        common_candidates.values(),
        team_count=team_count,
        require_simulated=True,
    )
    common_baseline_damage = (
        None if common_allocation is None else float(common_allocation.total_score)
    )

    runs: list[PolicyRun] = []
    for name, policy in policies.items():
        evaluator = MorisEvaluator.from_moris_snapshot(
            engine_commit=args.engine_commit,
            snapshot=snapshot,
            use_cache=True,
        )
        runs.append(
            run_policy_after_common_marginal(
                evaluator,
                name=name,
                policy=policy,
                roster=tuple(snapshot.roster),
                plan=marginal_plan,
                measurement=measurement,
                candidate_call_budget=candidate_call_budget,
                proxy_view_limit_per_view=proxy_view_limit_per_view,
                team_count=team_count,
                legal=validator,
                evaluate_kwargs=evaluate_kwargs,
            )
        )

    observed_calls = {row.candidate_simulate_calls for row in runs}
    if observed_calls != {candidate_call_budget}:
        raise AssertionError("equal candidate-call invariant was lost")

    output = {
        **dry,
        "common_marginal": {
            "actual_simulate_calls": common_evaluator.stats.simulate_calls,
            "runtime_s": common_runtime_s,
            "evaluated_candidate_count": len(common_candidates),
            "baseline_final_damage": common_baseline_damage,
            "baseline_allocation": [
                {"team": list(team), "damage": damage}
                for team, damage in _allocation_rows(common_allocation)
            ],
        },
        "runs": {
            row.name: {
                "candidate_simulate_calls": row.candidate_simulate_calls,
                "runtime_s": row.runtime_s,
                "final_damage": row.final_damage,
                "gain_over_common_baseline": (
                    None
                    if common_baseline_damage is None
                    else row.final_damage - common_baseline_damage
                ),
                "final_team_count": row.final_team_count,
                "evaluated_candidate_count": row.evaluated_candidate_count,
                "candidate_stream_count": row.stream_count,
                "ordinary_candidate_count": row.ordinary_candidate_count,
                "protected_team_count": row.protected_team_count,
                "cheap_expanded_states": row.cheap_expanded_states,
                "allocation": [
                    {"team": list(team), "damage": damage}
                    for team, damage in row.allocation
                ],
            }
            for row in runs
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
