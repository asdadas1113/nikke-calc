"""Run the strict Pure-vs-Meta benchmark from one local Worker JSON file.

This wrapper does not create a second benchmark implementation. It normalizes the
Worker payload through the production adapter, writes only identifier-free
profile/raw audit inputs into a temporary directory, then delegates to
``benchmark_optimizer_same_budget_account.py`` unchanged.

The original Worker file and temporary normalized account data are never written
to the repository.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from optimizer.worker_account import build_worker_account_bundle


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_RUNNER = ROOT / "tests" / "benchmark_optimizer_same_budget_account.py"


def load_worker(path: Path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def build_delegated_command(
    *,
    profile_path: Path,
    raw_path: Path,
    remaining_args: list[str],
    level_mode: str,
    unknown_policy: str,
) -> list[str]:
    return [
        sys.executable,
        str(ACCOUNT_RUNNER),
        "--profile",
        str(profile_path),
        "--raw",
        str(raw_path),
        "--level-mode",
        level_mode,
        "--unknown-policy",
        unknown_policy,
        *remaining_args,
    ]


def main() -> None:
    # Parse only Worker-specific account arguments. Every search/boss/meta option
    # remains owned by the canonical same-budget runner and is forwarded verbatim.
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--worker", type=Path, required=True)
    ap.add_argument("--preferred-area", type=int)
    ap.add_argument("--level-mode", choices=("fixed", "sync"), default="fixed")
    ap.add_argument("--unknown-policy", choices=("error", "moris-default"), default="error")
    args, remaining = ap.parse_known_args()

    bundle = build_worker_account_bundle(
        load_worker(args.worker),
        preferred_area=args.preferred_area,
        level_mode=args.level_mode,
        unknown_policy=args.unknown_policy,
    )
    if bundle.snapshot.unknown_policy == "error" and bundle.blocking_unknowns:
        paths = ", ".join(row.path for row in bundle.blocking_unknowns[:12])
        extra = len(bundle.blocking_unknowns) - 12
        if extra > 0:
            paths += f", ... +{extra}"
        raise ValueError(
            "strict Worker account audit failed before same-budget benchmark: " + paths
        )

    with tempfile.TemporaryDirectory(prefix="nikke-optimizer-worker-") as tmp:
        root = Path(tmp)
        profile_path = root / "profile.json"
        raw_path = root / "profile.raw.json"
        profile_path.write_text(
            json.dumps(bundle.profile_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raw_path.write_text(
            json.dumps(bundle.raw_sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        command = build_delegated_command(
            profile_path=profile_path,
            raw_path=raw_path,
            remaining_args=remaining,
            level_mode=args.level_mode,
            unknown_policy=args.unknown_policy,
        )
        completed = subprocess.run(command, cwd=ROOT, check=False)
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
