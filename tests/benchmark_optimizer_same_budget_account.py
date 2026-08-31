"""Historical research Pure-vs-Meta benchmark under equal Moris call counts.

This runner is local-only by design. It consumes gitignored profile/raw account
files plus an explicit search plan and normalized meta-evidence file, then runs
Pure and Meta-guided search through ``run_same_budget_comparison``. Nothing is
uploaded and the script only prints JSON to stdout.

This file intentionally replays the earlier descriptive Meta evidence format via
explicit ``Research*``/``research_*`` APIs. It is not a production Cold entry point.

The benchmark does not invent a roster-wide candidate generator. Reference teams,
candidate-team order, refinement order, search caps, and per-mode seed policy are
explicit plan inputs. Meta changes only which owned characters receive ordinary
search attention; seed-only Cold bypass remains bounded and score-neutral.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from optimizer import (
    BurstStructureValidator,
    CoreSeed,
    ResearchEnikkSeasonUsageSnapshot,
    ExactCompSeed,
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    MorisEvaluator,
    SoloRaidPeriod,
    SoloRaidSchedule,
    StructuralDemand,
    build_burst_role_map,
    derive_overload_piece_evidence,
    normalize_account_bundle,
    research_prepare_meta_guided_search_roster,
    run_anytime_search_round,
)
from optimizer.same_budget import run_same_budget_comparison


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def _date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label}: expected ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label}: invalid ISO date {value!r}") from exc


def team(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{label}: expected non-empty string list")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label}: duplicate members")
    return result


def names(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{label}: expected string list")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label}: duplicate names")
    return result


def parse_seeds(value: Any, label: str) -> tuple[tuple[ExactCompSeed, ...], tuple[CoreSeed, ...]]:
    if value is None:
        return (), ()
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected object")
    exact_rows = value.get("exact") or []
    core_rows = value.get("core") or []
    if not isinstance(exact_rows, list) or not isinstance(core_rows, list):
        raise ValueError(f"{label}: exact/core must be lists")

    exact: list[ExactCompSeed] = []
    for index, row in enumerate(exact_rows):
        if not isinstance(row, dict):
            raise ValueError(f"{label}.exact[{index}]: expected object")
        exact.append(
            ExactCompSeed(
                team(row.get("members"), f"{label}.exact[{index}].members"),
                source=str(row.get("source") or f"{label}:exact:{index}"),
            )
        )

    cores: list[CoreSeed] = []
    for index, row in enumerate(core_rows):
        if not isinstance(row, dict):
            raise ValueError(f"{label}.core[{index}]: expected object")
        members = team(row.get("members"), f"{label}.core[{index}].members")
        if len(members) < 2:
            raise ValueError(f"{label}.core[{index}]: requires at least two members")
        cores.append(
            CoreSeed(
                members,
                source=str(row.get("source") or f"{label}:core:{index}"),
            )
        )
    return tuple(exact), tuple(cores)


def parse_meta_evidence(payload: dict[str, Any]):
    completed_through = _date(payload.get("completed_through"), "meta.completed_through")

    policy_row = payload.get("policy")
    if not isinstance(policy_row, dict):
        raise ValueError("meta.policy must be an object")
    policy = LowUsagePolicy(
        completed_seasons=int(policy_row["completed_seasons"]),
        max_peak_usage=float(policy_row["max_peak_usage"]),
    )

    schedule_row = payload.get("schedule")
    if not isinstance(schedule_row, dict):
        raise ValueError("meta.schedule must be an object")
    periods_raw = schedule_row.get("periods")
    if not isinstance(periods_raw, list):
        raise ValueError("meta.schedule.periods must be a list")
    periods = tuple(
        SoloRaidPeriod(
            raid=int(row["raid"]),
            start_on=_date(row["start_on"], f"meta.schedule.periods[{i}].start_on"),
            end_on=_date(row["end_on"], f"meta.schedule.periods[{i}].end_on"),
        )
        for i, row in enumerate(periods_raw)
        if isinstance(row, dict)
    )
    if len(periods) != len(periods_raw):
        raise ValueError("meta.schedule.periods rows must be objects")
    schedule = SoloRaidSchedule(
        periods=periods,
        complete=bool(schedule_row.get("complete")),
        source=str(schedule_row.get("source") or "local-meta-plan"),
    )

    epochs_raw = payload.get("epochs") or {}
    if not isinstance(epochs_raw, dict):
        raise ValueError("meta.epochs must be an object")
    epochs: dict[str, MetaEpochEvidence] = {}
    for character, row in epochs_raw.items():
        if not isinstance(row, dict):
            raise ValueError(f"meta.epochs[{character!r}] must be an object")
        try:
            knowledge = MetaEpochKnowledge(str(row.get("knowledge")))
        except ValueError as exc:
            raise ValueError(f"meta.epochs[{character!r}].knowledge is invalid") from exc
        valid_from = None
        if knowledge is MetaEpochKnowledge.KNOWN:
            valid_from = _date(row.get("valid_from"), f"meta.epochs[{character!r}].valid_from")
        epochs[str(character)] = MetaEpochEvidence(
            character=str(character),
            knowledge=knowledge,
            valid_from=valid_from,
            source=str(row.get("source") or "local-meta-plan"),
            reason=str(row.get("reason") or ""),
        )

    snapshots_raw = payload.get("snapshots")
    if not isinstance(snapshots_raw, list):
        raise ValueError("meta.snapshots must be a list")
    snapshots: list[ResearchEnikkSeasonUsageSnapshot] = []
    for i, row in enumerate(snapshots_raw):
        if not isinstance(row, dict):
            raise ValueError(f"meta.snapshots[{i}] must be an object")
        appearances = row.get("player_appearances") or {}
        if not isinstance(appearances, dict):
            raise ValueError(f"meta.snapshots[{i}].player_appearances must be an object")
        mapped = row.get("mapped_characters") or []
        unknown = row.get("unknown_external_names") or []
        if not isinstance(mapped, list) or not all(isinstance(x, str) for x in mapped):
            raise ValueError(f"meta.snapshots[{i}].mapped_characters must be a string list")
        if not isinstance(unknown, list) or not all(isinstance(x, str) for x in unknown):
            raise ValueError(f"meta.snapshots[{i}].unknown_external_names must be a string list")
        snapshots.append(
            ResearchEnikkSeasonUsageSnapshot(
                raid=int(row["raid"]),
                boss=None if row.get("boss") is None else str(row.get("boss")),
                player_count=int(row["player_count"]),
                players_with_teams=int(row["players_with_teams"]),
                incomplete_player_rows=int(row["incomplete_player_rows"]),
                player_appearances={str(k): int(v) for k, v in appearances.items()},
                mapped_characters=frozenset(mapped),
                unknown_external_names=tuple(sorted(set(unknown))),
            )
        )

    return {
        "completed_through": completed_through,
        "policy": policy,
        "schedule": schedule,
        "epochs": epochs,
        "snapshots": tuple(snapshots),
        "restoration_batch_size": int(payload["restoration_batch_size"]),
        "cold_exploration_limit": int(payload["cold_exploration_limit"]),
        "protected_names": names(payload.get("protected_names"), "meta.protected_names"),
    }


def _filter_teams(rows: tuple[tuple[str, ...], ...], allowed: set[str]) -> tuple[tuple[str, ...], ...]:
    return tuple(row for row in rows if set(row) <= allowed)


def _allocation_rows(result) -> list[dict[str, Any]]:
    if result is None or result.allocation is None:
        return []
    return [
        {"members": list(row.members), "score": row.score, "source": row.source}
        for row in result.allocation.teams
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--meta", type=Path, required=True)
    ap.add_argument("--engine-commit", required=True)
    ap.add_argument("--level-mode", choices=("fixed", "sync"), default="fixed")
    ap.add_argument("--unknown-policy", choices=("error", "moris-default"), default="error")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    profile = load(args.profile)
    raw = load(args.raw)
    plan = load(args.plan)
    meta_payload = load(args.meta)
    meta = parse_meta_evidence(meta_payload)

    snapshot = normalize_account_bundle(
        profile,
        raw,
        level_mode=args.level_mode,
        unknown_policy=args.unknown_policy,
    )
    if snapshot.unknown_policy == "error" and snapshot.blocking_unknowns:
        raise ValueError("strict account audit failed before benchmark")
    owned = set(snapshot.roster)

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
    positions_per_candidate = int(search["positions_per_candidate"])
    candidate_limit = int(search["candidate_limit"])
    marginal_cap = search.get("marginal_max_simulate_calls")
    marginal_cap = None if marginal_cap is None else int(marginal_cap)
    per_view = search.get("proxy_view_limit_per_view")
    per_view = None if per_view is None else int(per_view)
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
    required_roles = names(demand_row.get("required_roles"), "plan.structural_demand.required_roles")
    demand = StructuralDemand(
        team_count=team_count,
        team_size=int(demand_row["team_size"]),
        required_roles=required_roles,
    )

    refs_raw = plan.get("reference_teams")
    candidates_raw = plan.get("candidate_teams")
    if not isinstance(refs_raw, list) or not isinstance(candidates_raw, list):
        raise ValueError("plan.reference_teams and plan.candidate_teams must be lists")
    references = tuple(team(row, f"plan.reference_teams[{i}]") for i, row in enumerate(refs_raw))
    candidates = tuple(team(row, f"plan.candidate_teams[{i}]") for i, row in enumerate(candidates_raw))
    refinement_incoming = names(plan.get("refinement_incoming"), "plan.refinement_incoming")

    for label, groups in (("reference", references), ("candidate", candidates)):
        for i, row in enumerate(groups):
            missing = set(row) - owned
            if missing:
                raise ValueError(f"{label}[{i}] contains unowned characters: {sorted(missing)}")
    missing_incoming = set(refinement_incoming) - owned
    if missing_incoming:
        raise ValueError(f"refinement_incoming contains unowned characters: {sorted(missing_incoming)}")

    pure_exact, pure_core = parse_seeds(plan.get("pure_seeds"), "plan.pure_seeds")
    meta_exact, meta_core = parse_seeds(plan.get("meta_seeds"), "plan.meta_seeds")

    validator = BurstStructureValidator.from_moris(config=config)
    for label, groups in (("reference", references), ("candidate", candidates)):
        for i, row in enumerate(groups):
            if not validator(row):
                raise ValueError(f"{label}[{i}] is hard-illegal: {row}")

    overload = derive_overload_piece_evidence(profile, raw)
    roles = build_burst_role_map(validator, snapshot.roster)
    meta_prepared = research_prepare_meta_guided_search_roster(
        snapshot.roster,
        meta["snapshots"],
        meta["epochs"],
        overload,
        roles,
        demand,
        schedule=meta["schedule"],
        completed_through=meta["completed_through"],
        policy=meta["policy"],
        restoration_batch_size=meta["restoration_batch_size"],
        cold_exploration_limit=meta["cold_exploration_limit"],
        protected_names=meta["protected_names"],
    )
    if not meta_prepared.prepared.structurally_feasible:
        raise ValueError("Meta-guided roster remains structurally infeasible after Cold restoration")

    pure_roster = tuple(snapshot.roster)
    meta_roster = tuple(meta_prepared.search_roster)
    pure_allowed = set(pure_roster)
    meta_allowed = set(meta_roster)
    pure_refs = _filter_teams(references, pure_allowed)
    meta_refs = _filter_teams(references, meta_allowed)
    pure_candidates = _filter_teams(candidates, pure_allowed)
    meta_candidates = _filter_teams(candidates, meta_allowed)
    pure_incoming = tuple(name for name in refinement_incoming if name in pure_allowed)
    meta_incoming = tuple(name for name in refinement_incoming if name in meta_allowed)

    if not pure_refs or not meta_refs:
        raise ValueError("both Pure and Meta require at least one surviving reference team")
    if not pure_candidates or not meta_candidates:
        raise ValueError("both Pure and Meta require at least one surviving candidate team")

    dry = {
        "engine_commit": args.engine_commit,
        "snapshot_id": snapshot.snapshot_id,
        "roster_count": len(snapshot.roster),
        "blocking_unknown_paths": [row.path for row in snapshot.blocking_unknowns],
        "simulate_call_budget": simulate_call_budget,
        "pure_search_roster_count": len(pure_roster),
        "meta_search_roster_count": len(meta_roster),
        "meta_initial_primary": list(meta_prepared.prepared.initial_partition.primary),
        "meta_initial_cold": list(meta_prepared.prepared.initial_partition.cold),
        "meta_restored": list(meta_prepared.prepared.restored),
        "meta_explored_cold": list(meta_prepared.explored_cold),
        "meta_still_deferred_cold": list(meta_prepared.still_deferred_cold),
        "pure_reference_count": len(pure_refs),
        "meta_reference_count": len(meta_refs),
        "pure_candidate_count": len(pure_candidates),
        "meta_candidate_count": len(meta_candidates),
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
        candidate_rows: tuple[tuple[str, ...], ...],
        incoming: tuple[str, ...],
        exact_seeds: tuple[ExactCompSeed, ...],
        core_seeds: tuple[CoreSeed, ...],
        *,
        seed_roster: tuple[str, ...],
        seed_candidates: tuple[tuple[str, ...], ...],
    ):
        def runner(evaluator, budget):
            result = run_anytime_search_round(
                evaluator,
                budget=budget,
                roster=roster,
                reference_teams=refs,
                candidate_teams=candidate_rows,
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
                seed_candidate_teams=seed_candidates,
                evaluate_kwargs=evaluate_kwargs,
            )
            captured[label] = result
            return result
        return runner

    pure_runner = run_mode(
        "pure",
        pure_roster,
        pure_refs,
        pure_candidates,
        pure_incoming,
        pure_exact,
        pure_core,
        seed_roster=pure_roster,
        seed_candidates=pure_candidates,
    )
    meta_runner = run_mode(
        "meta",
        meta_roster,
        meta_refs,
        meta_candidates,
        meta_incoming,
        meta_exact,
        meta_core,
        # Seed hypotheses may temporarily inspect a still-Cold owned character
        # without promoting it into ordinary Meta marginal/refinement search.
        seed_roster=tuple(snapshot.roster),
        seed_candidates=candidates,
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
            "final_damage": comparison.pure.final_damage,
            "evaluated_candidate_count": comparison.pure.evaluated_candidate_count,
            "stage_calls": comparison.pure.stage_calls.__dict__,
            "allocation": _allocation_rows(captured.get("pure")),
            "unfulfilled_exact_seeds": [list(row.members) for row in captured["pure"].seed_selection.unfulfilled_exact],
            "unfulfilled_core_seeds": [list(row.members) for row in captured["pure"].seed_selection.unfulfilled_cores],
        },
        "meta": {
            "runtime_s": comparison.meta.runtime_s,
            "final_damage": comparison.meta.final_damage,
            "evaluated_candidate_count": comparison.meta.evaluated_candidate_count,
            "stage_calls": comparison.meta.stage_calls.__dict__,
            "allocation": _allocation_rows(captured.get("meta")),
            "unfulfilled_exact_seeds": [list(row.members) for row in captured["meta"].seed_selection.unfulfilled_exact],
            "unfulfilled_core_seeds": [list(row.members) for row in captured["meta"].seed_selection.unfulfilled_cores],
        },
        "meta_minus_pure_damage": comparison.damage_delta,
        "meta_minus_pure_relative": comparison.relative_damage_delta,
        "false_deferred": None,
        "false_deferred_reason": "unknown without exhaustive or stronger oracle",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
