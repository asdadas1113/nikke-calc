from __future__ import annotations

import unittest

import optimizer
from optimizer import meta_eligibility, meta_eligibility_bounds, meta_policy, meta_policy_bounds


class OptimizerPublicMetaApiTests(unittest.TestCase):
    def test_unqualified_meta_classification_is_bounded(self):
        self.assertIs(
            optimizer.classify_meta_epoch_usage,
            meta_eligibility_bounds.classify_meta_epoch_usage_bounded,
        )
        self.assertIs(
            optimizer.classify_roster_meta_usage,
            meta_policy_bounds.classify_roster_meta_usage_bounded,
        )

    def test_unqualified_meta_partition_and_preparation_are_bounded(self):
        self.assertIs(
            optimizer.build_meta_guided_partition,
            meta_policy_bounds.build_meta_guided_partition_bounded,
        )
        self.assertIs(
            optimizer.prepare_meta_guided_roster,
            meta_policy_bounds.prepare_meta_guided_roster_bounded,
        )
        self.assertIs(
            optimizer.prepare_meta_guided_search_roster,
            meta_policy_bounds.prepare_meta_guided_search_roster_bounded,
        )

    def test_research_aliases_preserve_descriptive_implementations(self):
        self.assertIs(
            optimizer.research_classify_meta_epoch_usage,
            meta_eligibility.classify_meta_epoch_usage,
        )
        self.assertIs(
            optimizer.research_build_meta_guided_partition,
            meta_policy.build_meta_guided_partition,
        )
        self.assertIs(
            optimizer.research_prepare_meta_guided_search_roster,
            meta_policy.prepare_meta_guided_search_roster,
        )

    def test_certified_usage_types_are_public_and_descriptive_names_are_explicit(self):
        self.assertIn("CertifiedEnikkSeasonUsageSnapshot", optimizer.__all__)
        self.assertIn("RankingCoverageContract", optimizer.__all__)
        self.assertIn("certify_enikk_rankings", optimizer.__all__)
        self.assertIn("aggregate_bounded_character_window", optimizer.__all__)
        self.assertNotIn("EnikkSeasonUsageSnapshot", optimizer.__all__)
        self.assertNotIn("summarize_enikk_rankings", optimizer.__all__)
        self.assertIn("ResearchEnikkSeasonUsageSnapshot", optimizer.__all__)
        self.assertIn("research_summarize_enikk_rankings", optimizer.__all__)


if __name__ == "__main__":
    unittest.main()
