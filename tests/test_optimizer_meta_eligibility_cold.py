from __future__ import annotations

import unittest
from datetime import date

from optimizer.cold_pool import UsageClass
from optimizer.meta_eligibility import (
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    MetaUsageDecision,
    to_solo_raid_usage_evidence,
)
from optimizer.meta_usage import CharacterUsageWindow


class MetaEligibilityColdAdapterTests(unittest.TestCase):
    def test_low_decision_exports_boundary_distance_without_score_bonus(self):
        policy = LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01)
        window = CharacterUsageWindow(
            character="N",
            requested_eligible_raids=tuple(range(3, 11)),
            usable_raids=tuple(range(3, 11)),
            uncertain_raids=(),
            positive_raids=(3,),
            zero_raids=tuple(range(4, 11)),
            usage_fractions=tuple((raid, 0.005 if raid == 3 else 0.0) for raid in range(3, 11)),
            peak_usage=0.005,
            median_usage=0.0,
        )
        epoch = MetaEpochEvidence(
            "N", MetaEpochKnowledge.KNOWN, date(2026, 3, 1), "fixture"
        )
        decision = MetaUsageDecision(
            character="N",
            classification=UsageClass.LOW,
            reason="fixture-low",
            eligible_post_epoch_raids=tuple(range(3, 11)),
            inspected_raids=tuple(range(3, 11)),
            window=window,
            epoch=epoch,
            schedule_source="fixture",
            policy=policy,
        )

        evidence = to_solo_raid_usage_evidence(decision)

        self.assertEqual(evidence.classification, UsageClass.LOW)
        self.assertAlmostEqual(evidence.boundary_distance, 0.005)
        self.assertFalse(evidence.recent_evidence)
        self.assertFalse(evidence.boss_specific_evidence)

    def test_insufficient_decision_exports_no_boundary_distance(self):
        epoch = MetaEpochEvidence("N", MetaEpochKnowledge.UNKNOWN, None, "fixture")
        decision = MetaUsageDecision(
            character="N",
            classification=UsageClass.INSUFFICIENT,
            reason="unknown",
            eligible_post_epoch_raids=(),
            inspected_raids=(),
            window=None,
            epoch=epoch,
            schedule_source="fixture",
            policy=LowUsagePolicy(),
        )

        evidence = to_solo_raid_usage_evidence(decision, recent_evidence=True)

        self.assertEqual(evidence.classification, UsageClass.INSUFFICIENT)
        self.assertIsNone(evidence.boundary_distance)
        self.assertTrue(evidence.recent_evidence)


if __name__ == "__main__":
    unittest.main()
