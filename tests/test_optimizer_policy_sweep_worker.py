from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from optimizer.automatic_search import AutomaticPlacementMode


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tests" / "benchmark_optimizer_policy_sweep_worker.py"
SPEC = importlib.util.spec_from_file_location("benchmark_optimizer_policy_sweep_worker", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def variant(**overrides):
    row = {
        "single_team_beam_width": 8,
        "single_team_global_limit": 10,
        "single_team_per_core_limit": 2,
        "allocation_team_beam_width": 8,
        "allocation_team_options_per_state": 3,
        "allocation_beam_width": 6,
        "allocation_limit": 2,
        "placement_mode": "canonical-only",
    }
    row.update(overrides)
    return row


class WorkerPolicySweepRunnerTests(unittest.TestCase):
    def test_parses_multiple_explicit_variants(self):
        policies = RUNNER.parse_policy_variants(
            {
                "policy_variants": {
                    "narrow": variant(single_team_beam_width=4),
                    "wide": variant(single_team_beam_width=12),
                }
            },
            team_size=5,
        )
        self.assertEqual(tuple(policies), ("narrow", "wide"))
        self.assertEqual(policies["narrow"].single_team_beam_width, 4)
        self.assertEqual(policies["wide"].single_team_beam_width, 12)
        self.assertEqual(policies["narrow"].team_size, 5)
        self.assertEqual(
            policies["narrow"].placement_mode,
            AutomaticPlacementMode.CANONICAL_ONLY,
        )

    def test_structural_diverse_mode_is_explicitly_selectable(self):
        policies = RUNNER.parse_policy_variants(
            {
                "policy_variants": {
                    "canonical": variant(),
                    "diverse": variant(placement_mode="structural-diverse"),
                }
            },
            team_size=5,
        )
        self.assertEqual(
            policies["diverse"].placement_mode,
            AutomaticPlacementMode.STRUCTURAL_DIVERSE,
        )

    def test_requires_at_least_two_variants(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            RUNNER.parse_policy_variants(
                {"policy_variants": {"only": variant()}},
                team_size=5,
            )

    def test_missing_width_is_not_defaulted(self):
        row = variant()
        del row["allocation_beam_width"]
        with self.assertRaisesRegex(ValueError, "missing explicit fields"):
            RUNNER.parse_policy_variants(
                {"policy_variants": {"a": row, "b": variant()}},
                team_size=5,
            )

    def test_invalid_placement_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "canonical-only or all-permutations"):
            RUNNER.parse_policy_variants(
                {
                    "policy_variants": {
                        "a": variant(placement_mode="guess"),
                        "b": variant(),
                    }
                },
                team_size=5,
            )


if __name__ == "__main__":
    unittest.main()
