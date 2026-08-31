from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.cold_pool import (
    ColdPoolPartition,
    SoloRaidUsageEvidence,
    StructuralDemand,
    UsageClass,
    build_burst_role_map,
    check_structural_feasibility,
    partition_meta_guided_roster,
    restore_cold_until_feasible,
)
from optimizer.overload import OverloadKnowledge, OverloadPieceEvidence


def usage(
    name: str,
    classification: UsageClass,
    *,
    boundary: float | None = None,
    recent: bool = False,
    boss: bool = False,
) -> SoloRaidUsageEvidence:
    return SoloRaidUsageEvidence(
        name,
        classification,
        boundary_distance=boundary,
        recent_evidence=recent,
        boss_specific_evidence=boss,
    )


def overload(name: str, knowledge: OverloadKnowledge, count: int | None) -> OverloadPieceEvidence:
    return OverloadPieceEvidence(name, knowledge, count, "fixture")


class ColdPoolPartitionTests(unittest.TestCase):
    def test_only_low_usage_plus_proven_zero_goes_cold(self):
        roster = ("cold", "invested", "unknown", "used", "new", "protected")
        usage_rows = {
            "cold": usage("cold", UsageClass.LOW),
            "invested": usage("invested", UsageClass.LOW),
            "unknown": usage("unknown", UsageClass.LOW),
            "used": usage("used", UsageClass.USED),
            "new": usage("new", UsageClass.INSUFFICIENT),
            "protected": usage("protected", UsageClass.LOW),
        }
        overload_rows = {
            "cold": overload("cold", OverloadKnowledge.ZERO, 0),
            "invested": overload("invested", OverloadKnowledge.PRESENT, 2),
            "unknown": overload("unknown", OverloadKnowledge.UNKNOWN, None),
            "used": overload("used", OverloadKnowledge.ZERO, 0),
            "new": overload("new", OverloadKnowledge.ZERO, 0),
            "protected": overload("protected", OverloadKnowledge.ZERO, 0),
        }

        result = partition_meta_guided_roster(
            roster,
            usage_rows,
            overload_rows,
            protected_names=("protected",),
        )

        self.assertEqual(result.cold, ("cold",))
        self.assertEqual(
            result.primary,
            ("invested", "unknown", "used", "new", "protected"),
        )
        self.assertEqual(result.protected, ("protected",))
        self.assertEqual(result.fail_open, ("unknown", "new"))

    def test_missing_usage_or_overload_fails_open(self):
        roster = ("missing-usage", "missing-overload")
        result = partition_meta_guided_roster(
            roster,
            {"missing-overload": usage("missing-overload", UsageClass.LOW)},
            {"missing-usage": overload("missing-usage", OverloadKnowledge.ZERO, 0)},
        )
        self.assertEqual(result.primary, roster)
        self.assertEqual(result.cold, ())
        self.assertEqual(result.fail_open, roster)


class StructuralFeasibilityTests(unittest.TestCase):
    def test_multirole_character_can_cover_multiple_roles_inside_one_team(self):
        demand = StructuralDemand(team_count=2, team_size=2, required_roles=("1", "2", "3"))
        roles = {
            "A": ("1", "2", "3"),
            "B": ("1", "2", "3"),
            "C": (),
            "D": (),
        }

        result = check_structural_feasibility(("A", "B", "C", "D"), roles, demand)

        self.assertTrue(result.feasible)
        self.assertEqual(result.complete_teams, 2)
        self.assertEqual(result.covered_role_slots, 6)

    def test_role_complete_but_too_few_total_members_is_not_feasible(self):
        demand = StructuralDemand(team_count=2, team_size=3, required_roles=("1", "2", "3"))
        roles = {
            "A": ("1", "2", "3"),
            "B": ("1", "2", "3"),
            "C": (),
            "D": (),
            "E": (),
        }
        result = check_structural_feasibility(("A", "B", "C", "D", "E"), roles, demand)
        self.assertFalse(result.feasible)
        self.assertEqual(result.complete_teams, 2)
        self.assertEqual(result.member_deficit, 1)

    def test_missing_role_metadata_is_rejected_instead_of_guessed(self):
        demand = StructuralDemand(team_count=1, team_size=2, required_roles=("1", "2"))
        with self.assertRaisesRegex(ValueError, "missing structural roles"):
            check_structural_feasibility(("A", "B"), {"A": ("1",)}, demand)

    def test_burst_role_projection_includes_uncertain_dynamic_stage(self):
        reports = {
            "A": SimpleNamespace(
                deferred_reason=None,
                eligible_by_stage={"1": ("A",), "2": (), "3": ()},
                uncertain_stages=("2",),
            ),
            "B": SimpleNamespace(
                deferred_reason=None,
                eligible_by_stage={"1": (), "2": (), "3": ("B",)},
                uncertain_stages=(),
            ),
        }

        class FakeValidator:
            def inspect(self, members):
                return reports[members[0]]

        self.assertEqual(
            build_burst_role_map(FakeValidator(), ("A", "B")),
            {"A": frozenset({"1", "2"}), "B": frozenset({"3"})},
        )

    def test_burst_role_projection_rejects_deferred_explicit_sequence_semantics(self):
        class FakeValidator:
            def inspect(self, members):
                return SimpleNamespace(
                    deferred_reason="explicit burst_sequence requires simulator validation",
                    eligible_by_stage={"1": (), "2": (), "3": ()},
                    uncertain_stages=(),
                )

        with self.assertRaisesRegex(ValueError, "projection is unavailable"):
            build_burst_role_map(FakeValidator(), ("A",))


class ColdRestorationTests(unittest.TestCase):
    def test_structural_role_gain_beats_usage_boundary_proximity(self):
        demand = StructuralDemand(team_count=2, team_size=3, required_roles=("1", "2"))
        partition = ColdPoolPartition(
            primary=("A1", "A2", "B1", "F1", "F2"),
            cold=("A-close", "B-far"),
            protected=(),
            fail_open=(),
            decisions=(),
        )
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "F1": (),
            "F2": (),
            "A-close": ("1",),
            "B-far": ("2",),
        }
        usage_rows = {
            "A-close": usage("A-close", UsageClass.LOW, boundary=0.01),
            "B-far": usage("B-far", UsageClass.LOW, boundary=5.0),
        }

        result = restore_cold_until_feasible(
            partition,
            usage_rows,
            roles,
            demand,
            batch_size=1,
        )

        self.assertTrue(result.feasibility.feasible)
        self.assertEqual(result.restored, ("B-far",))
        self.assertEqual(result.remaining_cold, ("A-close",))

    def test_boundary_then_recent_boss_evidence_break_restoration_ties(self):
        demand = StructuralDemand(team_count=1, team_size=3, required_roles=("1", "2"))
        partition = ColdPoolPartition(
            primary=("A", "B"),
            cold=("far-niche", "close-plain", "close-niche"),
            protected=(),
            fail_open=(),
            decisions=(),
        )
        roles = {name: () for name in partition.primary + partition.cold}
        roles["A"] = ("1",)
        roles["B"] = ("2",)
        usage_rows = {
            "far-niche": usage("far-niche", UsageClass.LOW, boundary=2.0, boss=True),
            "close-plain": usage("close-plain", UsageClass.LOW, boundary=0.1),
            "close-niche": usage("close-niche", UsageClass.LOW, boundary=0.1, recent=True),
        }

        result = restore_cold_until_feasible(
            partition,
            usage_rows,
            roles,
            demand,
            batch_size=1,
        )

        # Roles are already complete; the only deficit is one filler. Boundary
        # proximity wins first, then niche evidence breaks the exact boundary tie.
        self.assertEqual(result.restored, ("close-niche",))
        self.assertTrue(result.feasibility.feasible)

    def test_restoration_rechecks_after_each_explicit_batch(self):
        demand = StructuralDemand(team_count=2, team_size=3, required_roles=("1", "2"))
        partition = ColdPoolPartition(
            primary=("A1", "B1", "F1", "F2"),
            cold=("A2", "B2", "F3", "F4"),
            protected=(),
            fail_open=(),
            decisions=(),
        )
        roles = {
            "A1": ("1",), "B1": ("2",), "F1": (), "F2": (),
            "A2": ("1",), "B2": ("2",), "F3": (), "F4": (),
        }
        usage_rows = {
            name: usage(name, UsageClass.LOW, boundary=float(index))
            for index, name in enumerate(partition.cold)
        }

        result = restore_cold_until_feasible(
            partition,
            usage_rows,
            roles,
            demand,
            batch_size=1,
        )

        self.assertTrue(result.feasibility.feasible)
        self.assertEqual(len(result.steps), len(result.restored))
        self.assertEqual(result.restored[:2], ("A2", "B2"))
        self.assertEqual(len(result.primary), 6)


if __name__ == "__main__":
    unittest.main()
