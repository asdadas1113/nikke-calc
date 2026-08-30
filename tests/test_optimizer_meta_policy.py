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
)
from optimizer.meta_policy import build_meta_guided_partition, classify_roster_meta_usage
from optimizer.meta_usage import EnikkSeasonUsageSnapshot
from optimizer.overload import OverloadKnowledge, OverloadPieceEvidence


ROSTER = ("low", "used", "missing-epoch", "invested")
POLICY = LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01)


def schedule() -> SoloRaidSchedule:
    return SoloRaidSchedule(
        tuple(
            SoloRaidPeriod(raid, date(2026, raid, 1), date(2026, raid, 7))
            for raid in range(1, 11)
        ),
        True,
        "fixture",
    )


def snapshots() -> tuple[EnikkSeasonUsageSnapshot, ...]:
    rows = []
    for raid in range(1, 11):
        appearances = {
            "low": 1,
            "used": 5 if raid == 7 else 0,
            "missing-epoch": 0,
            "invested": 1,
        }
        rows.append(
            EnikkSeasonUsageSnapshot(
                raid=raid,
                boss=f"boss-{raid}",
                player_count=100,
                players_with_teams=100,
                incomplete_player_rows=0,
                player_appearances={name: count for name, count in appearances.items() if count},
                mapped_characters=frozenset(ROSTER),
                unknown_external_names=(),
            )
        )
    return tuple(rows)


def epoch(name: str, month: int = 3) -> MetaEpochEvidence:
    return MetaEpochEvidence(
        name,
        MetaEpochKnowledge.KNOWN,
        date(2026, month, 1),
        "fixture",
    )


def ol(name: str, knowledge: OverloadKnowledge, count: int | None):
    return OverloadPieceEvidence(name, knowledge, count, "fixture")


class MetaPolicyTests(unittest.TestCase):
    def test_missing_epoch_fails_open_before_cold_partition(self):
        result = classify_roster_meta_usage(
            ROSTER,
            snapshots(),
            {
                "low": epoch("low"),
                "used": epoch("used"),
                "invested": epoch("invested"),
            },
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
        )

        by_name = {row.character: row for row in result.decisions}
        self.assertEqual(by_name["low"].classification, UsageClass.LOW)
        self.assertEqual(by_name["used"].classification, UsageClass.USED)
        self.assertEqual(by_name["missing-epoch"].classification, UsageClass.INSUFFICIENT)
        self.assertEqual(
            by_name["missing-epoch"].reason,
            "meta-epoch-unknown-fail-open",
        )

    def test_partition_requires_both_low_usage_and_proven_ol_zero(self):
        result = build_meta_guided_partition(
            ROSTER,
            snapshots(),
            {
                "low": epoch("low"),
                "used": epoch("used"),
                "invested": epoch("invested"),
            },
            {
                "low": ol("low", OverloadKnowledge.ZERO, 0),
                "used": ol("used", OverloadKnowledge.ZERO, 0),
                "missing-epoch": ol("missing-epoch", OverloadKnowledge.ZERO, 0),
                "invested": ol("invested", OverloadKnowledge.PRESENT, 2),
            },
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
        )

        self.assertEqual(result.partition.cold, ("low",))
        self.assertEqual(
            result.partition.primary,
            ("used", "missing-epoch", "invested"),
        )
        self.assertIn("missing-epoch", result.partition.fail_open)

    def test_priority_review_protection_bypasses_cold_without_reclassifying_usage(self):
        result = build_meta_guided_partition(
            ("low",),
            snapshots(),
            {"low": epoch("low")},
            {"low": ol("low", OverloadKnowledge.ZERO, 0)},
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
            protected_names=("low",),
        )

        self.assertEqual(result.usage.decisions[0].classification, UsageClass.LOW)
        self.assertEqual(result.partition.cold, ())
        self.assertEqual(result.partition.primary, ("low",))
        self.assertEqual(result.partition.protected, ("low",))

    def test_ten_season_conservative_policy_is_caller_owned(self):
        result = classify_roster_meta_usage(
            ("low",),
            snapshots(),
            {"low": epoch("low", month=1)},
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=LowUsagePolicy(completed_seasons=10, max_peak_usage=0.01),
        )

        self.assertEqual(result.decisions[0].classification, UsageClass.LOW)
        self.assertEqual(result.decisions[0].inspected_raids, tuple(range(1, 11)))


if __name__ == "__main__":
    unittest.main()
