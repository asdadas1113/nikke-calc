from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from optimizer import AutomaticPlacementMode


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tests" / "benchmark_optimizer_same_budget_auto_worker.py"
SPEC = importlib.util.spec_from_file_location("benchmark_optimizer_same_budget_auto_worker", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


class SameBudgetAutoWorkerRunnerTests(unittest.TestCase):
    def test_policy_parser_requires_every_width_and_preserves_placement_mode(self):
        search = {
            "automatic_discovery": {
                "single_team_beam_width": 20,
                "single_team_global_limit": 30,
                "single_team_per_core_limit": 4,
                "allocation_team_beam_width": 12,
                "allocation_team_options_per_state": 6,
                "allocation_beam_width": 10,
                "allocation_limit": 3,
                "placement_mode": "all-permutations",
            }
        }
        policy = RUNNER.parse_discovery_policy(search, team_size=5)
        self.assertEqual(policy.team_size, 5)
        self.assertEqual(policy.single_team_beam_width, 20)
        self.assertEqual(policy.allocation_limit, 3)
        self.assertEqual(policy.placement_mode, AutomaticPlacementMode.ALL_PERMUTATIONS)

    def test_missing_width_fails_instead_of_using_a_hidden_default(self):
        search = {
            "automatic_discovery": {
                "single_team_beam_width": 20,
                "placement_mode": "canonical-only",
            }
        }
        with self.assertRaisesRegex(ValueError, "missing explicit fields"):
            RUNNER.parse_discovery_policy(search, team_size=5)

    def test_placement_mode_is_explicit(self):
        row = {
            "single_team_beam_width": 20,
            "single_team_global_limit": 30,
            "single_team_per_core_limit": 4,
            "allocation_team_beam_width": 12,
            "allocation_team_options_per_state": 6,
            "allocation_beam_width": 10,
            "allocation_limit": 3,
        }
        with self.assertRaisesRegex(ValueError, "placement_mode"):
            RUNNER.parse_discovery_policy({"automatic_discovery": row}, team_size=5)


if __name__ == "__main__":
    unittest.main()
