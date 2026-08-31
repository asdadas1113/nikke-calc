from __future__ import annotations

import unittest
from datetime import date

from optimizer.cold_pool import UsageClass
from optimizer.meta_eligibility import (
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    SoloRaidPeriod,
    SoloRaidSchedule,
    classify_meta_epoch_usage,
    post_epoch_completed_raids,
)
from optimizer.meta_usage import EnikkSeasonUsageSnapshot


POLICY = LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01)


def schedule(*, complete: bool = True, through: int = 10) -> SoloRaidSchedule:
    periods = tuple(
        SoloRaidPeriod(
            raid=raid,
            start_on=date(2026, raid, 1),
            end_on=date(2026, raid, 7),
        )
        for raid in range(1, through + 1)
    )
    return SoloRaidSchedule(periods, complete, "fixture-schedule")


def snapshot(
    raid: int,
    appearances: int = 0,
    *,
    incomplete_rows: int = 0,
    mapped: bool = True,
) -> EnikkSeasonUsageSnapshot:
    players = 100
    return EnikkSeasonUsageSnapshot(
        raid=raid,
        boss=f"boss-{raid}",
        player_count=players,
        players_with_teams=players - incomplete_rows,
        incomplete_player_rows=incomplete_rows,
        player_appearances={"N": appearances} if appearances else {},
        mapped_characters=frozenset({"N"}) if mapped else frozenset(),
        unknown_external_names=(),
    )


class MetaEpochEligibilityTests(unittest.TestCase):
    def test_known_epoch_uses_only_eight_fully_post_epoch_completed_raids(self):
        epoch = MetaEpochEvidence(
            "N",
            MetaEpochKnowledge.KNOWN,
            date(2026, 2, 28),
            "fixture",
            "major change before S3",
        )
        snapshots = tuple(snapshot(raid, 1) for raid in range(1, 11))

        result = classify_meta_epoch_usage(
            "N",
            snapshots,
            epoch=epoch,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
        )

        self.assertEqual(result.classification, UsageClass.LOW)
        self.assertEqual(result.eligible_post_epoch_raids, tuple(range(3, 11)))
        self.assertEqual(result.inspected_raids, tuple(range(3, 11)))
        self.assertEqual(result.window.peak_usage, 0.01)

    def test_same_day_epoch_is_excluded_when_only_date_precision_is_known(self):
        epoch = MetaEpochEvidence(
            "N",
            MetaEpochKnowledge.KNOWN,
            date(2026, 3, 1),
            "fixture",
            "release/change same calendar day as S3 start",
        )

        eligible = post_epoch_completed_raids(
            epoch,
            schedule(),
            completed_through=date(2026, 10, 7),
        )
        self.assertEqual(eligible, tuple(range(4, 11)))

        result = classify_meta_epoch_usage(
            "N",
            tuple(snapshot(raid, 0) for raid in range(1, 11)),
            epoch=epoch,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
        )
        self.assertEqual(result.classification, UsageClass.INSUFFICIENT)
        self.assertEqual(result.reason, "insufficient-completed-post-epoch-raids")
        self.assertEqual(result.eligible_post_epoch_raids, tuple(range(4, 11)))

    def test_change_after_raid_start_excludes_that_raid_and_fails_open_when_short(self):
        epoch = MetaEpochEvidence(
            "N",
            MetaEpochKnowledge.KNOWN,
            date(2026, 3, 2),
            "fixture",
            "change after S3 start",
        )

        eligible = post_epoch_completed_raids(
            epoch,
            schedule(),
            completed_through=date(2026, 10, 7),
        )
        self.assertEqual(eligible, tuple(range(4, 11)))

        result = classify_meta_epoch_usage(
            "N",
            tuple(snapshot(raid, 0) for raid in range(1, 11)),
            epoch=epoch,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
        )
        self.assertEqual(result.classification, UsageClass.INSUFFICIENT)
        self.assertEqual(result.reason, "insufficient-completed-post-epoch-raids")
        self.assertEqual(result.inspected_raids, ())

    def test_old_low_usage_before_latest_epoch_cannot_help_cold_classification(self):
        epoch = MetaEpochEvidence(
            "N",
            MetaEpochKnowledge.KNOWN,
            date(2026, 6, 1),
            "fixture",
            "favorite item reset",
        )
        snapshots = tuple(snapshot(raid, 0) for raid in range(1, 11))

        result = classify_meta_epoch_usage(
            "N",
            snapshots,
            epoch=epoch,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
        )

        self.assertEqual(result.classification, UsageClass.INSUFFICIENT)
        self.assertEqual(result.eligible_post_epoch_raids, (7, 8, 9, 10))

    def test_unknown_or_uncertain_epoch_fails_open(self):
        for knowledge in (MetaEpochKnowledge.UNKNOWN, MetaEpochKnowledge.UNCERTAIN):
            with self.subTest(knowledge=knowledge):
                epoch = MetaEpochEvidence("N", knowledge, None, "fixture")
                result = classify_meta_epoch_usage(
                    "N",
                    tuple(snapshot(raid) for raid in range(1, 11)),
                    epoch=epoch,
                    schedule=schedule(),
                    completed_through=date(2026, 10, 7),
                    policy=POLICY,
                )
                self.assertEqual(result.classification, UsageClass.INSUFFICIENT)
                self.assertIn("fail-open", result.reason)

    def test_incomplete_schedule_or_usage_snapshot_fails_open(self):
        epoch = MetaEpochEvidence(
            "N",
            MetaEpochKnowledge.KNOWN,
            date(2026, 2, 28),
            "fixture",
        )
        complete_snapshots = tuple(snapshot(raid) for raid in range(1, 11))

        schedule_result = classify_meta_epoch_usage(
            "N",
            complete_snapshots,
            epoch=epoch,
            schedule=schedule(complete=False),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
        )
        self.assertEqual(schedule_result.classification, UsageClass.INSUFFICIENT)
        self.assertEqual(schedule_result.reason, "raid-schedule-incomplete-fail-open")

        unsafe = tuple(
            snapshot(raid, incomplete_rows=1 if raid == 5 else 0)
            for raid in range(1, 11)
        )
        usage_result = classify_meta_epoch_usage(
            "N",
            unsafe,
            epoch=epoch,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
        )
        self.assertEqual(usage_result.classification, UsageClass.INSUFFICIENT)
        self.assertEqual(usage_result.reason, "usage-window-incomplete-fail-open")

    def test_any_post_epoch_peak_above_boundary_is_used_not_low(self):
        epoch = MetaEpochEvidence(
            "N",
            MetaEpochKnowledge.KNOWN,
            date(2026, 2, 28),
            "fixture",
        )
        snapshots = tuple(
            snapshot(raid, 5 if raid == 7 else 0)
            for raid in range(1, 11)
        )

        result = classify_meta_epoch_usage(
            "N",
            snapshots,
            epoch=epoch,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
        )

        self.assertEqual(result.classification, UsageClass.USED)
        self.assertEqual(result.window.peak_usage, 0.05)

    def test_active_raid_is_not_counted_before_completion_cutoff(self):
        epoch = MetaEpochEvidence(
            "N",
            MetaEpochKnowledge.KNOWN,
            date(2026, 2, 28),
            "fixture",
        )
        periods = schedule().periods + (
            SoloRaidPeriod(11, date(2026, 11, 1), date(2026, 11, 7)),
        )
        full_schedule = SoloRaidSchedule(periods, True, "fixture-schedule")

        eligible = post_epoch_completed_raids(
            epoch,
            full_schedule,
            completed_through=date(2026, 11, 3),
        )
        self.assertEqual(eligible, tuple(range(3, 11)))

    def test_invalid_epoch_or_policy_does_not_invent_dates_or_thresholds(self):
        with self.assertRaises(ValueError):
            MetaEpochEvidence("N", MetaEpochKnowledge.KNOWN, None, "fixture")
        with self.assertRaises(ValueError):
            MetaEpochEvidence(
                "N",
                MetaEpochKnowledge.UNKNOWN,
                date(2026, 1, 1),
                "fixture",
            )
        with self.assertRaises(ValueError):
            LowUsagePolicy(completed_seasons=0)
        with self.assertRaises(ValueError):
            LowUsagePolicy(max_peak_usage=1.1)


if __name__ == "__main__":
    unittest.main()
