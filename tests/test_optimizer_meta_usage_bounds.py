from __future__ import annotations

import unittest

from optimizer.meta_usage_bounds import (
    RankingCoverageContract,
    aggregate_bounded_character_window,
    certify_enikk_rankings,
)


NAME_MAP = {
    "Liter": "리타",
    "Crown": "크라운",
    "Alice": "앨리스",
    "Snow White": "스노우 화이트",
    "A": "A",
    "B": "B",
    "C": "C",
    "D": "D",
    "E": "E",
}


def contract(*, ranks: int = 2) -> RankingCoverageContract:
    return RankingCoverageContract(
        servers=("GLOBAL", "JP"),
        rank_start=1,
        rank_end=ranks,
        team_count=1,
        team_size=5,
        source="fixture",
    )


def row(server: str, rank: int, player: str, chars=("Liter", "Crown", "Alice", "A", "B")):
    return {
        "server": server,
        "rank": rank,
        "playerid": player,
        "teams": [{"characters": list(chars)}],
    }


class RankingCoverageContractTests(unittest.TestCase):
    def test_expected_player_slots_are_server_rank_product(self):
        self.assertEqual(contract(ranks=3).expected_player_slots, 6)

    def test_duplicate_servers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            RankingCoverageContract(
                servers=("GLOBAL", "GLOBAL"),
                rank_start=1,
                rank_end=50,
                team_count=5,
                team_size=5,
                source="fixture",
            )


class CertifiedUsageTests(unittest.TestCase):
    def test_complete_contract_produces_exact_bounds(self):
        snapshot = certify_enikk_rankings(
            39,
            (
                row("GLOBAL", 1, "g1"),
                row("GLOBAL", 2, "g2"),
                row("JP", 1, "j1", ("Crown", "Alice", "A", "B", "C")),
                row("JP", 2, "j2", ("Crown", "Alice", "A", "B", "C")),
            ),
            NAME_MAP,
            contract=contract(),
        )
        obs = snapshot.observe("리타")
        self.assertTrue(snapshot.fully_complete)
        self.assertEqual(snapshot.uncertain_player_slots, 0)
        self.assertEqual(obs.lower_fraction, 0.5)
        self.assertEqual(obs.upper_fraction, 0.5)

    def test_missing_slot_increases_upper_bound_without_zero_filling(self):
        snapshot = certify_enikk_rankings(
            39,
            (
                row("GLOBAL", 1, "g1", ("Crown", "Alice", "A", "B", "C")),
                row("GLOBAL", 2, "g2", ("Crown", "Alice", "A", "B", "C")),
                row("JP", 1, "j1", ("Crown", "Alice", "A", "B", "C")),
            ),
            NAME_MAP,
            contract=contract(),
        )
        obs = snapshot.observe("리타")
        self.assertEqual(snapshot.missing_player_slots, 1)
        self.assertEqual(obs.lower_fraction, 0.0)
        self.assertEqual(obs.upper_fraction, 0.25)

    def test_malformed_present_slot_is_uncertainty_not_zero(self):
        broken = row("JP", 2, "j2")
        broken["teams"] = [{"characters": ["Liter"]}]
        snapshot = certify_enikk_rankings(
            39,
            (
                row("GLOBAL", 1, "g1", ("Crown", "Alice", "A", "B", "C")),
                row("GLOBAL", 2, "g2", ("Crown", "Alice", "A", "B", "C")),
                row("JP", 1, "j1", ("Crown", "Alice", "A", "B", "C")),
                broken,
            ),
            NAME_MAP,
            contract=contract(),
        )
        self.assertEqual(snapshot.missing_player_slots, 0)
        self.assertEqual(snapshot.malformed_player_slots, 1)
        self.assertEqual(snapshot.observe("리타").upper_fraction, 0.25)

    def test_unknown_external_mapping_makes_that_player_adversarial(self):
        unknown = row("JP", 2, "j2", ("Mystery", "Crown", "Alice", "A", "B"))
        snapshot = certify_enikk_rankings(
            39,
            (
                row("GLOBAL", 1, "g1", ("Crown", "Alice", "A", "B", "C")),
                row("GLOBAL", 2, "g2", ("Crown", "Alice", "A", "B", "C")),
                row("JP", 1, "j1", ("Crown", "Alice", "A", "B", "C")),
                unknown,
            ),
            NAME_MAP,
            contract=contract(),
        )
        self.assertEqual(snapshot.mapping_uncertain_player_slots, 1)
        self.assertEqual(snapshot.unknown_external_names, ("Mystery",))
        self.assertEqual(snapshot.observe("리타").upper_fraction, 0.25)

    def test_unmapped_target_never_gets_bounds(self):
        snapshot = certify_enikk_rankings(
            39,
            (row("GLOBAL", 1, "g1"),),
            {"Liter": "리타"},
            contract=contract(),
        )
        obs = snapshot.observe("크라운")
        self.assertIsNone(obs.lower_fraction)
        self.assertIsNone(obs.upper_fraction)

    def test_duplicate_server_rank_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate server/rank"):
            certify_enikk_rankings(
                39,
                (row("GLOBAL", 1, "p1"), row("GLOBAL", 1, "p2")),
                NAME_MAP,
                contract=contract(),
            )

    def test_duplicate_player_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate playerid"):
            certify_enikk_rankings(
                39,
                (row("GLOBAL", 1, "same"), row("GLOBAL", 2, "same")),
                NAME_MAP,
                contract=contract(),
            )

    def test_row_outside_contract_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside coverage contract"):
            certify_enikk_rankings(
                39,
                (row("SEA", 1, "p1"),),
                NAME_MAP,
                contract=contract(),
            )

    def test_character_reuse_across_teams_is_malformed(self):
        full_contract = RankingCoverageContract(
            servers=("GLOBAL",),
            rank_start=1,
            rank_end=1,
            team_count=2,
            team_size=2,
            source="fixture",
        )
        snapshot = certify_enikk_rankings(
            39,
            ({
                "server": "GLOBAL",
                "rank": 1,
                "playerid": "p",
                "teams": [
                    {"characters": ["A", "B"]},
                    {"characters": ["A", "C"]},
                ],
            },),
            NAME_MAP,
            contract=full_contract,
        )
        self.assertEqual(snapshot.malformed_player_slots, 1)
        self.assertEqual(snapshot.uncertain_player_slots, 1)


class BoundedWindowTests(unittest.TestCase):
    def test_peak_upper_uses_worst_requested_season(self):
        c = RankingCoverageContract(
            servers=("GLOBAL",),
            rank_start=1,
            rank_end=4,
            team_count=1,
            team_size=5,
            source="fixture",
        )
        s38 = certify_enikk_rankings(
            38,
            tuple(
                row("GLOBAL", rank, f"38-{rank}", ("Crown", "Alice", "A", "B", "C"))
                for rank in range(1, 5)
            ),
            NAME_MAP,
            contract=c,
        )
        s39 = certify_enikk_rankings(
            39,
            tuple(
                row("GLOBAL", rank, f"39-{rank}", ("Crown", "Alice", "A", "B", "C"))
                for rank in range(1, 4)
            ),
            NAME_MAP,
            contract=c,
        )
        window = aggregate_bounded_character_window(
            "리타",
            (s38, s39),
            eligible_raids=(38, 39),
        )
        self.assertTrue(window.complete_for_requested_window)
        self.assertEqual(window.peak_lower_usage, 0.0)
        self.assertEqual(window.peak_upper_usage, 0.25)
        self.assertEqual(window.bounds, ((38, 0.0, 0.0), (39, 0.0, 0.25)))

    def test_missing_snapshot_or_target_mapping_is_uncertain(self):
        snapshot = certify_enikk_rankings(
            39,
            (row("GLOBAL", 1, "g1"),),
            {"Liter": "리타"},
            contract=contract(),
        )
        window = aggregate_bounded_character_window(
            "크라운",
            (snapshot,),
            eligible_raids=(38, 39),
        )
        self.assertFalse(window.complete_for_requested_window)
        self.assertEqual(window.uncertain_raids, (38, 39))
        self.assertIsNone(window.peak_upper_usage)


if __name__ == "__main__":
    unittest.main()
