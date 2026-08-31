from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tests" / "benchmark_optimizer_same_budget_worker.py"
SPEC = importlib.util.spec_from_file_location("benchmark_optimizer_same_budget_worker", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


class SameBudgetWorkerWrapperTests(unittest.TestCase):
    def test_delegated_command_preserves_canonical_runner_and_remaining_args(self):
        command = RUNNER.build_delegated_command(
            profile_path=Path("/tmp/profile.json"),
            raw_path=Path("/tmp/profile.raw.json"),
            remaining_args=["--plan", "plan.json", "--meta", "meta.json", "--dry-run"],
            level_mode="sync",
            unknown_policy="error",
        )

        self.assertEqual(command[1], str(RUNNER.ACCOUNT_RUNNER))
        self.assertIn("--profile", command)
        self.assertIn("--raw", command)
        self.assertIn("--level-mode", command)
        self.assertIn("sync", command)
        self.assertEqual(command[-5:], ["--plan", "plan.json", "--meta", "meta.json", "--dry-run"])


if __name__ == "__main__":
    unittest.main()
