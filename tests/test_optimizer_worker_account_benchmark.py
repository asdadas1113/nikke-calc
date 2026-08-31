from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tests" / "benchmark_optimizer_worker_account.py"
SPEC = importlib.util.spec_from_file_location("benchmark_optimizer_worker_account", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


class WorkerAccountBenchmarkTests(unittest.TestCase):
    def test_skill_investment_is_aggregate_context_not_strength_score(self):
        profile = {
            "chars": {
                "A": {"skill_levels": {"1": 10, "2": 10, "3": 10}},
                "B": {"skill_levels": {"1": 7, "2": 8, "3": 9}},
                "C": {"skill_levels": {"1": 4, "2": 4, "3": 4}},
                "D": {"skill_levels": {"1": 1, "2": 1, "3": 1}},
            }
        }
        result = RUNNER.summarize_skill_investment(profile)

        self.assertEqual(result["all_three_at_least_4"], 3)
        self.assertEqual(result["all_three_at_least_7"], 2)
        self.assertEqual(result["all_three_at_10"], 1)
        self.assertEqual(result["skill_level_sum_distribution"], {"3": 1, "12": 1, "24": 1, "30": 1})
        self.assertNotIn("score", result)
        self.assertNotIn("priority", result)

    def test_missing_normalized_skill_levels_fail_loudly(self):
        with self.assertRaisesRegex(ValueError, "normalized skill_levels"):
            RUNNER.summarize_skill_investment({"chars": {"A": {}}})


if __name__ == "__main__":
    unittest.main()
