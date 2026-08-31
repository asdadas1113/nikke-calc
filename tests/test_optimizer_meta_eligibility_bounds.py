from __future__ import annotations

import unittest
from datetime import date, timedelta

from optimizer.cold_pool import UsageClass
from optimizer.meta_eligibility import (
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    SoloRaidPeriod,
    SoloRaidSchedule,
)
from optimizer.meta_eligibility_bounds import classify_meta_epoch_usage_bounded
from optimizer.meta_usage_bounds import (
    CertifiedEnikkSeasonUsageSnapshot,
    RankingCoverageContract,
)


CONTRACT = RankingCoverageContract(
    servers=("GLOBAL", "JP", "KR", "NA", "SEA", "TW-HK"),
    rank_start=1,
    rank_end=50,
    team_count=5,
    team_size=5,
    source="fixture:6x50",
)


def snapshot(raid: int, appearances: int, *, missing: int = 2):
    return CertifiedEnikkSeasonUsageSnapshot(
        raid=raid,
        boss="fixture",
        contract=CONTRACT,
        observed_complete_player_slots=300 - missing,
        missing_player_slots=missing,
        malformed_player_slots=0,
        mapping_uncertain_player_slots=0,
        player_appearances={"A": appearances} if appearances else {},
        mapped_characters=frozenset({"A"}),
        unknown_external_names=(),
    )


def schedule():
    start = date(2026, 1, 10)
    periods = []
    for offset, raid in enumerate(range(33, 41)):
        raid_start = start + timedelta(days=offset * 10)
        periods.append(SoloRaidPeriod(raid, raid_start, raid_start + timedelta(days=2)))
    return SoloRaidSchedule(tuple(periods), complete=True, source="fixture")


def epoch():
    return MetaEpochEvidence(
        "A",
        MetaEpochKnowledge.KNOWN,
        date(2026, 1, 1),
        "fixture",
    )


class BoundedMetaEligibilityTests(unittest.TestCase):
    def classify(self, appearances: int, *, missing: int = 2):
        snapshots = tuple(
            snapshot(raid, appearances, missing=missing)
            for raid in range(33, 41)
        )
        return classify_meta_epoch_usage_bounded(
            "A",
            snapshots,
            epoch=epoch(),
            schedule=schedule(),
            completed_through=date(2026, 4, 1),
            policy=LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01),
        )

    def test_zero_observed_with_two_missing_of_300_is_still_safely_low(self):
        result = self.classify(0)
        self.assertEqual(result.classification, UsageClass.LOW)
        self.assertEqual(result.window.peak_usage, 2 / 300)
        self.assertAlmostEqual(result.boundary_distance or 0.0, 0.01 - 2 / 300)

    def test_one_observed_plus_two_missing_hits_one_percent_boundary_and_is_low(self):
        result = self.classify(1)
        self.assertEqual(result.classification, UsageClass.LOW)
        self.assertEqual(result.window.peak_usage, 3 / 300)
        self.assertEqual(result.boundary_distance, 0.0)

    def test_two_observed_plus_two_missing_crosses_boundary_and_is_insufficient(self):
        result = self.classify(2)
        self.assertEqual(result.classification, UsageClass.INSUFFICIENT)
        self.assertEqual(result.reason, "usage-bound-crosses-peak-boundary-fail-open")
        self.assertEqual(result.window.peak_usage, 4 / 300)

    def test_observed_lower_bound_above_boundary_is_used(self):
        result = self.classify(4)
        self.assertEqual(result.classification, UsageClass.USED)
        self.assertEqual(result.reason, "post-epoch-lower-bound-exceeds-peak-boundary")

    def test_complete_300_rows_has_exact_zero_bound(self):
        result = self.classify(0, missing=0)
        self.assertEqual(result.classification, UsageClass.LOW)
        self.assertEqual(result.window.peak_usage, 0.0)

    def test_unknown_epoch_still_fails_open_before_usage_bounds(self):
        result = classify_meta_epoch_usage_bounded(
            "A",
            tuple(snapshot(raid, 0) for raid in range(33, 41)),
            epoch=MetaEpochEvidence(
                "A",
                MetaEpochKnowledge.UNKNOWN,
                None,
                "fixture",
            ),
            schedule=schedule(),
            completed_through=date(2026, 4, 1),
            policy=LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01),
        )
        self.assertEqual(result.classification, UsageClass.INSUFFICIENT)


if __name__ == "__main__":
    unittest.main()
