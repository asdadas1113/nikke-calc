from __future__ import annotations

import unittest

from optimizer.candidate_generation import generate_additive_beam_candidates


class CandidateGenerationTests(unittest.TestCase):
    def test_global_beam_returns_high_additive_teams_without_simulation(self):
        scores = {"A": 10, "B": 9, "C": 8, "D": 7, "E": 6}
        result = generate_additive_beam_candidates(
            tuple(scores),
            scores,
            team_size=3,
            beam_width=6,
            global_limit=3,
        )
        self.assertEqual(result.teams[0], ("A", "B", "C"))
        self.assertEqual(result.candidates[0].proxy_score, 27.0)
        self.assertGreater(result.expanded_states, 0)

    def test_required_core_gets_its_own_candidate_channel(self):
        scores = {"A": 10, "B": 9, "C": 8, "D": 1, "E": 0}
        result = generate_additive_beam_candidates(
            tuple(scores),
            scores,
            team_size=3,
            beam_width=6,
            global_limit=1,
            required_cores=(("D", "E"),),
            per_core_limit=1,
        )
        self.assertEqual(result.teams[0], ("A", "B", "C"))
        self.assertIn(("A", "D", "E"), result.teams)
        core_row = next(row for row in result.candidates if set(row.required_members) == {"D", "E"})
        self.assertEqual(core_row.source, "additive-beam:core")

    def test_core_channel_is_discovery_only_and_does_not_bonus_proxy(self):
        scores = {"A": 10, "B": 9, "C": 8, "D": 1, "E": 0}
        result = generate_additive_beam_candidates(
            tuple(scores),
            scores,
            team_size=3,
            beam_width=6,
            global_limit=1,
            required_cores=(("D", "E"),),
            per_core_limit=1,
        )
        global_row = next(row for row in result.candidates if not row.required_members)
        core_row = next(row for row in result.candidates if row.required_members)
        self.assertEqual(global_row.proxy_score, 27.0)
        self.assertEqual(core_row.proxy_score, 11.0)
        self.assertLess(core_row.proxy_score, global_row.proxy_score)

    def test_hard_illegal_placements_are_rejected(self):
        scores = {"A": 5, "B": 4, "C": 3, "D": 2}

        def legal(team):
            return "A" not in team

        result = generate_additive_beam_candidates(
            tuple(scores),
            scores,
            team_size=2,
            beam_width=6,
            global_limit=3,
            legal=legal,
        )
        self.assertTrue(all("A" not in team for team in result.teams))
        self.assertGreater(result.rejected_illegal, 0)

    def test_placement_expander_may_emit_multiple_ordered_variants(self):
        scores = {"A": 3, "B": 2, "C": 1}

        def placements(members):
            yield members
            yield tuple(reversed(members))

        result = generate_additive_beam_candidates(
            tuple(scores),
            scores,
            team_size=2,
            beam_width=3,
            global_limit=2,
            placement_expander=placements,
        )
        self.assertEqual(result.teams[:2], (("A", "B"), ("B", "A")))

    def test_missing_proxy_score_fails_instead_of_guessing(self):
        with self.assertRaisesRegex(ValueError, "missing character proxy scores"):
            generate_additive_beam_candidates(
                ("A", "B", "C"),
                {"A": 1, "B": 1},
                team_size=2,
                beam_width=2,
                global_limit=1,
            )


if __name__ == "__main__":
    unittest.main()
