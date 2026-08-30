from __future__ import annotations

import unittest

from optimizer import MetaEpochKnowledge
from tests.benchmark_optimizer_same_budget_account import (
    _filter_teams,
    parse_meta_evidence,
    parse_seeds,
)


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

        parsed = parse_meta_evidence(payload)

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
        exact, cores = parse_seeds(
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
            _filter_teams(rows, {"A", "B", "C", "D"}),
            (("A", "B"), ("C", "D")),
        )

    def test_unknown_epoch_cannot_supply_valid_from(self):
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
        parsed = parse_meta_evidence(payload)
        self.assertEqual(parsed["epochs"]["A"].knowledge, MetaEpochKnowledge.UNCERTAIN)
        self.assertIsNone(parsed["epochs"]["A"].valid_from)


if __name__ == "__main__":
    unittest.main()
