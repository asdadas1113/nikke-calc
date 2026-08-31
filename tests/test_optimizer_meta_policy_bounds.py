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
from optimizer.meta_policy_bounds import build_meta_guided_partition_bounded
from optimizer.meta_usage_bounds import (
    CertifiedEnikkSeasonUsageSnapshot,
    RankingCoverageContract,
)
from optimizer.overload import OverloadKnowledge, OverloadPieceEvidence


CONTRACT = RankingCoverageContract(
    servers=("GLOBAL", "JP", "KR", "NA", "SEA", "TW-HK"),
    rank_start=1,
    rank_end=50,
    team_count=5,
    team_size=5,
    source="fixture",
)


def schedule():
    periods = []
    for offset, raid in enumerate(range(33, 41)):
        start = date(2026, 1, 10) + timedelta(days=offset * 10)
        periods.append(SoloRaidPeriod(raid, start, start + timedelta(days=2)))
    return SoloRaidSchedule(tuple(periods), complete=True, source="fixture")


def snapshots():
    # A: upper=(0+2)/300 <1% => LOW
    # B: lower=2/300, upper=4/300 => boundary crossed => INSUFFICIENT
    # C: lower=4/300 >1% => USED
    return tuple(
        CertifiedEnikkSeasonUsageSnapshot(
            raid=raid,
            boss="fixture",
            contract=CONTRACT,
            observed_complete_player_slots=298,
            missing_player_slots=2,
            malformed_player_slots=0,
            mapping_uncertain_player_slots=0,
            player_appearances={"B": 2, "C": 4},
            mapped_characters=frozenset({"A", "B", "C"}),
            unknown_external_names=(),
        )
        for raid in range(33, 41)
    )


def epochs():
    return {
        name: MetaEpochEvidence(
            name,
            MetaEpochKnowledge.KNOWN,
            date(2026, 1, 1),
            "fixture",
        )
        for name in ("A", "B", "C")
    }


def ol(name: str, knowledge: OverloadKnowledge, pieces):
    return OverloadPieceEvidence(name, knowledge, pieces, "fixture")


class BoundedMetaPolicyTests(unittest.TestCase):
    def test_only_safely_low_plus_proven_ol0_enters_cold(self):
        result = build_meta_guided_partition_bounded(
            ("A", "B", "C"),
            snapshots(),
            epochs(),
            {
                "A": ol("A", OverloadKnowledge.ZERO, 0),
                "B": ol("B", OverloadKnowledge.ZERO, 0),
                "C": ol("C", OverloadKnowledge.ZERO, 0),
            },
            schedule=schedule(),
            completed_through=date(2026, 4, 1),
            policy=LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01),
        )

        classes = {
            row.character: row.classification
            for row in result.usage.decisions
        }
        self.assertEqual(classes["A"], UsageClass.LOW)
        self.assertEqual(classes["B"], UsageClass.INSUFFICIENT)
        self.assertEqual(classes["C"], UsageClass.USED)
        self.assertEqual(result.partition.cold, ("A",))
        self.assertEqual(result.partition.primary, ("B", "C"))

    def test_low_usage_with_present_or_unknown_ol_stays_primary(self):
        result = build_meta_guided_partition_bounded(
            ("A", "B", "C"),
            snapshots(),
            epochs(),
            {
                "A": ol("A", OverloadKnowledge.PRESENT, 1),
                "B": ol("B", OverloadKnowledge.UNKNOWN, None),
                "C": ol("C", OverloadKnowledge.ZERO, 0),
            },
            schedule=schedule(),
            completed_through=date(2026, 4, 1),
            policy=LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01),
        )
        self.assertEqual(result.partition.cold, ())
        self.assertEqual(result.partition.primary, ("A", "B", "C"))


if __name__ == "__main__":
    unittest.main()
