from __future__ import annotations

import unittest
from datetime import date

from optimizer.meta_eligibility import MetaEpochKnowledge
from optimizer.meta_epoch_registry import MetaChangeEffect, MetaChangeEvent
from optimizer.meta_release import (
    FirstAvailabilityEvidence,
    FirstAvailabilityKnowledge,
    derive_meta_epochs_from_availability_and_changes,
    parse_first_availability_evidence,
    release_reset_events,
)


class MetaReleaseTests(unittest.TestCase):
    def test_known_first_availability_becomes_reset(self):
        release = FirstAvailabilityEvidence(
            "A",
            FirstAvailabilityKnowledge.KNOWN,
            date(2026, 7, 2),
            "special-recruit",
            "official:patch-note",
        )
        event = release_reset_events((release,))[0]
        self.assertEqual(event.effect, MetaChangeEffect.RESET)
        self.assertEqual(event.effective_on, date(2026, 7, 2))
        self.assertEqual(event.kind, "first-availability:special-recruit")

    def test_unknown_release_has_no_date_and_emits_no_event(self):
        release = FirstAvailabilityEvidence(
            "A",
            FirstAvailabilityKnowledge.UNKNOWN,
            None,
            "unknown",
            "registry:missing",
        )
        self.assertEqual(release_reset_events((release,)), ())
        epoch = derive_meta_epochs_from_availability_and_changes(
            ("A",),
            (release,),
            (),
            through=date(2026, 8, 31),
        )["A"]
        self.assertEqual(epoch.knowledge, MetaEpochKnowledge.UNKNOWN)
        self.assertIsNone(epoch.valid_from)

    def test_unknown_release_can_be_superseded_by_later_confirmed_reset(self):
        release = FirstAvailabilityEvidence(
            "A",
            FirstAvailabilityKnowledge.UNKNOWN,
            None,
            "unknown",
            "registry:missing",
        )
        favorite = MetaChangeEvent(
            "A",
            date(2026, 5, 1),
            MetaChangeEffect.RESET,
            "favorite-item-skill-replacement",
            "official:favorite-item-note",
        )
        epoch = derive_meta_epochs_from_availability_and_changes(
            ("A",),
            (release,),
            (favorite,),
            through=date(2026, 8, 31),
        )["A"]
        self.assertEqual(epoch.knowledge, MetaEpochKnowledge.KNOWN)
        self.assertEqual(epoch.valid_from, date(2026, 5, 1))

    def test_later_uncertain_change_invalidates_known_release_epoch(self):
        release = FirstAvailabilityEvidence(
            "A",
            FirstAvailabilityKnowledge.KNOWN,
            date(2025, 1, 1),
            "special-recruit",
            "official:release",
        )
        uncertain = MetaChangeEvent(
            "A",
            date(2026, 3, 1),
            MetaChangeEffect.UNCERTAIN,
            "balance-adjustment",
            "official:patch-note",
        )
        epoch = derive_meta_epochs_from_availability_and_changes(
            ("A",),
            (release,),
            (uncertain,),
            through=date(2026, 8, 31),
        )["A"]
        self.assertEqual(epoch.knowledge, MetaEpochKnowledge.UNCERTAIN)
        self.assertIsNone(epoch.valid_from)

    def test_parser_rejects_unknown_row_with_invented_date(self):
        with self.assertRaisesRegex(ValueError, "must not contain a date"):
            parse_first_availability_evidence(
                (
                    {
                        "character": "A",
                        "knowledge": "unknown",
                        "available_from": "2026-01-01",
                        "mechanism": "unknown",
                        "source": "manual",
                    },
                )
            )

    def test_parser_requires_exact_date_for_known_row(self):
        with self.assertRaisesRegex(ValueError, "requires available_from"):
            parse_first_availability_evidence(
                (
                    {
                        "character": "A",
                        "knowledge": "known",
                        "mechanism": "special-recruit",
                        "source": "official",
                    },
                )
            )

    def test_release_evidence_outside_roster_is_rejected(self):
        release = FirstAvailabilityEvidence(
            "B",
            FirstAvailabilityKnowledge.KNOWN,
            date(2026, 1, 1),
            "special-recruit",
            "official",
        )
        with self.assertRaisesRegex(ValueError, "outside roster"):
            derive_meta_epochs_from_availability_and_changes(
                ("A",),
                (release,),
                (),
                through=date(2026, 8, 31),
            )


if __name__ == "__main__":
    unittest.main()
