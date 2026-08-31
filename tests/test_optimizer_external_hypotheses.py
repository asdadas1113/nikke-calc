from __future__ import annotations

import unittest

from optimizer.external_hypotheses import build_external_hypothesis_plan
from optimizer.seed_sources import CompositionOrderKnowledge, ExternalCompositionEvidence


class ExternalHypothesisPlanTests(unittest.TestCase):
    def test_unknown_order_yields_core_seed_and_unordered_reference_from_same_row(self):
        row = ExternalCompositionEvidence(
            members=("A", "B", "C", "D", "E"),
            order_knowledge=CompositionOrderKnowledge.UNKNOWN_ORDER,
            source="external:one",
        )
        plan = build_external_hypothesis_plan(
            (row,),
            owned_roster=("A", "B", "C", "D", "E"),
        )

        self.assertEqual(len(plan.seeds.core_seeds), 1)
        self.assertEqual(set(plan.seeds.core_seeds[0].members), set(row.members))
        self.assertEqual(len(plan.references.compositions), 1)
        self.assertFalse(plan.references.compositions[0].order_known)
        self.assertEqual(plan.references.compositions[0].source, row.source)
        self.assertEqual(plan.skipped_before_adaptation, ())

    def test_proven_order_yields_exact_seed_and_exact_reference(self):
        row = ExternalCompositionEvidence(
            members=("E", "D", "C", "B", "A"),
            order_knowledge=CompositionOrderKnowledge.PROVEN_ORDERED,
            source="external:ordered",
        )
        plan = build_external_hypothesis_plan(
            (row,),
            owned_roster=("A", "B", "C", "D", "E"),
        )

        self.assertEqual(plan.seeds.exact_seeds[0].members, row.members)
        self.assertEqual(plan.references.compositions[0].members, row.members)
        self.assertTrue(plan.references.compositions[0].order_known)

    def test_unowned_public_composition_is_skipped_for_both_channels_without_replacement(self):
        row = ExternalCompositionEvidence(
            members=("A", "B", "C", "D", "X"),
            order_knowledge=CompositionOrderKnowledge.UNKNOWN_ORDER,
            source="external:missing",
        )
        plan = build_external_hypothesis_plan(
            (row,),
            owned_roster=("A", "B", "C", "D", "E"),
        )

        self.assertEqual(plan.seeds.exact_seeds, ())
        self.assertEqual(plan.seeds.core_seeds, ())
        self.assertEqual(plan.references.compositions, ())
        self.assertEqual(
            plan.skipped_before_adaptation[0].reason,
            "unowned-members:X",
        )

    def test_incomplete_mapping_is_visible_once_before_both_channels(self):
        row = ExternalCompositionEvidence(
            members=("A", "B", "C", "D"),
            order_knowledge=CompositionOrderKnowledge.UNKNOWN_ORDER,
            source="external:unknown-id",
            mapping_complete=False,
            unmapped_labels=("999",),
        )
        plan = build_external_hypothesis_plan(
            (row,),
            owned_roster=("A", "B", "C", "D", "E"),
        )
        self.assertEqual(plan.seeds.core_seeds, ())
        self.assertEqual(plan.references.compositions, ())
        self.assertEqual(
            plan.skipped_before_adaptation[0].reason,
            "incomplete-character-mapping",
        )


if __name__ == "__main__":
    unittest.main()
