from __future__ import annotations

import unittest
from datetime import date

from optimizer.cold_pool import StructuralDemand
from optimizer.meta_eligibility import (
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    SoloRaidPeriod,
    SoloRaidSchedule,
)
from optimizer.meta_policy import prepare_meta_guided_roster
from optimizer.meta_usage import EnikkSeasonUsageSnapshot
from optimizer.overload import OverloadKnowledge, OverloadPieceEvidence


POLICY = LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01)


def schedule() -> SoloRaidSchedule:
    return SoloRaidSchedule(
        tuple(
            SoloRaidPeriod(raid, date(2026, raid, 1), date(2026, raid, 7))
            for raid in range(1, 11)
        ),
        True,
        "fixture",
    )


def epoch(name: str) -> MetaEpochEvidence:
    # These tests exercise Cold restoration, not timestamp precision. Keep the
    # epoch strictly before S3 so the intended eight-season LOW window is valid.
    return MetaEpochEvidence(
        name,
        MetaEpochKnowledge.KNOWN,
        date(2026, 2, 28),
        "fixture",
    )


def ol0(name: str) -> OverloadPieceEvidence:
    return OverloadPieceEvidence(name, OverloadKnowledge.ZERO, 0, "fixture")


def snapshots(roster: tuple[str, ...], low: set[str]) -> tuple[EnikkSeasonUsageSnapshot, ...]:
    rows = []
    for raid in range(1, 11):
        counts = {
            name: (1 if name in low else 5)
            for name in roster
        }
        rows.append(
            EnikkSeasonUsageSnapshot(
                raid=raid,
                boss=f"boss-{raid}",
                player_count=100,
                players_with_teams=100,
                incomplete_player_rows=0,
                player_appearances=counts,
                mapped_characters=frozenset(roster),
                unknown_external_names=(),
            )
        )
    return tuple(rows)


class PrepareMetaGuidedRosterTests(unittest.TestCase):
    def test_restores_only_cold_member_needed_for_structural_five_team_supply(self):
        roster = ("A1", "A2", "B1", "B2", "F1", "F2")
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "B2": ("2",),
            "F1": (),
            "F2": (),
        }
        demand = StructuralDemand(team_count=2, team_size=3, required_roles=("1", "2"))

        result = prepare_meta_guided_roster(
            roster,
            snapshots(roster, {"B2"}),
            {name: epoch(name) for name in roster},
            {name: ol0(name) for name in roster},
            roles,
            demand,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
            restoration_batch_size=1,
        )

        self.assertEqual(result.initial_partition.cold, ("B2",))
        self.assertEqual(result.restored, ("B2",))
        self.assertEqual(result.remaining_cold, ())
        self.assertTrue(result.structurally_feasible)
        self.assertEqual(set(result.active_roster), set(roster))

    def test_does_not_restore_cold_when_primary_is_already_feasible(self):
        roster = ("A1", "A2", "B1", "B2", "F1", "F2", "F3")
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "B2": ("2",),
            "F1": (),
            "F2": (),
            "F3": (),
        }
        demand = StructuralDemand(team_count=2, team_size=3, required_roles=("1", "2"))

        result = prepare_meta_guided_roster(
            roster,
            snapshots(roster, {"F3"}),
            {name: epoch(name) for name in roster},
            {name: ol0(name) for name in roster},
            roles,
            demand,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
            restoration_batch_size=1,
        )

        self.assertEqual(result.initial_partition.cold, ("F3",))
        self.assertEqual(result.restored, ())
        self.assertEqual(result.remaining_cold, ("F3",))
        self.assertTrue(result.structurally_feasible)
        self.assertNotIn("F3", result.active_roster)

    def test_returns_infeasible_instead_of_inventing_missing_roster(self):
        roster = ("A1", "A2", "B1", "B2", "F1")
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "B2": ("2",),
            "F1": (),
        }
        demand = StructuralDemand(team_count=2, team_size=3, required_roles=("1", "2"))

        result = prepare_meta_guided_roster(
            roster,
            snapshots(roster, set()),
            {name: epoch(name) for name in roster},
            {name: ol0(name) for name in roster},
            roles,
            demand,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
            restoration_batch_size=1,
        )

        self.assertFalse(result.structurally_feasible)
        self.assertEqual(result.restored, ())
        self.assertEqual(result.restoration.feasibility.member_deficit, 1)


if __name__ == "__main__":
    unittest.main()
