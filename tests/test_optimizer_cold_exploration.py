from __future__ import annotations

import unittest

from optimizer.cold_exploration import plan_cold_exploration
from optimizer.cold_pool import SoloRaidUsageEvidence, StructuralDemand, UsageClass


def low(
    name: str,
    boundary: float | None,
    *,
    recent: bool = False,
    boss: bool = False,
) -> SoloRaidUsageEvidence:
    return SoloRaidUsageEvidence(
        name,
        UsageClass.LOW,
        boundary_distance=boundary,
        recent_evidence=recent,
        boss_specific_evidence=boss,
    )


class ColdExplorationPlannerTests(unittest.TestCase):
    def setUp(self):
        self.demand = StructuralDemand(
            team_count=2,
            team_size=3,
            required_roles=("1", "2"),
        )

    def test_scarce_role_precedes_closer_boundary_filler(self):
        active = ("A1", "A2", "B1", "B2", "F1", "F2")
        cold = ("scarce-b2", "very-close-filler")
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "B2": ("2",),
            "F1": (),
            "F2": (),
            "scarce-b2": ("2",),
            "very-close-filler": (),
        }
        usage = {
            "scarce-b2": low("scarce-b2", 0.009),
            "very-close-filler": low("very-close-filler", 0.0),
        }

        plan = plan_cold_exploration(
            active,
            cold,
            usage,
            roles,
            self.demand,
            limit=1,
        )

        self.assertEqual(plan.selected_characters, ("scarce-b2",))
        self.assertEqual(plan.selected[0].scarce_role_slack, 0)
        self.assertEqual(plan.deferred, ("very-close-filler",))

    def test_greedy_role_supply_update_spreads_attention(self):
        active = ("A1", "A2", "B1", "B2", "F1", "F2")
        cold = ("A-extra", "A-extra-2", "B-extra")
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "B2": ("2",),
            "F1": (),
            "F2": (),
            "A-extra": ("1",),
            "A-extra-2": ("1",),
            "B-extra": ("2",),
        }
        usage = {
            name: low(name, 0.005)
            for name in cold
        }

        plan = plan_cold_exploration(
            active,
            cold,
            usage,
            roles,
            self.demand,
            limit=2,
        )

        # Stable order breaks the first exact scarcity tie. After A-extra is
        # selected, B remains the scarcer role and receives the second probe.
        self.assertEqual(plan.selected_characters, ("A-extra", "B-extra"))
        self.assertEqual(plan.deferred, ("A-extra-2",))

    def test_boundary_then_niche_then_stable_order_breaks_same_role_ties(self):
        active = ("A1", "A2", "B1", "B2", "F1", "F2")
        cold = ("far-niche", "close", "close-niche", "close-niche-later")
        roles = {name: () for name in active + cold}
        roles.update({"A1": ("1",), "A2": ("1",), "B1": ("2",), "B2": ("2",)})
        usage = {
            "far-niche": low("far-niche", 0.009, recent=True),
            "close": low("close", 0.001),
            "close-niche": low("close-niche", 0.001, boss=True),
            "close-niche-later": low("close-niche-later", 0.001, recent=True),
        }

        plan = plan_cold_exploration(
            active,
            cold,
            usage,
            roles,
            self.demand,
            limit=4,
        )

        self.assertEqual(
            plan.selected_characters,
            ("close-niche", "close-niche-later", "close", "far-niche"),
        )

    def test_search_roster_is_temporary_active_plus_selected_only(self):
        active = ("A1", "A2", "B1", "B2", "F1", "F2")
        cold = ("C1", "C2")
        roles = {name: () for name in active + cold}
        roles.update({"A1": ("1",), "A2": ("1",), "B1": ("2",), "B2": ("2",)})
        usage = {"C1": low("C1", 0.001), "C2": low("C2", 0.002)}

        plan = plan_cold_exploration(
            active,
            cold,
            usage,
            roles,
            self.demand,
            limit=1,
        )

        self.assertEqual(plan.search_roster, active + ("C1",))
        self.assertEqual(plan.deferred, ("C2",))

    def test_limit_is_explicit_and_zero_spends_no_exploration(self):
        active = ("A1", "A2", "B1", "B2", "F1", "F2")
        roles = {name: () for name in active + ("C",)}
        roles.update({"A1": ("1",), "A2": ("1",), "B1": ("2",), "B2": ("2",)})

        plan = plan_cold_exploration(
            active,
            ("C",),
            {"C": low("C", 0.001)},
            roles,
            self.demand,
            limit=0,
        )
        self.assertEqual(plan.selected, ())
        self.assertEqual(plan.search_roster, active)
        self.assertEqual(plan.deferred, ("C",))

        with self.assertRaises(ValueError):
            plan_cold_exploration(
                active,
                ("C",),
                {"C": low("C", 0.001)},
                roles,
                self.demand,
                limit=-1,
            )

    def test_invalid_overlap_or_missing_roles_fails_loudly(self):
        with self.assertRaises(ValueError):
            plan_cold_exploration(
                ("A",),
                ("A",),
                {},
                {"A": ("1",)},
                self.demand,
                limit=1,
            )

        with self.assertRaises(ValueError):
            plan_cold_exploration(
                ("A",),
                ("C",),
                {},
                {"A": ("1",)},
                self.demand,
                limit=1,
            )


if __name__ == "__main__":
    unittest.main()
