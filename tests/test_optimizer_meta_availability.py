from __future__ import annotations

import unittest
from datetime import date

from optimizer.cold_pool import UsageClass
from optimizer.meta_availability import (
    AvailabilityKnowledge,
    FirstPositiveAvailability,
    derive_first_positive_availability,
    derive_roster_first_positive_availability,
)
from optimizer.meta_eligibility import LowUsagePolicy, SoloRaidPeriod, SoloRaidSchedule
from optimizer.meta_policy import classify_roster_meta_usage
from optimizer.meta_usage import EnikkSeasonUsageSnapshot


def schedule(*, complete: bool = True, raids: tuple[int, ...] = (37, 38, 39, 40)) -> SoloRaidSchedule:
    periods = []
    for index, raid in enumerate(raids):
        month = 4 + index
        periods.append(
            SoloRaidPeriod(
                raid=raid,
                start_on=date(2026, month, 1),
                end_on=date(2026, month, 7),
            )
        )
    return SoloRaidSchedule(tuple(periods), complete, "fixture-schedule")


def snapshot(
    raid: int,
    *,
    appearances: int = 0,
    mapped: bool = True,
    incomplete_rows: int = 0,
) -> EnikkSeasonUsageSnapshot:
    player_count = 100
    return EnikkSeasonUsageSnapshot(
        raid=raid,
        boss=f"boss-{raid}",
        player_count=player_count,
        players_with_teams=player_count - incomplete_rows,
        incomplete_player_rows=incomplete_rows,
        player_appearances={"N": appearances} if appearances else {},
        mapped_characters=frozenset({"N"}) if mapped else frozenset(),
        unknown_external_names=(),
    )


class FirstPositiveAvailabilityTests(unittest.TestCase):
    def test_first_positive_excludes_observed_raid_and_starts_after_raid_end(self):
        result = derive_first_positive_availability(
            "N",
            (
                snapshot(37),
                snapshot(38, appearances=0),
                snapshot(39, appearances=3),
                snapshot(40, appearances=2),
            ),
            schedule(),
        )

        self.assertEqual(result.knowledge, AvailabilityKnowledge.KNOWN)
        self.assertEqual(result.first_positive_raid, 39)
        self.assertEqual(result.valid_from, date(2026, 6, 8))
        self.assertIn("S39", result.reason)

    def test_positive_usage_remains_evidence_with_incomplete_player_rows(self):
        result = derive_first_positive_availability(
            "N",
            (snapshot(39, appearances=1, incomplete_rows=25),),
            schedule(raids=(39,)),
        )

        self.assertEqual(result.knowledge, AvailabilityKnowledge.KNOWN)
        self.assertEqual(result.first_positive_raid, 39)

    def test_unmapped_positive_does_not_become_availability_evidence(self):
        result = derive_first_positive_availability(
            "N",
            (snapshot(39, appearances=3, mapped=False),),
            schedule(raids=(39,)),
        )

        self.assertEqual(result.knowledge, AvailabilityKnowledge.UNKNOWN)
        self.assertIsNone(result.first_positive_raid)
        self.assertIsNone(result.valid_from)

    def test_incomplete_schedule_or_missing_positive_raid_is_uncertain(self):
        incomplete = derive_first_positive_availability(
            "N",
            (snapshot(39, appearances=1),),
            schedule(complete=False, raids=(39,)),
        )
        self.assertEqual(incomplete.knowledge, AvailabilityKnowledge.UNCERTAIN)

        missing_period = derive_first_positive_availability(
            "N",
            (snapshot(39, appearances=1),),
            schedule(raids=(38, 40)),
        )
        self.assertEqual(missing_period.knowledge, AvailabilityKnowledge.UNCERTAIN)
        self.assertIn("S39", missing_period.reason)

    def test_no_positive_observation_is_unknown_not_zero_release_evidence(self):
        result = derive_first_positive_availability(
            "N",
            (snapshot(37), snapshot(38), snapshot(39)),
            schedule(raids=(37, 38, 39)),
        )

        self.assertEqual(result.knowledge, AvailabilityKnowledge.UNKNOWN)
        self.assertIsNone(result.valid_from)

    def test_roster_derivation_is_per_character_and_rejects_duplicates(self):
        rows = (
            EnikkSeasonUsageSnapshot(
                raid=39,
                boss="boss",
                player_count=100,
                players_with_teams=100,
                incomplete_player_rows=0,
                player_appearances={"A": 1},
                mapped_characters=frozenset({"A", "B"}),
                unknown_external_names=(),
            ),
        )
        result = derive_roster_first_positive_availability(
            ("A", "B"),
            rows,
            schedule(raids=(39,)),
        )
        self.assertEqual(result["A"].knowledge, AvailabilityKnowledge.KNOWN)
        self.assertEqual(result["B"].knowledge, AvailabilityKnowledge.UNKNOWN)

        with self.assertRaises(ValueError):
            derive_roster_first_positive_availability(
                ("A", "A"),
                rows,
                schedule(raids=(39,)),
            )

    def test_known_first_positive_does_not_substitute_for_missing_meta_epoch(self):
        rows = tuple(
            snapshot(raid, appearances=1 if raid == 37 else 0)
            for raid in (37, 38, 39, 40)
        )
        availability = derive_first_positive_availability("N", rows, schedule())
        self.assertEqual(availability.knowledge, AvailabilityKnowledge.KNOWN)

        classified = classify_roster_meta_usage(
            ("N",),
            rows,
            {},
            schedule=schedule(),
            completed_through=date(2026, 7, 7),
            policy=LowUsagePolicy(completed_seasons=2, max_peak_usage=0.01),
        )
        self.assertEqual(classified.decisions[0].classification, UsageClass.INSUFFICIENT)
        self.assertEqual(classified.decisions[0].reason, "meta-epoch-unknown-fail-open")

    def test_dataclass_does_not_allow_invented_known_or_unknown_dates(self):
        with self.assertRaises(ValueError):
            FirstPositiveAvailability(
                "N",
                AvailabilityKnowledge.KNOWN,
                None,
                None,
                "fixture",
                "invalid",
            )
        with self.assertRaises(ValueError):
            FirstPositiveAvailability(
                "N",
                AvailabilityKnowledge.UNKNOWN,
                39,
                date(2026, 6, 8),
                "fixture",
                "invalid",
            )


if __name__ == "__main__":
    unittest.main()
