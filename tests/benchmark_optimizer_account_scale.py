"""Run the existing optimizer core against a local account-sync input.

No search heuristic lives here. The local plan explicitly supplies marginal
references, initial candidate teams, and the incoming order/budget for one-swap
refinement. Real account/profile files remain outside git.

Input may be either the canonical local ``profile + raw`` pair or one JSON
response copied from the site's BlaBlaLink Worker. Worker account identifiers are
not copied into the normalized snapshot.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from optimizer import (
    BurstStructureValidator,
    CandidateTeam,
    MorisEvaluator,
    evaluate_allocation_with_one_swap_refinement,
    normalize_account_bundle,
    normalize_blablalink_worker_payload,
)
from optimizer.marginal import measure_marginals


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def team(value, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{label}: expected non-empty string list")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label}: duplicate members")
    return result


def names(value, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{label}: expected explicit string list")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label}: duplicate names")
    return result


def check_owned(values, owned: set[str], label: str) -> None:
    missing = [name for name in values if name not in owned]
    if missing:
        raise ValueError(f"{label}: absent from account snapshot: {missing}")


def stats(ev: MorisEvaluator) -> tuple[int, int, int, float]:
    s = ev.stats
    return s.simulate_calls, s.requests, s.cache_hits, s.simulate_s


def delta(ev: MorisEvaluator, before, wall: float) -> dict:
    calls, requests, hits, sim_s = before
    s = ev.stats
    return {
        "simulate_calls": s.simulate_calls - calls,
        "requests": s.requests - requests,
        "cache_hits": s.cache_hits - hits,
        "simulate_s": s.simulate_s - sim_s,
        "wall_s": wall,
    }


def allocation_rows(allocation) -> list[dict]:
    if allocation is None:
        return []
    return [{"members": list(row.members), "score": row.score} for row in allocation.teams]


def account_snapshot(args):
    if args.worker_json is not None:
        if args.profile is not None or args.raw is not None:
            raise ValueError("--worker-json cannot be combined with --profile/--raw")
        worker = load(args.worker_json)
        return normalize_blablalink_worker_payload(
            worker,
            preferred_area=args.preferred_area,
            level_mode=args.level_mode,
            unknown_policy=args.unknown_policy,
        )

    if args.profile is None or args.raw is None:
        raise ValueError("supply either --worker-json or both --profile and --raw")
    profile = load(args.profile)
    raw = load(args.raw)
    return normalize_account_bundle(
        profile,
        raw,
        level_mode=args.level_mode,
        unknown_policy=args.unknown_policy,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", type=Path)
    ap.add_argument("--raw", type=Path)
    ap.add_argument("--worker-json", type=Path)
    ap.add_argument("--preferred-area", type=int)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--engine-commit", required=True)
    ap.add_argument("--level-mode", choices=("fixed", "sync"), default="fixed")
    ap.add_argument("--unknown-policy", choices=("error", "moris-default"), default="error")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    snapshot = account_snapshot(args)
    plan = load(args.plan)
    owned = set(snapshot.roster)

    config = dict(plan.get("config") or {})
    if config.get("rng_mode") not in (None, "expected"):
        raise ValueError("benchmark requires rng_mode=expected")
    config["rng_mode"] = "expected"
    config.setdefault("immune_blocks_burst", True)
    enemy = dict(plan.get("enemy") or {})
    seed = int(plan.get("seed", 42))
    team_count = int(plan.get("team_count", 5))
    validator = BurstStructureValidator.from_moris(config=config)

    candidate_values = plan.get("candidate_teams") or []
    if not isinstance(candidate_values, list):
        raise ValueError("candidate_teams must be a list")
    candidates = [
        CandidateTeam(team(value, f"candidate_teams[{i}]"), proxy_score=0.0, source="scale-plan")
        for i, value in enumerate(candidate_values)
    ]
    for i, row in enumerate(candidates):
        check_owned(row.members, owned, f"candidate_teams[{i}]")
        if not validator(row.members):
            raise ValueError(f"candidate_teams[{i}] is hard-illegal")

    marginal = plan.get("marginal") or {}
    if not isinstance(marginal, dict):
        raise ValueError("marginal must be an object")
    marginal_roster = names(marginal.get("roster"), "marginal.roster")
    refs = tuple(
        team(value, f"marginal.reference_teams[{i}]")
        for i, value in enumerate(marginal.get("reference_teams") or [])
    )
    check_owned(marginal_roster, owned, "marginal.roster")
    for i, row in enumerate(refs):
        check_owned(row, owned, f"marginal.reference_teams[{i}]")
        if not validator(row):
            raise ValueError(f"marginal.reference_teams[{i}] is hard-illegal")
    if bool(marginal_roster) != bool(refs):
        raise ValueError("marginal roster and references must be supplied together")

    refine = plan.get("refinement") or {}
    if not isinstance(refine, dict):
        raise ValueError("refinement must be an object")
    incoming = names(refine.get("incoming"), "refinement.incoming")
    check_owned(incoming, owned, "refinement.incoming")
    positions = refine.get("positions")
    if positions is not None:
        if not isinstance(positions, list) or not all(isinstance(x, int) for x in positions):
            raise ValueError("refinement.positions must be an integer list")
        positions = tuple(positions)
    max_new = int(refine.get("max_new", 0))

    base_result = {
        "engine_commit": args.engine_commit,
        "snapshot_id": snapshot.snapshot_id,
        "roster_count": len(owned),
        "snapshot_notes": list(snapshot.notes()),
        "blocking_unknown_paths": [row.path for row in snapshot.blocking_unknowns],
        "candidate_count": len(candidates),
        "marginal_roster_count": len(marginal_roster),
        "marginal_reference_count": len(refs),
        "refinement_incoming_count": len(incoming),
        "refinement_max_new": max_new,
        "recall": None,
        "recall_reason": "no exhaustive oracle at production roster size",
    }
    if args.dry_run:
        print(json.dumps(base_result, ensure_ascii=False, indent=2))
        return
    if snapshot.unknown_policy == "error" and snapshot.blocking_unknowns:
        raise ValueError("strict account audit failed before simulation")

    kwargs = {"config": config, "enemy": enemy, "seed": seed, "verbose": False}
    ev = MorisEvaluator.from_moris_snapshot(engine_commit=args.engine_commit, snapshot=snapshot)
    started = perf_counter()

    marginal_metrics = {"simulate_calls": 0, "requests": 0, "cache_hits": 0, "simulate_s": 0.0, "wall_s": 0.0}
    if marginal_roster:
        before = stats(ev)
        stage = perf_counter()
        measure_marginals(ev, marginal_roster, refs, legal=validator, evaluate_kwargs=kwargs)
        marginal_metrics = delta(ev, before, perf_counter() - stage)

    result = evaluate_allocation_with_one_swap_refinement(
        ev,
        candidates,
        team_count=team_count,
        legal=validator,
        refinement_incoming=incoming,
        refinement_positions=positions,
        refinement_max_new=max_new,
        evaluate_kwargs=kwargs,
    )

    fresh_total = None
    fresh_calls = 0
    if result.refined_allocation is not None:
        fresh = MorisEvaluator.from_moris_snapshot(
            engine_commit=args.engine_commit, snapshot=snapshot, use_cache=False
        )
        fresh_total = sum(fresh.evaluate(row.members, **kwargs).score for row in result.refined_allocation.teams)
        fresh_calls = fresh.stats.simulate_calls
        if abs(fresh_total - result.refined_allocation.total_score) > 1e-6:
            raise AssertionError("fresh final evaluation disagrees with refined allocation")

    base_result.update(
        {
            "marginal_stage": marginal_metrics,
            "candidate_stage": result.candidate_stage.__dict__,
            "refinement_stage": result.refinement_stage.__dict__,
            "optimizer_simulate_calls": ev.stats.simulate_calls,
            "optimizer_cache_hits": ev.stats.cache_hits,
            "initial_total": result.initial_total,
            "refined_total": result.refined_total,
            "refine_gain": result.refine_gain,
            "refine_gain_pct": result.refine_gain_pct,
            "initial_allocation": allocation_rows(result.initial_allocation),
            "refined_allocation": allocation_rows(result.refined_allocation),
            "refinement_neighbor_count": len(result.refinement_neighbors),
            "fresh_final_total": fresh_total,
            "fresh_final_calls": fresh_calls,
            "wall_s": perf_counter() - started,
        }
    )
    print(json.dumps(base_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
