"""Audit one local anonymous BlaBlaLink Worker payload before real benchmarks.

The input file is never uploaded by this runner. It normalizes the Worker payload
through the production optimizer adapter, derives exact Overload-piece evidence
from the identifier-free raw sidecar, and prints only aggregate diagnostics plus
optional names of characters whose Overload presence is already proven.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from optimizer.overload import OverloadKnowledge, derive_overload_piece_evidence
from optimizer.worker_account import WorkerAccountBundle, build_worker_account_bundle


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def summarize_worker_account(
    bundle: WorkerAccountBundle,
    *,
    include_present_names: bool = False,
) -> dict[str, Any]:
    overload = derive_overload_piece_evidence(
        bundle.profile_payload,
        bundle.raw_sidecar,
    )
    knowledge = Counter(row.knowledge.value for row in overload.values())
    piece_counts = Counter(
        str(row.piece_count)
        for row in overload.values()
        if row.piece_count is not None
    )
    result: dict[str, Any] = {
        "snapshot_id": bundle.snapshot.snapshot_id,
        "area": bundle.raw_sidecar.get("area"),
        "roster_count": len(bundle.roster),
        "blocking_unknown_count": len(bundle.blocking_unknowns),
        "blocking_unknown_paths": [row.path for row in bundle.blocking_unknowns],
        "notes": list(bundle.snapshot.notes()),
        "overload": {
            "zero": knowledge.get(OverloadKnowledge.ZERO.value, 0),
            "present": knowledge.get(OverloadKnowledge.PRESENT.value, 0),
            "unknown": knowledge.get(OverloadKnowledge.UNKNOWN.value, 0),
            "exact_piece_count_distribution": {
                key: piece_counts[key]
                for key in sorted(piece_counts, key=int)
            },
        },
    }
    if include_present_names:
        result["overload"]["present_characters"] = [
            {
                "character": name,
                "piece_count": row.piece_count,
                "source": row.source,
            }
            for name, row in overload.items()
            if row.knowledge is OverloadKnowledge.PRESENT
        ]
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=Path, required=True)
    ap.add_argument("--preferred-area", type=int)
    ap.add_argument("--level-mode", choices=("fixed", "sync"), default="fixed")
    ap.add_argument("--unknown-policy", choices=("error", "moris-default"), default="error")
    ap.add_argument("--show-overload-present", action="store_true")
    args = ap.parse_args()

    bundle = build_worker_account_bundle(
        load(args.worker),
        preferred_area=args.preferred_area,
        level_mode=args.level_mode,
        unknown_policy=args.unknown_policy,
    )
    result = summarize_worker_account(
        bundle,
        include_present_names=args.show_overload_present,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))

    if bundle.snapshot.unknown_policy == "error" and bundle.blocking_unknowns:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
