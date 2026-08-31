"""Run the bounded automatic Pure-vs-Meta benchmark across anonymous accounts.

Account payloads remain local. ``--workers`` may point to a directory of Worker
JSON files, one Worker JSON file, or a ZIP containing Worker JSON files. ZIP
members are materialized only into a temporary directory for the child benchmark.
The default aggregate output replaces source filenames and snapshot hashes with
``sample_001`` style labels.

Each account delegates to ``benchmark_optimizer_same_budget_auto_enikk_worker.py``
so owned reference compositions are resolved independently before Pure and Meta
receive equal NEW Moris simulate-call budgets. This script aggregates results; it
does not introduce another scoring model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator, Sequence

TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parent
RUNNER = TEST_DIR / "benchmark_optimizer_same_budget_auto_enikk_worker.py"


@dataclass(frozen=True)
class WorkerInput:
    source_label: str
    path: Path


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: Worker JSON root must be an object")
    return value


def _zip_member_names(path: Path) -> tuple[str, ...]:
    with zipfile.ZipFile(path) as archive:
        names = []
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".json"):
                continue
            member = Path(info.filename)
            if member.is_absolute() or ".." in member.parts:
                raise ValueError(f"unsafe ZIP member path: {info.filename!r}")
            names.append(info.filename)
    return tuple(sorted(names))


@contextmanager
def materialize_workers(source: Path) -> Iterator[tuple[WorkerInput, ...]]:
    """Yield local Worker JSON paths without persisting ZIP contents."""

    if source.is_dir():
        paths = tuple(sorted(path for path in source.iterdir() if path.suffix.lower() == ".json"))
        if not paths:
            raise ValueError(f"no JSON workers found in {source}")
        for path in paths:
            _load_json_object(path)
        yield tuple(WorkerInput(path.name, path) for path in paths)
        return

    if source.is_file() and source.suffix.lower() == ".json":
        _load_json_object(source)
        yield (WorkerInput(source.name, source),)
        return

    if source.is_file() and source.suffix.lower() == ".zip":
        names = _zip_member_names(source)
        if not names:
            raise ValueError(f"no JSON workers found in {source}")
        with tempfile.TemporaryDirectory(prefix="nikke-transfer-workers-") as tmp:
            root = Path(tmp)
            materialized: list[WorkerInput] = []
            with zipfile.ZipFile(source) as archive:
                for index, name in enumerate(names, start=1):
                    payload = json.loads(archive.read(name).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError(f"{name}: Worker JSON root must be an object")
                    path = root / f"worker-{index:03d}.json"
                    path.write_text(
                        json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    materialized.append(WorkerInput(name, path))
            yield tuple(materialized)
        return

    raise ValueError("--workers must be a Worker JSON file, directory, or ZIP")


def _result_row(label: str, result: dict[str, Any]) -> dict[str, Any]:
    pure = result["pure"]
    meta = result["meta"]
    return {
        "sample": label,
        "status": "ok",
        "roster_count": int(result["roster_count"]),
        "pure_search_roster_count": int(result["pure_search_roster_count"]),
        "meta_search_roster_count": int(result["meta_search_roster_count"]),
        "initial_cold_count": len(result.get("meta_initial_cold") or ()),
        "restored_count": len(result.get("meta_restored") or ()),
        "explored_cold_count": len(result.get("meta_explored_cold") or ()),
        "still_deferred_cold_count": len(result.get("meta_still_deferred_cold") or ()),
        "simulate_calls": int(result["actual_equal_simulate_calls"]),
        "pure_final_damage": float(pure["final_damage"]),
        "meta_final_damage": float(meta["final_damage"]),
        "damage_delta": float(result["meta_minus_pure_damage"]),
        "relative_damage_delta": result.get("meta_minus_pure_relative"),
        "pure_runtime_s": float(pure["runtime_s"]),
        "meta_runtime_s": float(meta["runtime_s"]),
        "pure_simulate_s": float(pure.get("simulate_s", pure["runtime_s"])),
        "meta_simulate_s": float(meta.get("simulate_s", meta["runtime_s"])),
        "pure_batch_requests": int(pure.get("batch_requests", 0)),
        "meta_batch_requests": int(meta.get("batch_requests", 0)),
        "pure_max_batch_size": int(pure.get("max_batch_size", 1)),
        "meta_max_batch_size": int(meta.get("max_batch_size", 1)),
        "pure_stage_calls": dict(pure["stage_calls"]),
        "meta_stage_calls": dict(meta["stage_calls"]),
        "pure_allocation": list(pure.get("allocation") or ()),
        "meta_allocation": list(meta.get("allocation") or ()),
        "false_deferred": result.get("false_deferred"),
        "false_deferred_reason": result.get("false_deferred_reason"),
    }


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in rows if row.get("status") == "ok"]
    failed = [row for row in rows if row.get("status") != "ok"]
    wins = sum(float(row["damage_delta"]) > 0.0 for row in successful)
    losses = sum(float(row["damage_delta"]) < 0.0 for row in successful)
    ties = len(successful) - wins - losses
    deltas = [float(row["relative_damage_delta"]) for row in successful if row.get("relative_damage_delta") is not None]
    return {
        "sample_count": len(rows),
        "successful_count": len(successful),
        "failed_count": len(failed),
        "meta_win_count": wins,
        "tie_count": ties,
        "pure_win_count": losses,
        "mean_relative_damage_delta": (sum(deltas) / len(deltas)) if deltas else None,
        "min_relative_damage_delta": min(deltas) if deltas else None,
        "max_relative_damage_delta": max(deltas) if deltas else None,
        "total_initial_cold": sum(int(row["initial_cold_count"]) for row in successful),
        "total_restored": sum(int(row["restored_count"]) for row in successful),
        "total_explored_cold": sum(int(row["explored_cold_count"]) for row in successful),
        "total_still_deferred_cold": sum(int(row["still_deferred_cold_count"]) for row in successful),
    }


def _child_command(args: argparse.Namespace, worker: Path) -> list[str]:
    command = [
        sys.executable,
        str(RUNNER),
        "--worker",
        str(worker),
        "--plan",
        str(args.plan),
        "--meta",
        str(args.meta),
        "--engine-commit",
        args.engine_commit,
        "--enikk-teams-dump",
        str(args.enikk_teams_dump),
        "--enikk-raid",
        str(args.enikk_raid),
        "--level-mode",
        args.level_mode,
        "--unknown-policy",
        args.unknown_policy,
        "--evaluation-batch-size",
        str(args.evaluation_batch_size),
    ]
    if args.preferred_area is not None:
        command.extend(["--preferred-area", str(args.preferred_area)])
    return command


def _run_one(
    args: argparse.Namespace,
    worker: WorkerInput,
    index: int,
) -> tuple[int, dict[str, Any]]:
    label = f"sample_{index:03d}"
    completed = subprocess.run(
        _child_command(args, worker.path),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        row: dict[str, Any] = {
            "sample": label,
            "status": "error",
            "error": (completed.stderr or completed.stdout or "child benchmark failed").strip(),
        }
    else:
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            row = {
                "sample": label,
                "status": "error",
                "error": f"child produced invalid JSON: {exc}",
            }
        else:
            row = _result_row(label, result)
    if args.include_source_labels:
        row["source_label"] = worker.source_label
    return index, row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--meta", type=Path, required=True)
    ap.add_argument("--engine-commit", required=True)
    ap.add_argument("--enikk-teams-dump", type=Path, required=True)
    ap.add_argument("--enikk-raid", type=int, required=True)
    ap.add_argument("--preferred-area", type=int)
    ap.add_argument("--level-mode", choices=("fixed", "sync"), default="fixed")
    ap.add_argument("--unknown-policy", choices=("error", "moris-default"), default="error")
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="independent account subprocesses to run concurrently (1-6)",
    )
    ap.add_argument(
        "--evaluation-batch-size",
        type=int,
        default=6,
        help="candidate evaluation round width; 6 matches Moris browser pool max",
    )
    ap.add_argument("--include-source-labels", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    if not 1 <= args.parallel <= 6:
        raise ValueError("--parallel must be between 1 and 6")
    if args.evaluation_batch_size <= 0:
        raise ValueError("--evaluation-batch-size must be positive")
    if args.fail_fast and args.parallel != 1:
        raise ValueError("--fail-fast requires --parallel=1")

    started = perf_counter()
    rows: list[dict[str, Any]] = []
    with materialize_workers(args.workers) as workers:
        indexed = tuple(enumerate(workers, start=1))
        if args.parallel == 1:
            for index, worker in indexed:
                _index, row = _run_one(args, worker, index)
                rows.append(row)
                if args.fail_fast and row.get("status") != "ok":
                    break
        else:
            by_index: dict[int, dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=min(args.parallel, len(indexed))) as pool:
                futures = {
                    pool.submit(_run_one, args, worker, index): index
                    for index, worker in indexed
                }
                for future in as_completed(futures):
                    index, row = future.result()
                    by_index[index] = row
            rows = [by_index[index] for index, _worker in indexed]
    wall_s = perf_counter() - started

    output = {
        "benchmark": "anonymous-bounded-transfer-set",
        "engine_commit": args.engine_commit,
        "enikk_raid": args.enikk_raid,
        "parallel_accounts": args.parallel,
        "evaluation_batch_size": args.evaluation_batch_size,
        "wall_s": wall_s,
        "summary": summarize(rows),
        "accounts": rows,
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
