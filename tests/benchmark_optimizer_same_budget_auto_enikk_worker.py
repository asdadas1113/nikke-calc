"""Automatic Worker Pure-vs-Meta benchmark with Enikk composition preparation.

This wrapper owns only common setup before the canonical automatic comparison:
1. parse an Enikk Teams dump by repository resource ids;
2. gate it against the full owned roster;
3. use a separate Moris evaluator to resolve bounded unknown slot placements;
4. resolve either explicit meta epochs OR curated change events for the owned roster;
5. write selected ordered references, optional exploration-only seeds, and resolved
   explicit epochs into temporary inputs;
6. delegate the actual Pure-vs-Meta comparison to
   ``benchmark_optimizer_same_budget_auto_worker.py``.

Reference discovery calls are reported separately and are never hidden inside one
mode's budget. External uses/max/average damage never become optimizer scores.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

import benchmark_optimizer_same_budget_account as base  # noqa: E402

from optimizer import (  # noqa: E402
    BurstStructureValidator,
    MorisEvaluator,
    SearchBudget,
    build_worker_account_bundle,
    collect_enikk_team_dump_compositions,
    prepare_external_references,
)
from optimizer.meta_epoch_input import resolve_meta_epoch_input  # noqa: E402

AUTO_RUNNER = TEST_DIR / "benchmark_optimizer_same_budget_auto_worker.py"


def _append_external_seeds(plan: dict[str, Any], prepared, mode: str) -> None:
    if mode not in {"off", "both", "pure", "meta"}:
        raise ValueError("reference_discovery.external_seed_mode must be off/both/pure/meta")
    if mode == "off":
        return

    exact_rows = [
        {"members": list(row.members), "source": row.source}
        for row in prepared.hypotheses.seeds.exact_seeds
    ]
    core_rows = [
        {"members": list(row.members), "source": row.source}
        for row in prepared.hypotheses.seeds.core_seeds
    ]
    targets = []
    if mode in {"both", "pure"}:
        targets.append("pure_seeds")
    if mode in {"both", "meta"}:
        targets.append("meta_seeds")
    for key in targets:
        existing = plan.get(key)
        if existing is None:
            existing = {}
            plan[key] = existing
        if not isinstance(existing, dict):
            raise ValueError(f"plan.{key} must be an object")
        current_exact = existing.setdefault("exact", [])
        current_core = existing.setdefault("core", [])
        if not isinstance(current_exact, list) or not isinstance(current_core, list):
            raise ValueError(f"plan.{key}.exact/core must be lists")
        current_exact.extend(exact_rows)
        current_core.extend(core_rows)


def _source_summary(collection, prepared) -> dict[str, Any]:
    return {
        "parsed_evidence_count": len(collection.evidence),
        "malformed_row_count": len(collection.malformed_rows),
        "ownership_or_mapping_skip_count": len(
            prepared.hypotheses.skipped_before_adaptation
        ),
        "reference_hypothesis_count": len(
            prepared.hypotheses.references.compositions
        ),
        "selected_reference_count": len(prepared.references),
        "common_reference_simulate_calls": prepared.common_simulate_calls,
        "unfulfilled_reference_sources": list(prepared.discovery.unfulfilled_sources),
        "external_exact_seed_count": len(prepared.hypotheses.seeds.exact_seeds),
        "external_core_seed_count": len(prepared.hypotheses.seeds.core_seeds),
    }


def _resolved_meta_payload(
    payload: dict[str, Any],
    roster: Sequence[str],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Normalize epochs/change_events into the legacy explicit ``epochs`` shape.

    The canonical auto-worker runner can therefore stay unchanged. Presence of a
    key counts as choosing that mode: even ``epochs: {}`` together with
    ``change_events: []`` is rejected as ambiguous.
    """

    parsed = base.parse_meta_evidence(payload)
    explicit_epochs = parsed["epochs"] if "epochs" in payload else None
    event_rows = payload.get("change_events") if "change_events" in payload else None
    if event_rows is not None and (
        not isinstance(event_rows, list)
        or not all(isinstance(row, dict) for row in event_rows)
    ):
        raise ValueError("meta.change_events must be a list of objects")

    resolved = resolve_meta_epoch_input(
        roster,
        through=parsed["completed_through"],
        explicit_epochs=explicit_epochs,
        change_event_rows=event_rows,
        source="benchmark-meta-epoch-input",
    )
    out = json.loads(json.dumps(payload, ensure_ascii=False))
    out.pop("change_events", None)
    out["epochs"] = {
        name: {
            "knowledge": row.knowledge.value,
            **(
                {"valid_from": row.valid_from.isoformat()}
                if row.valid_from is not None
                else {}
            ),
            "source": row.source,
            "reason": row.reason,
        }
        for name, row in resolved.items()
    }
    counts: dict[str, int] = {}
    for row in resolved.values():
        counts[row.knowledge.value] = counts.get(row.knowledge.value, 0) + 1
    return out, counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--meta", type=Path, required=True)
    ap.add_argument("--engine-commit", required=True)
    ap.add_argument("--enikk-teams-dump", type=Path, required=True)
    ap.add_argument("--enikk-raid", type=int, required=True)
    ap.add_argument("--preferred-area", type=int)
    ap.add_argument("--level-mode", choices=("fixed", "sync"), default="fixed")
    ap.add_argument("--unknown-policy", choices=("error", "moris-default"), default="error")
    args = ap.parse_args()

    bundle = build_worker_account_bundle(
        base.load(args.worker),
        preferred_area=args.preferred_area,
        level_mode=args.level_mode,
        unknown_policy=args.unknown_policy,
    )
    snapshot = bundle.snapshot
    if snapshot.unknown_policy == "error" and snapshot.blocking_unknowns:
        raise ValueError("strict Worker account audit failed before Enikk reference preparation")

    plan = base.load(args.plan)
    meta_payload, epoch_counts = _resolved_meta_payload(
        base.load(args.meta),
        snapshot.roster,
    )
    config = dict(plan.get("config") or {})
    if config.get("rng_mode") not in (None, "expected"):
        raise ValueError("same-budget benchmark requires rng_mode=expected")
    config["rng_mode"] = "expected"
    config.setdefault("immune_blocks_burst", True)
    enemy = dict(plan.get("enemy") or {})
    seed = int(plan.get("seed", 42))

    demand_row = plan.get("structural_demand")
    if not isinstance(demand_row, dict):
        raise ValueError("plan.structural_demand must be an object")
    team_size = int(demand_row["team_size"])

    ref_policy = plan.get("reference_discovery")
    if not isinstance(ref_policy, dict):
        raise ValueError("plan.reference_discovery must be an object")
    required = (
        "simulate_call_budget",
        "max_placements_per_composition",
        "external_seed_mode",
    )
    missing = tuple(name for name in required if name not in ref_policy)
    if missing:
        raise ValueError(
            "plan.reference_discovery missing explicit fields: " + ", ".join(missing)
        )
    reference_budget = SearchBudget(int(ref_policy["simulate_call_budget"]))
    max_placements = int(ref_policy["max_placements_per_composition"])
    external_seed_mode = str(ref_policy["external_seed_mode"])

    collection = collect_enikk_team_dump_compositions(
        args.enikk_teams_dump.read_text(encoding="utf-8"),
        raid=args.enikk_raid,
    )
    validator = BurstStructureValidator.from_moris(config=config)
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
    prepared = prepare_external_references(
        common_evaluator,
        collection.evidence,
        owned_roster=snapshot.roster,
        budget=reference_budget,
        max_placements_per_composition=max_placements,
        team_size=team_size,
        legal=validator,
        evaluate_kwargs=evaluate_kwargs,
    )
    if not prepared.references:
        raise ValueError("Enikk preparation produced no owned, hard-legal Moris references")

    delegated_plan = json.loads(json.dumps(plan, ensure_ascii=False))
    delegated_plan["reference_teams"] = [list(team) for team in prepared.references]
    _append_external_seeds(delegated_plan, prepared, external_seed_mode)

    with tempfile.TemporaryDirectory(prefix="nikke-optimizer-enikk-") as tmp:
        root = Path(tmp)
        plan_path = root / "plan.json"
        meta_path = root / "meta.json"
        plan_path.write_text(
            json.dumps(delegated_plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        meta_path.write_text(
            json.dumps(meta_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(AUTO_RUNNER),
            "--worker",
            str(args.worker),
            "--plan",
            str(plan_path),
            "--meta",
            str(meta_path),
            "--engine-commit",
            args.engine_commit,
            "--level-mode",
            args.level_mode,
            "--unknown-policy",
            args.unknown_policy,
        ]
        if args.preferred_area is not None:
            command.extend(["--preferred-area", str(args.preferred_area)])
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            if completed.stdout:
                print(completed.stdout, end="", file=sys.stdout)
            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)
            raise SystemExit(completed.returncode)

        result = json.loads(completed.stdout)
        result["external_reference_setup"] = {
            "source": f"enikk:S{args.enikk_raid}:teams-dump",
            "external_seed_mode": external_seed_mode,
            **_source_summary(collection, prepared),
        }
        result["meta_epoch_setup"] = {
            "resolved_owned_character_count": len(snapshot.roster),
            "knowledge_counts": dict(sorted(epoch_counts.items())),
            "input_mode": (
                "change_events"
                if "change_events" in base.load(args.meta)
                else "explicit_epochs"
                if "epochs" in base.load(args.meta)
                else "none"
            ),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
