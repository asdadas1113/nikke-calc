from __future__ import annotations

import unittest

from optimizer.meta_usage import (
    aggregate_character_window,
    summarize_enikk_rankings,
)


NAME_MAP = {
    "Liter": "리타",
    "Crown": "크라운",
    "Alice": "앨리스",
    "Snow White": "스노우 화이트",
}


def team(*characters: str) -> dict:
    return {"characters": list(characters)}


class SeasonUsageTests(unittest.TestCase):
    def test_usage_counts_each_character_once_per_player(self):
        rankings = [
            {"teams": [team("Liter", "Crown"), team("Liter", "Alice")]},
            {"teams": [team("Crown", "Alice")]},
            {"teams": [team("Alice")]},
        ]
        snapshot = summarize_enikk_rankings(39, rankings, NAME_MAP, boss="fixture")

        self.assertEqual(snapshot.player_count, 3)
        self.assertEqual(snapshot.players_with_teams, 3)
        self.assertEqual(snapshot.player_appearances["리타"], 1)
        self.assertEqual(snapshot.player_appearances["크라운"], 2)
        self.assertEqual(snapshot.player_appearances["앨리스"], 3)
        self.assertAlmostEqual(snapshot.observe("크라운").usage_fraction or 0, 2 / 3)

    def test_unknown_external_name_is_reported_not_guessed(self):
        snapshot = summarize_enikk_rankings(
            39,
            [{"teams": [team("Future Character", "Liter")]}],
            NAME_MAP,
        )
        self.assertEqual(snapshot.unknown_external_names, ("Future Character",))
        self.assertEqual(snapshot.player_appearances["리타"], 1)

    def test_zero_is_safe_only_for_mapped_character_with_complete_rows(self):
        complete = summarize_enikk_rankings(
            39,
            [{"teams": [team("Liter")]}, {"teams": [team("Crown")]}],
            NAME_MAP,
        )
        zero = complete.observe("스노우 화이트")
        self.assertEqual(zero.player_appearances, 0)
        self.assertTrue(zero.zero_evidence_safe)
        self.assertEqual(zero.usage_fraction, 0.0)

        unknown = complete.observe("신규 미매핑")
        self.assertFalse(unknown.source_character_known)
        self.assertIsNone(unknown.usage_fraction)

        incomplete = summarize_enikk_rankings(
            39,
            [{"teams": [team("Liter")]}, {"teams": []}],
            NAME_MAP,
        )
        unsafe_zero = incomplete.observe("스노우 화이트")
        self.assertFalse(unsafe_zero.zero_evidence_safe)
        self.assertIsNone(unsafe_zero.usage_fraction)
        self.assertEqual(incomplete.incomplete_player_rows, 1)

    def test_positive_usage_survives_incomplete_row_warning(self):
        snapshot = summarize_enikk_rankings(
            39,
            [{"teams": [team("Liter")]}, {}],
            NAME_MAP,
        )
        obs = snapshot.observe("리타")
        self.assertEqual(obs.player_appearances, 1)
        self.assertEqual(obs.usage_fraction, 0.5)


class UsageWindowTests(unittest.TestCase):
    def test_window_requires_explicit_eligibility_and_includes_safe_zeroes(self):
        s37 = summarize_enikk_rankings(
            37,
            [{"teams": [team("Liter")]}, {"teams": [team("Crown")]}],
            NAME_MAP,
        )
        s38 = summarize_enikk_rankings(
            38,
            [{"teams": [team("Liter")]}, {"teams": [team("Liter")]}],
            NAME_MAP,
        )
        s39 = summarize_enikk_rankings(
            39,
            [{"teams": [team("Crown")]}, {"teams": [team("Crown")]}],
            NAME_MAP,
        )

        result = aggregate_character_window(
            "리타",
            (s37, s38, s39),
            eligible_raids=(37, 38, 39),
        )

        self.assertTrue(result.complete_for_requested_window)
        self.assertEqual(result.usable_raids, (37, 38, 39))
        self.assertEqual(result.positive_raids, (37, 38))
        self.assertEqual(result.zero_raids, (39,))
        self.assertEqual(result.usage_fractions, ((37, 0.5), (38, 1.0), (39, 0.0)))
        self.assertEqual(result.peak_usage, 1.0)
        self.assertEqual(result.median_usage, 0.5)

    def test_missing_snapshot_or_unmapped_character_stays_uncertain(self):
        s38 = summarize_enikk_rankings(
            38,
            [{"teams": [team("Liter")]}],
            {"Liter": "리타"},
        )
        result = aggregate_character_window(
            "크라운",
            (s38,),
            eligible_raids=(37, 38),
        )
        self.assertFalse(result.complete_for_requested_window)
        self.assertEqual(result.usable_raids, ())
        self.assertEqual(result.uncertain_raids, (37, 38))
        self.assertIsNone(result.peak_usage)

    def test_positive_observation_remains_usable_when_other_rows_are_incomplete(self):
        snapshot = summarize_enikk_rankings(
            39,
            [{"teams": [team("Liter")]}, {"teams": []}],
            NAME_MAP,
        )
        result = aggregate_character_window(
            "리타",
            (snapshot,),
            eligible_raids=(39,),
        )
        self.assertEqual(result.positive_raids, (39,))
        self.assertEqual(result.usage_fractions, ((39, 0.5),))
        self.assertFalse(result.uncertain_raids)

    def test_duplicate_season_snapshot_is_rejected(self):
        snapshot = summarize_enikk_rankings(39, [{"teams": [team("Liter")]}], NAME_MAP)
        with self.assertRaisesRegex(ValueError, "duplicate season"):
            aggregate_character_window(
                "리타",
                (snapshot, snapshot),
                eligible_raids=(39,),
            )


if __name__ == "__main__":
    unittest.main()
