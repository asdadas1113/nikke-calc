from __future__ import annotations

import unittest

from optimizer.meta_bounds_input import parse_bounded_meta_evidence
from optimizer.meta_eligibility import MetaEpochKnowledge
from optimizer.meta_usage_bounds import CertifiedEnikkSeasonUsageSnapshot


def payload():
    return {
        "completed_through": "2026-08-31",
        "policy": {"completed_seasons": 1, "max_peak_usage": 0.01},
        "schedule": {
            "periods": [
                {"raid": 40, "start_on": "2026-08-01", "end_on": "2026-08-03"}
            ],
            "complete": True,
            "source": "fixture-schedule",
        },
        "coverage_contract": {
            "servers": ["GLOBAL"],
            "rank_start": 1,
            "rank_end": 4,
            "team_count": 5,
            "team_size": 5,
            "source": "fixture-contract",
        },
        "epochs": {
            "A": {
                "knowledge": "known",
                "valid_from": "2026-01-01",
                "source": "fixture-epoch",
            }
        },
        "snapshots": [
            {
                "raid": 40,
                "boss": "fixture",
                "observed_complete_player_slots": 4,
                "missing_player_slots": 0,
                "malformed_player_slots": 0,
                "mapping_uncertain_player_slots": 0,
                "ambiguous_player_slots": {"A": 2},
                "player_appearances": {},
                "mapped_characters": ["A", "B"],
                "unknown_external_names": ["Rei"],
            }
        ],
        "restoration_batch_size": 1,
        "cold_exploration_limit": 1,
        "protected_names": [],
    }


class BoundedMetaInputTests(unittest.TestCase):
    def test_parses_certified_snapshot_and_localized_ambiguity(self):
        parsed = parse_bounded_meta_evidence(payload(), roster=("A", "B"))

        self.assertEqual(len(parsed.snapshots), 1)
        snapshot = parsed.snapshots[0]
        self.assertIsInstance(snapshot, CertifiedEnikkSeasonUsageSnapshot)
        self.assertEqual(snapshot.expected_player_slots, 4)
        self.assertEqual(snapshot.observe("A").upper_fraction, 0.5)
        self.assertEqual(snapshot.observe("B").upper_fraction, 0.0)
        self.assertEqual(parsed.epochs["A"].knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(parsed.epochs["B"].knowledge, MetaEpochKnowledge.UNKNOWN)

    def test_every_uncertainty_field_is_mandatory(self):
        for key in (
            "observed_complete_player_slots",
            "missing_player_slots",
            "malformed_player_slots",
            "mapping_uncertain_player_slots",
            "ambiguous_player_slots",
        ):
            with self.subTest(key=key):
                row = payload()
                del row["snapshots"][0][key]
                with self.assertRaisesRegex(ValueError, key):
                    parse_bounded_meta_evidence(row, roster=("A", "B"))

    def test_coverage_contract_is_mandatory_even_without_snapshots(self):
        row = payload()
        row["snapshots"] = []
        del row["coverage_contract"]
        with self.assertRaisesRegex(ValueError, "coverage_contract"):
            parse_bounded_meta_evidence(row, roster=("A", "B"))

    def test_contract_coverage_mismatch_fails(self):
        row = payload()
        row["snapshots"][0]["observed_complete_player_slots"] = 3
        with self.assertRaisesRegex(ValueError, "expected_player_slots"):
            parse_bounded_meta_evidence(row, roster=("A", "B"))

    def test_explicit_epochs_and_registry_mode_cannot_mix(self):
        row = payload()
        row["change_events"] = []
        with self.assertRaisesRegex(ValueError, "either explicit epochs"):
            parse_bounded_meta_evidence(row, roster=("A", "B"))

    def test_no_epoch_input_fails_open_to_unknown(self):
        row = payload()
        del row["epochs"]
        parsed = parse_bounded_meta_evidence(row, roster=("A", "B"))
        self.assertEqual(
            {evidence.knowledge for evidence in parsed.epochs.values()},
            {MetaEpochKnowledge.UNKNOWN},
        )

    def test_registry_mode_resolves_change_event(self):
        row = payload()
        del row["epochs"]
        row["change_events"] = [
            {
                "character": "A",
                "effective_on": "2026-05-01",
                "effect": "reset",
                "kind": "favorite-item",
                "source": "fixture-change",
            }
        ]
        parsed = parse_bounded_meta_evidence(row, roster=("A", "B"))
        self.assertEqual(parsed.epochs["A"].knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(parsed.epochs["A"].valid_from.isoformat(), "2026-05-01")
        self.assertEqual(parsed.epochs["B"].knowledge, MetaEpochKnowledge.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
