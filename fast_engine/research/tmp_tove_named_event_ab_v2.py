from __future__ import annotations

import subprocess
import sys

from fast_engine.research import tmp_tove_named_event_ab as ab


def run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True)


def main() -> None:
    # Baseline in a child process so patched modules are never shadowed by the
    # parent's pre-patch import cache.
    run(
        sys.executable,
        "-c",
        "from fast_engine.research.tmp_tove_named_event_ab import baseline; baseline()",
    )
    ab.patch_runner_worktree()
    run("git", "diff", "--check")
    run(
        "git", "diff", "--",
        "fast_engine/engine/dispatcher.py",
        "fast_engine/engine/score.py",
        "fast_engine/tests/test_named_buff_event_runtime.py",
    )
    ab.write_tmp_regression()
    run(
        sys.executable, "-m", "unittest", "-v",
        "fast_engine.tests.test_damage_dynamic_ammo_charge",
        "fast_engine.tests.test_named_buff_event_runtime",
        "fast_engine.tests.test_tmp_tove_pct_named_event",
    )
    run(
        sys.executable,
        "-c",
        "from fast_engine.research.tmp_tove_named_event_ab import public_delta; public_delta()",
    )
    run(
        sys.executable, "-m", "unittest", "discover",
        "-s", "fast_engine/tests", "-p", "test_*.py",
    )


if __name__ == "__main__":
    main()
