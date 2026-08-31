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
from optimizer.meta_policy import prepare_meta_guided_search_roster
from optimizer.meta_usage import EnikkSeasonUsageSnapshot
from optimizer.overload import OverloadKnowledge, OverloadPieceEvidence


POLICY = LowUsagePolicy(completed_seasons=8, max_peak_usage=0.01)
DEMAND = StructuralDemand(team_count=2, team_size=3, required_roles=("1", "2"))


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
    # These tests exercise search-roster restoration/exploration. Keep the epoch
    # strictly before S3 so the intended eight-season LOW window is unambiguous.
    return MetaEpochEvidence(
        name,
        MetaEpochKnowledge.KNOWN,
        date(2026, 2, 28),
        "fixture",
    )


def ol0(name: str) -> OverloadPieceEvidence:
    return OverloadPieceEvidence(name, OverloadKnowledge.ZERO, 0, "fixture")


def snapshots(roster: tuple[str, ...], low_names: set[str]) -> tuple[EnikkSeasonUsageSnapshot, ...]:
    rows = []
    for raid in range(1, 11):
        counts = {
            name: (1 if name in low_names else 5)
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


class MetaGuidedSearchPreparationTests(unittest.TestCase):
    def test_primary_feasible_still_gets_explicit_bounded_cold_exploration(self):
        roster = ("A1", "A2", "B1", "B2", "F1", "F2", "cold-filler", "cold-b2")
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "B2": ("2",),
            "F1": (),
            "F2": (),
            "cold-filler": (),
            "cold-b2": ("2",),
        }
        result = prepare_meta_guided_search_roster(
            roster,
            snapshots(roster, {"cold-filler", "cold-b2"}),
            {name: epoch(name) for name in roster},
            {name: ol0(name) for name in roster},
            roles,
            DEMAND,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
            restoration_batch_size=1,
            cold_exploration_limit=1,
        )

        self.assertTrue(result.prepared.structurally_feasible)
        self.assertEqual(result.prepared.restored, ())
        self.assertEqual(
            set(result.prepared.initial_partition.cold),
            {"cold-filler", "cold-b2"},
        )
        # Same score-blind scarce-role policy as the standalone planner.
        self.assertEqual(result.explored_cold, ("cold-b2",))
        self.assertEqual(result.still_deferred_cold, ("cold-filler",))
        self.assertIn("cold-b2", result.search_roster)
        self.assertNotIn("cold-filler", result.search_roster)
        # Exploration does not rewrite the original classification.
        self.assertIn("cold-b2", result.prepared.initial_partition.cold)

    def test_structurally_required_cold_is_restored_not_counted_as_exploration(self):
        roster = ("A1", "A2", "B1", "B2", "F1", "F2", "cold-filler")
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "B2": ("2",),
            "F1": (),
            "F2": (),
            "cold-filler": (),
        }
        # Make B2 Cold, so Primary cannot supply two B2-complete teams until B2 is restored.
        result = prepare_meta_guided_search_roster(
            roster,
            snapshots(roster, {"B2", "cold-filler"}),
            {name: epoch(name) for name in roster},
            {name: ol0(name) for name in roster},
            roles,
            DEMAND,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
            restoration_batch_size=1,
            cold_exploration_limit=1,
        )

        self.assertEqual(result.prepared.restored, ("B2",))
        self.assertEqual(result.explored_cold, ("cold-filler",))
        self.assertIn("B2", result.prepared.active_roster)
        self.assertIn("cold-filler", result.search_roster)

    def test_priority_review_bypass_never_spends_cold_exploration_quota(self):
        roster = ("A1", "A2", "B1", "B2", "F1", "F2", "review", "cold")
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "B2": ("2",),
            "F1": (),
            "F2": (),
            "review": (),
            "cold": (),
        }
        result = prepare_meta_guided_search_roster(
            roster,
            snapshots(roster, {"review", "cold"}),
            {name: epoch(name) for name in roster},
            {name: ol0(name) for name in roster},
            roles,
            DEMAND,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
            restoration_batch_size=1,
            cold_exploration_limit=1,
            protected_names=("review",),
        )

        self.assertIn("review", result.prepared.active_roster)
        self.assertNotIn("review", result.prepared.initial_partition.cold)
        self.assertEqual(result.explored_cold, ("cold",))

    def test_zero_exploration_limit_preserves_restored_active_roster_only(self):
        roster = ("A1", "A2", "B1", "B2", "F1", "F2", "cold")
        roles = {
            "A1": ("1",),
            "A2": ("1",),
            "B1": ("2",),
            "B2": ("2",),
            "F1": (),
            "F2": (),
            "cold": (),
        }
        result = prepare_meta_guided_search_roster(
            roster,
            snapshots(roster, {"cold"}),
            {name: epoch(name) for name in roster},
            {name: ol0(name) for name in roster},
            roles,
            DEMAND,
            schedule=schedule(),
            completed_through=date(2026, 10, 7),
            policy=POLICY,
            restoration_batch_size=1,
            cold_exploration_limit=0,
        )

        self.assertEqual(result.explored_cold, ())
        self.assertEqual(result.search_roster, result.prepared.active_roster)
        self.assertEqual(result.still_deferred_cold, ("cold",))


if __name__ == "__main__":
    unittest.main()
