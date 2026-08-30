from __future__ import annotations

import unittest
from datetime import date

from optimizer.meta_eligibility import MetaEpochKnowledge
from optimizer.meta_epoch_registry import (
    MetaChangeEffect,
    MetaChangeEvent,
    derive_meta_epoch_evidence,
    parse_meta_change_events,
)


class MetaEpochRegistryTests(unittest.TestCase):
    def test_latest_confirmed_reset_wins_release_and_later_favorite_item(self):
        events = (
            MetaChangeEvent("A", date(2024, 1, 1), MetaChangeEffect.RESET, "release", "release-source"),
            MetaChangeEvent("A", date(2026, 5, 1), MetaChangeEffect.RESET, "favorite-item", "favorite-source"),
        )
        epoch = derive_meta_epoch_evidence(("A",), events, through=date(2026, 8, 31))["A"]
        self.assertEqual(epoch.knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(epoch.valid_from, date(2026, 5, 1))
        self.assertEqual(epoch.source, "favorite-source")

    def test_uncertain_change_after_reset_forces_fail_open_epoch(self):
        events = (
            MetaChangeEvent("A", date(2024, 1, 1), MetaChangeEffect.RESET, "release", "release-source"),
            MetaChangeEvent("A", date(2026, 6, 1), MetaChangeEffect.UNCERTAIN, "rebalance", "patch-source"),
        )
        epoch = derive_meta_epoch_evidence(("A",), events, through=date(2026, 8, 31))["A"]
        self.assertEqual(epoch.knowledge, MetaEpochKnowledge.UNCERTAIN)
        self.assertIsNone(epoch.valid_from)
        self.assertIn("rebalance", epoch.reason)

    def test_later_confirmed_reset_makes_earlier_uncertainty_irrelevant(self):
        events = (
            MetaChangeEvent("A", date(2026, 1, 1), MetaChangeEffect.UNCERTAIN, "old-fix", "old-source"),
            MetaChangeEvent("A", date(2026, 7, 1), MetaChangeEffect.RESET, "favorite-item", "new-source"),
        )
        epoch = derive_meta_epoch_evidence(("A",), events, through=date(2026, 8, 31))["A"]
        self.assertEqual(epoch.knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(epoch.valid_from, date(2026, 7, 1))

    def test_confirmed_no_reset_after_epoch_does_not_invalidate_history(self):
        events = (
            MetaChangeEvent("A", date(2025, 1, 1), MetaChangeEffect.RESET, "release", "release-source"),
            MetaChangeEvent("A", date(2026, 7, 1), MetaChangeEffect.NO_RESET, "text-fix", "patch-source"),
        )
        epoch = derive_meta_epoch_evidence(("A",), events, through=date(2026, 8, 31))["A"]
        self.assertEqual(epoch.knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(epoch.valid_from, date(2025, 1, 1))

    def test_no_event_is_unknown_not_release_inference(self):
        epoch = derive_meta_epoch_evidence(("A",), (), through=date(2026, 8, 31))["A"]
        self.assertEqual(epoch.knowledge, MetaEpochKnowledge.UNKNOWN)
        self.assertIsNone(epoch.valid_from)

    def test_future_change_does_not_affect_current_epoch(self):
        events = (
            MetaChangeEvent("A", date(2025, 1, 1), MetaChangeEffect.RESET, "release", "release-source"),
            MetaChangeEvent("A", date(2026, 9, 1), MetaChangeEffect.UNCERTAIN, "future", "future-source"),
        )
        epoch = derive_meta_epoch_evidence(("A",), events, through=date(2026, 8, 31))["A"]
        self.assertEqual(epoch.knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(epoch.valid_from, date(2025, 1, 1))

    def test_parser_requires_explicit_effect_and_source(self):
        parsed = parse_meta_change_events(
            (
                {
                    "character": "A",
                    "effective_on": "2026-05-01",
                    "effect": "reset",
                    "kind": "favorite-item",
                    "source": "source-url-or-id",
                },
            )
        )
        self.assertEqual(parsed[0].effect, MetaChangeEffect.RESET)
        with self.assertRaisesRegex(ValueError, "missing fields"):
            parse_meta_change_events(
                ({"character": "A", "effective_on": "2026-05-01"},)
            )


if __name__ == "__main__":
    unittest.main()
