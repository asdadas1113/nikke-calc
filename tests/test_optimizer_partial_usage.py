from __future__ import annotations

import unittest

from optimizer.cold_pool import SoloRaidUsageEvidence, UsageClass
from optimizer.partial_usage import (
    PartialUsageScope,
    build_partial_positive_surface,
    mark_recent_positive_usage,
)


class PartialUsageTests(unittest.TestCase):
    def test_zero_cannot_be_represented_on_partial_surface(self):
        with self.assertRaisesRegex(ValueError, "strictly positive"):
            build_partial_positive_surface(
                39,
                {"A": 0.0},
                scope=PartialUsageScope.ADVANTAGE_ONLY,
                source="enikk:S39:advantage",
            )

    def test_absent_character_never_becomes_zero_evidence(self):
        surface = build_partial_positive_surface(
            39,
            {"A": 0.003},
            scope=PartialUsageScope.ADVANTAGE_ONLY,
            source="enikk:S39:advantage",
        )
        self.assertIsNone(surface.get("B"))
        self.assertFalse(surface.absence_is_zero_safe("B"))

    def test_point_three_percent_remains_positive_observation(self):
        surface = build_partial_positive_surface(
            39,
            {"A": 0.003},
            scope=PartialUsageScope.ADVANTAGE_ONLY,
            source="enikk:S39:advantage",
        )
        self.assertAlmostEqual(surface.get("A").usage_fraction, 0.003)

    def test_recent_marker_does_not_change_classification_or_boundary(self):
        usage = {
            "A": SoloRaidUsageEvidence(
                "A", UsageClass.LOW, boundary_distance=0.002,
            ),
            "B": SoloRaidUsageEvidence("B", UsageClass.INSUFFICIENT),
        }
        surface = build_partial_positive_surface(
            39,
            {"A": 0.003},
            scope=PartialUsageScope.ADVANTAGE_ONLY,
            source="enikk:S39:advantage",
        )
        marked = mark_recent_positive_usage(usage, (surface,))

        self.assertEqual(marked["A"].classification, UsageClass.LOW)
        self.assertEqual(marked["A"].boundary_distance, 0.002)
        self.assertTrue(marked["A"].recent_evidence)
        self.assertEqual(marked["B"], usage["B"])

    def test_no_popularity_threshold_is_applied(self):
        surface = build_partial_positive_surface(
            39,
            {"rare": 0.00001, "common": 1.0},
            scope=PartialUsageScope.PARTIAL_POSITIVE,
            source="synthetic",
        )
        self.assertEqual(surface.observed_characters, ("rare", "common"))


if __name__ == "__main__":
    unittest.main()
