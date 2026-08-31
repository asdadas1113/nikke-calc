from __future__ import annotations

import unittest
from datetime import date

from optimizer.meta_eligibility import MetaEpochEvidence, MetaEpochKnowledge
from optimizer.meta_epoch_input import resolve_meta_epoch_input


class MetaEpochInputTests(unittest.TestCase):
    def test_change_events_derive_full_roster_and_leave_missing_character_unknown(self):
        result = resolve_meta_epoch_input(
            ("A", "B"),
            through=date(2026, 8, 31),
            change_event_rows=(
                {
                    "character": "A",
                    "effective_on": "2026-05-01",
                    "effect": "reset",
                    "kind": "favorite-item",
                    "source": "patch-source",
                },
            ),
        )
        self.assertEqual(result["A"].knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(result["A"].valid_from, date(2026, 5, 1))
        self.assertEqual(result["B"].knowledge, MetaEpochKnowledge.UNKNOWN)

    def test_first_availability_and_change_events_share_registry_mode(self):
        result = resolve_meta_epoch_input(
            ("A", "B"),
            through=date(2026, 8, 31),
            first_availability_rows=(
                {
                    "character": "A",
                    "knowledge": "known",
                    "available_from": "2025-01-01",
                    "mechanism": "special-recruit",
                    "source": "official-release",
                },
                {
                    "character": "B",
                    "knowledge": "unknown",
                    "mechanism": "unknown",
                    "source": "registry-missing",
                },
            ),
            change_event_rows=(
                {
                    "character": "A",
                    "effective_on": "2026-05-01",
                    "effect": "reset",
                    "kind": "favorite-item",
                    "source": "official-favorite",
                },
            ),
        )
        self.assertEqual(result["A"].knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(result["A"].valid_from, date(2026, 5, 1))
        self.assertEqual(result["B"].knowledge, MetaEpochKnowledge.UNKNOWN)

    def test_first_availability_alone_establishes_release_epoch(self):
        result = resolve_meta_epoch_input(
            ("A",),
            through=date(2026, 8, 31),
            first_availability_rows=(
                {
                    "character": "A",
                    "knowledge": "known",
                    "available_from": "2026-07-02",
                    "mechanism": "special-recruit",
                    "source": "official-release",
                },
            ),
        )
        self.assertEqual(result["A"].knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(result["A"].valid_from, date(2026, 7, 2))

    def test_explicit_epochs_fill_missing_owned_rows_as_unknown(self):
        explicit = {
            "A": MetaEpochEvidence(
                "A",
                MetaEpochKnowledge.KNOWN,
                date(2025, 1, 1),
                "explicit-source",
            )
        }
        result = resolve_meta_epoch_input(
            ("A", "B"),
            through=date(2026, 8, 31),
            explicit_epochs=explicit,
        )
        self.assertEqual(result["A"], explicit["A"])
        self.assertEqual(result["B"].knowledge, MetaEpochKnowledge.UNKNOWN)

    def test_explicit_and_registry_modes_are_rejected_even_when_empty(self):
        with self.assertRaisesRegex(ValueError, "registry evidence"):
            resolve_meta_epoch_input(
                ("A",),
                through=date(2026, 8, 31),
                explicit_epochs={},
                change_event_rows=(),
            )
        with self.assertRaisesRegex(ValueError, "registry evidence"):
            resolve_meta_epoch_input(
                ("A",),
                through=date(2026, 8, 31),
                explicit_epochs={},
                first_availability_rows=(),
            )

    def test_no_mode_infers_nothing_from_roster_existence(self):
        result = resolve_meta_epoch_input(
            ("A",),
            through=date(2026, 8, 31),
        )
        self.assertEqual(result["A"].knowledge, MetaEpochKnowledge.UNKNOWN)
        self.assertIsNone(result["A"].valid_from)

    def test_explicit_epoch_for_unowned_character_is_rejected(self):
        explicit = {
            "X": MetaEpochEvidence(
                "X",
                MetaEpochKnowledge.KNOWN,
                date(2025, 1, 1),
                "source",
            )
        }
        with self.assertRaisesRegex(ValueError, "outside roster"):
            resolve_meta_epoch_input(
                ("A",),
                through=date(2026, 8, 31),
                explicit_epochs=explicit,
            )


if __name__ == "__main__":
    unittest.main()
