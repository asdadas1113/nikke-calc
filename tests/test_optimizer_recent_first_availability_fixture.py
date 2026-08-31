from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from optimizer.cold_pool import UsageClass
from optimizer.meta_eligibility import (
    LowUsagePolicy,
    SoloRaidPeriod,
    SoloRaidSchedule,
    classify_meta_epoch_usage,
    post_epoch_completed_raids,
)
from optimizer.meta_release import (
    derive_meta_epochs_from_availability_and_changes,
    parse_first_availability_evidence,
)
from optimizer.meta_usage import EnikkSeasonUsageSnapshot


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "optimizer_recent_first_availability_2026.json"
POLICY = LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01)


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def load_schedule(payload) -> SoloRaidSchedule:
    return SoloRaidSchedule(
        tuple(
            SoloRaidPeriod(
                raid=int(row["raid"]),
                start_on=date.fromisoformat(row["start_on"]),
                end_on=date.fromisoformat(row["end_on"]),
            )
            for row in payload["normal_solo_raid_periods"]
        ),
        True,
        "fixture:public-2026-normal-solo-raid-periods",
    )


def zero_usage_snapshots(roster, schedule):
    names = frozenset(roster)
    return tuple(
        EnikkSeasonUsageSnapshot(
            raid=period.raid,
            boss=f"fixture-S{period.raid}",
            player_count=100,
            players_with_teams=100,
            incomplete_player_rows=0,
            player_appearances={},
            mapped_characters=names,
            unknown_external_names=(),
        )
        for period in schedule.periods
    )


class RecentFirstAvailabilityFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = load_fixture()
        cls.releases = parse_first_availability_evidence(
            cls.payload["first_availability"]
        )
        cls.roster = tuple(row.character for row in cls.releases)
        cls.schedule = load_schedule(cls.payload)
        cls.epochs = derive_meta_epochs_from_availability_and_changes(
            cls.roster,
            cls.releases,
            (),
            through=date(2026, 8, 31),
            registry_source="fixture:recent-first-availability-2026",
        )

    def test_fixture_sources_are_explicit_and_rows_are_unique(self):
        self.assertEqual(len(self.roster), len(set(self.roster)))
        self.assertTrue(all(row.source.startswith("https://") for row in self.releases))
        self.assertEqual(tuple(period.raid for period in self.schedule.periods), (38, 39, 40))

    def test_recent_release_dates_map_to_only_fully_post_epoch_normal_raids(self):
        expected = {
            "네온 : 비전 아이": (38, 39, 40),
            "민트": (38, 39, 40),
            "아크레인저 블랙": (38, 39, 40),
            "신데렐라 : 크리스탈 웨이브": (39, 40),
            "마르차나 : 마린 스터디": (39, 40),
            "라플라스 : 얼티밋 히어로": (40,),
            "맥스웰 : 오디너리 미케닉": (40,),
            "퀸(마코토)": (40,),
            # 2026-08-20 release and S40 start share a calendar date. The
            # date-only model cannot prove ordering, so S40 must fail open.
            "유키코": (),
        }
        for name, raids in expected.items():
            with self.subTest(character=name):
                self.assertEqual(
                    post_epoch_completed_raids(
                        self.epochs[name],
                        self.schedule,
                        completed_through=date(2026, 8, 31),
                    ),
                    raids,
                )

    def test_even_perfect_apparent_zero_usage_cannot_make_recent_units_low(self):
        snapshots = zero_usage_snapshots(self.roster, self.schedule)
        for name in self.roster:
            with self.subTest(character=name):
                decision = classify_meta_epoch_usage(
                    name,
                    snapshots,
                    epoch=self.epochs[name],
                    schedule=self.schedule,
                    completed_through=date(2026, 8, 31),
                    policy=POLICY,
                )
                self.assertEqual(decision.classification, UsageClass.INSUFFICIENT)
                self.assertEqual(
                    decision.reason,
                    "insufficient-completed-post-epoch-raids",
                )
                self.assertLess(len(decision.eligible_post_epoch_raids), 8)
                self.assertEqual(decision.inspected_raids, ())


if __name__ == "__main__":
    unittest.main()
