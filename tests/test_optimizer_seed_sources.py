from __future__ import annotations

import unittest

from optimizer.seed_sources import (
    CompositionOrderKnowledge,
    ExternalCompositionEvidence,
    adapt_external_compositions,
    normalize_enikk_sr_team,
    normalize_labeled_composition,
)


MEMBERS = ("A", "B", "C", "D", "E")


class ExternalSeedSourceTests(unittest.TestCase):
    def test_only_proven_ordered_evidence_becomes_exact_seed(self):
        proven = ExternalCompositionEvidence(
            MEMBERS,
            CompositionOrderKnowledge.PROVEN_ORDERED,
            "fixture:ordered",
        )
        unknown = ExternalCompositionEvidence(
            ("E", "D", "C", "B", "A"),
            CompositionOrderKnowledge.UNKNOWN_ORDER,
            "fixture:unknown",
        )

        result = adapt_external_compositions((proven, unknown))

        self.assertEqual(tuple(seed.members for seed in result.exact_seeds), (MEMBERS,))
        self.assertEqual(len(result.core_seeds), 1)
        self.assertEqual(set(result.core_seeds[0].members), set(MEMBERS))

    def test_membership_only_and_unknown_order_never_create_exact_seed(self):
        rows = (
            ExternalCompositionEvidence(
                MEMBERS,
                CompositionOrderKnowledge.MEMBERSHIP_ONLY,
                "fixture:membership",
            ),
            ExternalCompositionEvidence(
                ("B", "A", "E", "D", "C"),
                CompositionOrderKnowledge.UNKNOWN_ORDER,
                "fixture:unknown",
            ),
        )

        result = adapt_external_compositions(rows)

        self.assertEqual(result.exact_seeds, ())
        # Same five-member relationship is deduplicated despite display order.
        self.assertEqual(len(result.core_seeds), 1)
        self.assertEqual(result.core_seeds[0].members, tuple(sorted(MEMBERS)))

    def test_incomplete_mapping_is_skipped_instead_of_guessing(self):
        evidence = normalize_labeled_composition(
            ("a", "b", "missing", "d", "e"),
            {"a": "A", "b": "B", "d": "D", "e": "E"},
            source="fixture",
        )
        self.assertFalse(evidence.mapping_complete)
        self.assertEqual(evidence.unmapped_labels, ("missing",))

        result = adapt_external_compositions((evidence,))
        self.assertEqual(result.exact_seeds, ())
        self.assertEqual(result.core_seeds, ())
        self.assertEqual(result.skipped[0].reason, "incomplete-character-mapping")

    def test_wrong_team_size_is_diagnostic_not_partial_core(self):
        evidence = ExternalCompositionEvidence(
            ("A", "B", "C", "D"),
            CompositionOrderKnowledge.UNKNOWN_ORDER,
            "fixture",
        )
        result = adapt_external_compositions((evidence,))
        self.assertEqual(result.core_seeds, ())
        self.assertEqual(result.skipped[0].reason, "unexpected-team-size")

    def test_enikk_serialized_character_array_defaults_to_unknown_order(self):
        evidence = normalize_enikk_sr_team(
            {"characters": ["a", "b", "c", "d", "e"]},
            {"a": "A", "b": "B", "c": "C", "d": "D", "e": "E"},
            source="enikk:S39:rank1:team1",
        )

        self.assertEqual(
            evidence.order_knowledge,
            CompositionOrderKnowledge.UNKNOWN_ORDER,
        )
        result = adapt_external_compositions((evidence,))
        self.assertEqual(result.exact_seeds, ())
        self.assertEqual(len(result.core_seeds), 1)

    def test_explicit_source_contract_can_promote_enikk_row_to_exact(self):
        evidence = normalize_enikk_sr_team(
            {"characters": ["a", "b", "c", "d", "e"]},
            {"a": "A", "b": "B", "c": "C", "d": "D", "e": "E"},
            source="fixture:documented-order",
            order_knowledge=CompositionOrderKnowledge.PROVEN_ORDERED,
        )
        result = adapt_external_compositions((evidence,))
        self.assertEqual(tuple(seed.members for seed in result.exact_seeds), (MEMBERS,))
        self.assertEqual(result.core_seeds, ())

    def test_duplicate_canonical_member_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_labeled_composition(
                ("a", "a2", "c", "d", "e"),
                {"a": "A", "a2": "A", "c": "C", "d": "D", "e": "E"},
                source="fixture",
            )


if __name__ == "__main__":
    unittest.main()
