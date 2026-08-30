from __future__ import annotations

import unittest

from optimizer.constraints import (
    BurstMetadata,
    BurstStructureValidator,
    ConstraintSet,
    TeamRequirement,
)


class BurstStructureValidatorTest(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "B1": BurstMetadata("1", 20.0),
            "B2": BurstMetadata("2", 40.0),
            "B3": BurstMetadata("3", 40.0),
            "ALT3": BurstMetadata("3", 20.0),
            "FLEX": BurstMetadata("A", 40.0),
            "DYN2": BurstMetadata("3", 40.0, frozenset({"2"})),
        }

    def test_missing_stage_is_hard_rejected(self):
        validator = BurstStructureValidator(self.metadata)
        report = validator.inspect(("B1", "B3"))

        self.assertFalse(report.legal)
        self.assertEqual(report.missing_stages, ("2",))
        self.assertEqual(report.uncertain_stages, ())

    def test_cooldown_is_diagnostic_not_legality_threshold(self):
        validator = BurstStructureValidator(self.metadata)
        report = validator.inspect(("B1", "B2", "B3"))

        self.assertTrue(report.legal)
        self.assertEqual(report.min_cooldown_by_stage["1"], 20.0)
        self.assertEqual(report.min_cooldown_by_stage["2"], 40.0)
        self.assertEqual(report.min_cooldown_by_stage["3"], 40.0)

    def test_flexible_a_stage_fills_all_static_buckets(self):
        validator = BurstStructureValidator(self.metadata)
        report = validator.inspect(("FLEX",))

        self.assertTrue(report.legal)
        self.assertEqual(report.eligible_by_stage["1"], ("FLEX",))
        self.assertEqual(report.eligible_by_stage["2"], ("FLEX",))
        self.assertEqual(report.eligible_by_stage["3"], ("FLEX",))

    def test_auto_mode_no_burst_names_are_removed_from_candidates(self):
        validator = BurstStructureValidator(self.metadata, no_burst_names={"B2"})
        report = validator.inspect(("B1", "B2", "B3"))

        self.assertFalse(report.legal)
        self.assertEqual(report.missing_stages, ("2",))

    def test_dynamic_stage_possibility_survives_hard_pruning(self):
        validator = BurstStructureValidator(self.metadata)
        report = validator.inspect(("B1", "DYN2", "B3"))

        self.assertTrue(report.legal)
        self.assertEqual(report.missing_stages, ())
        self.assertEqual(report.uncertain_stages, ("2",))
        self.assertFalse(report.fully_resolved)

    def test_explicit_sequence_is_deferred_to_moris(self):
        validator = BurstStructureValidator(self.metadata, explicit_sequence=True)
        report = validator.inspect(("B3",))

        self.assertTrue(report.legal)
        self.assertFalse(report.fully_resolved)
        self.assertIn("burst_sequence", report.deferred_reason or "")

    def test_character_stage_override_matches_moris_input_semantics(self):
        validator = BurstStructureValidator(
            self.metadata,
            stage_overrides={"FLEX": "2"},
        )
        report = validator.inspect(("B1", "FLEX", "B3"))

        self.assertTrue(report.legal)
        self.assertEqual(report.eligible_by_stage["1"], ("B1",))
        self.assertEqual(report.eligible_by_stage["2"], ("FLEX",))
        self.assertEqual(report.eligible_by_stage["3"], ("B3",))

    def test_constraint_set_can_use_burst_validator_as_hard_constraint(self):
        validator = BurstStructureValidator(self.metadata)
        constraints = ConstraintSet(team_size=3, validators=(validator,))

        self.assertTrue(constraints.validate_team(("B1", "B2", "B3")))
        self.assertFalse(constraints.validate_team(("B1", "B3", "ALT3")))

    def test_named_requirement_is_domain_agnostic_and_constraint_set_is_callable(self):
        requirement = TeamRequirement(
            "future-policy",
            lambda team: "A" in team or {"B", "C"}.issubset(team),
        )
        constraints = ConstraintSet(team_size=3, requirements=(requirement,))

        self.assertTrue(constraints(("A", "X", "Y")))
        self.assertTrue(constraints(("B", "C", "X")))
        self.assertFalse(constraints(("X", "Y", "Z")))
        self.assertEqual(
            constraints.failed_requirements(("X", "Y", "Z")),
            ("future-policy",),
        )

    def test_named_requirement_labels_must_be_unique(self):
        first = TeamRequirement("same", lambda team: True)
        second = TeamRequirement("same", lambda team: True)

        with self.assertRaises(ValueError):
            ConstraintSet(requirements=(first, second))

    def test_named_requirement_label_must_be_non_empty(self):
        with self.assertRaises(ValueError):
            TeamRequirement("   ", lambda team: True)

    def test_from_moris_reads_canonical_stage_and_cooldown_metadata(self):
        validator = BurstStructureValidator.from_moris()
        report = validator.inspect(("네온", "아니스", "라피"))

        self.assertTrue(report.legal)
        self.assertTrue(report.fully_resolved)
        self.assertEqual(report.min_cooldown_by_stage["1"], 20.0)
        self.assertEqual(report.min_cooldown_by_stage["2"], 20.0)
        self.assertEqual(report.min_cooldown_by_stage["3"], 40.0)


if __name__ == "__main__":
    unittest.main()
