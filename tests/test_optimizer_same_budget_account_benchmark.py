from __future__ import annotations

import importlib.util
import pathlib
import unittest

from optimizer import MetaEpochKnowledge


SCRIPT = pathlib.Path(__file__).with_name("benchmark_optimizer_same_budget_account.py")
spec = importlib.util.spec_from_file_location("benchmark_optimizer_same_budget_account", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class SameBudgetAccountBenchmarkInputTests(unittest.TestCase):
    def test_meta_parser_preserves_explicit_epoch_schedule_and_policy(self):
        payload = {
            "completed_through": "2026-08-31",
            "policy": {"completed_seasons": 8, "max_peak_usage": 0.01},
            "restoration_batch_size": 1,
            "cold_exploration_limit": 2,
            "protected_names": ["Priority"],
            "schedule": {
                "complete": True,
                "source": "fixture",
                "periods": [
                    {"raid": 39, "start_on": "2026-07-16", "end_on": "2026-07-23"},
                    {"raid": 40, "start_on": "2026-08-20", "end_on": "2026-08-27"},
                ],
            },
            "epochs": {
                "Old": {
                    "knowledge": "known",
                    "valid_from": "2026-01-01",
                    "source": "fixture:major-change",
                },
                "New": {
                    "knowledge": "unknown",
                    "source": "fixture:missing",
                },
            },
            "snapshots": [
                {
                    "raid": 39,
                    "boss": "BossA",
                    "player_count": 300,
                    "players_with_teams": 300,
                    "incomplete_player_rows": 0,
                    "player_appearances": {"Old": 1},
                    "mapped_characters": ["Old", "New", "Priority"],
                    "unknown_external_names": [],
                }
            ],
        }

        parsed = module.parse_meta_evidence(payload)

        self.assertEqual(parsed["policy"].completed_seasons, 8)
        self.assertEqual(parsed["policy"].max_peak_usage, 0.01)
        self.assertEqual(parsed["schedule"].source, "fixture")
        self.assertEqual(parsed["schedule"].periods[0].raid, 39)
        self.assertEqual(parsed["epochs"]["Old"].knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(parsed["epochs"]["New"].knowledge, MetaEpochKnowledge.UNKNOWN)
        self.assertIsNone(parsed["epochs"]["New"].valid_from)
        self.assertEqual(parsed["snapshots"][0].observe("Old").player_appearances, 1)
        self.assertEqual(parsed["protected_names"], ("Priority",))
        self.assertEqual(parsed["cold_exploration_limit"], 2)

    def test_seed_parser_keeps_pure_and_meta_policy_explicit(self):
        exact, cores = module.parse_seeds(
            {
                "exact": [
                    {"members": ["A", "B", "C", "D", "E"], "source": "ranker"}
                ],
                "core": [
                    {"members": ["A", "B"], "source": "mechanical-core"}
                ],
            },
            "mode",
        )
        self.assertEqual(exact[0].members, ("A", "B", "C", "D", "E"))
        self.assertEqual(exact[0].source, "ranker")
        self.assertEqual(cores[0].members, ("A", "B"))
        self.assertEqual(cores[0].source, "mechanical-core")

    def test_meta_filter_preserves_common_input_order(self):
        rows = (
            ("A", "B"),
            ("A", "Cold"),
            ("C", "D"),
            ("Cold", "D"),
        )
        self.assertEqual(
            module._filter_teams(rows, {"A", "B", "C", "D"}),
            (("A", "B"), ("C", "D")),
        )

    def test_uncertain_epoch_ignores_supplied_valid_from(self):
        payload = {
            "completed_through": "2026-08-31",
            "policy": {"completed_seasons": 8, "max_peak_usage": 0.01},
            "restoration_batch_size": 1,
            "cold_exploration_limit": 0,
            "schedule": {"complete": True, "source": "fixture", "periods": []},
            "epochs": {
                "A": {
                    "knowledge": "uncertain",
                    "valid_from": "2026-01-01",
                    "source": "fixture",
                }
            },
            "snapshots": [],
        }
        parsed = module.parse_meta_evidence(payload)
        self.assertEqual(parsed["epochs"]["A"].knowledge, MetaEpochKnowledge.UNCERTAIN)
        self.assertIsNone(parsed["epochs"]["A"].valid_from)


if __name__ == "__main__":
    unittest.main()
