from __future__ import annotations

import unittest

from optimizer.reference_sources import adapt_external_reference_compositions
from optimizer.seed_sources import CompositionOrderKnowledge, ExternalCompositionEvidence


class ReferenceSourceAdaptationTests(unittest.TestCase):
    def test_unknown_order_stays_unordered_reference_hypothesis(self):
        row = ExternalCompositionEvidence(
            members=("A", "B", "C", "D", "E"),
            order_knowledge=CompositionOrderKnowledge.UNKNOWN_ORDER,
            source="external:one",
        )
        result = adapt_external_reference_compositions(
            (row,),
            owned_roster=("A", "B", "C", "D", "E"),
        )

        self.assertEqual(len(result.compositions), 1)
        self.assertFalse(result.compositions[0].order_known)
        self.assertEqual(result.compositions[0].members, row.members)

    def test_proven_order_is_preserved_exactly(self):
        row = ExternalCompositionEvidence(
            members=("E", "D", "C", "B", "A"),
            order_knowledge=CompositionOrderKnowledge.PROVEN_ORDERED,
            source="external:ordered",
        )
        result = adapt_external_reference_compositions(
            (row,),
            owned_roster=("A", "B", "C", "D", "E"),
        )

        self.assertTrue(result.compositions[0].order_known)
        self.assertEqual(result.compositions[0].members, ("E", "D", "C", "B", "A"))

    def test_unowned_members_are_skipped_not_replaced(self):
        row = ExternalCompositionEvidence(
            members=("A", "B", "C", "D", "X"),
            order_knowledge=CompositionOrderKnowledge.MEMBERSHIP_ONLY,
            source="external:missing",
        )
        result = adapt_external_reference_compositions(
            (row,),
            owned_roster=("A", "B", "C", "D", "E"),
        )

        self.assertEqual(result.compositions, ())
        self.assertEqual(result.skipped[0].reason, "unowned-members:X")

    def test_duplicate_unknown_membership_does_not_gain_popularity_weight(self):
        one = ExternalCompositionEvidence(
            members=("A", "B", "C", "D", "E"),
            order_knowledge=CompositionOrderKnowledge.UNKNOWN_ORDER,
            source="rank1",
        )
        two = ExternalCompositionEvidence(
            members=("E", "D", "C", "B", "A"),
            order_knowledge=CompositionOrderKnowledge.UNKNOWN_ORDER,
            source="rank2",
        )
        result = adapt_external_reference_compositions(
            (one, two),
            owned_roster=("A", "B", "C", "D", "E"),
        )

        self.assertEqual(len(result.compositions), 1)
        self.assertEqual(result.compositions[0].source, "rank1")


if __name__ == "__main__":
    unittest.main()
