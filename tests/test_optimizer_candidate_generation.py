from __future__ import annotations

import unittest

from optimizer.candidate_generation import (
    all_permutation_placements,
    generate_additive_allocation_beam_candidates,
    generate_additive_beam_candidates,
)


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

    def test_placement_variants_are_interleaved_across_memberships(self):
        scores = {"A": 3, "B": 2, "C": 1}

        def placements(members):
            yield members
            yield tuple(reversed(members))

        result = generate_additive_beam_candidates(
            tuple(scores),
            scores,
            team_size=2,
            beam_width=3,
            global_limit=3,
            placement_expander=placements,
        )
        # AB/BA must not monopolize the output before AC receives a first look.
        self.assertEqual(result.teams[:2], (("A", "B"), ("A", "C")))
        self.assertIn(("B", "A"), result.teams)

    def test_single_team_top_k_can_lack_full_non_overlap_supply(self):
        scores = {name: 10 - i for i, name in enumerate("ABCDEFGHIJ")}
        result = generate_additive_beam_candidates(
            tuple(scores),
            scores,
            team_size=2,
            beam_width=10,
            global_limit=10,
        )
        covered = {name for team in result.teams for name in team}
        self.assertNotIn("J", covered)

    def test_allocation_beam_protects_a_complete_disjoint_path(self):
        scores = {name: 10 - i for i, name in enumerate("ABCDEFGHIJ")}
        result = generate_additive_allocation_beam_candidates(
            tuple(scores),
            scores,
            team_size=2,
            team_count=5,
            team_beam_width=10,
            team_options_per_state=3,
            allocation_beam_width=6,
            allocation_limit=2,
        )

        self.assertTrue(result.allocations)
        best = result.allocations[0]
        self.assertEqual(len(best.teams), 5)
        flattened = [name for team in best.teams for name in team]
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertEqual(set(flattened), set(scores))
        self.assertEqual(best.proxy_total, sum(scores.values()))
        candidate_memberships = {frozenset(team) for team in result.teams}
        self.assertTrue(all(frozenset(team) in candidate_memberships for team in best.teams))

    def test_allocation_beam_never_adds_a_diversity_bonus(self):
        scores = {name: 6 - i for i, name in enumerate("ABCDEF")}
        result = generate_additive_allocation_beam_candidates(
            tuple(scores),
            scores,
            team_size=2,
            team_count=3,
            team_beam_width=6,
            team_options_per_state=3,
            allocation_beam_width=4,
            allocation_limit=1,
        )
        allocation = result.allocations[0]
        self.assertEqual(
            allocation.proxy_total,
            sum(scores[name] for team in allocation.teams for name in team),
        )

    def test_allocation_membership_width_is_not_consumed_by_order_permutations(self):
        scores = {"A": 4, "B": 3, "C": 2, "D": 1}
        result = generate_additive_allocation_beam_candidates(
            tuple(scores),
            scores,
            team_size=2,
            team_count=2,
            team_beam_width=6,
            team_options_per_state=2,
            allocation_beam_width=3,
            allocation_limit=1,
            placement_expander=all_permutation_placements,
        )

        self.assertEqual(len(result.allocations[0].teams), 2)
        self.assertEqual(len(result.candidate_channels), 2)
        self.assertTrue(all(len(channel) == 2 for channel in result.candidate_channels))
        # First placement of each membership is emitted before either membership's
        # second permutation.
        first_memberships = [frozenset(team) for team in result.teams[:2]]
        self.assertEqual(len(set(first_memberships)), 2)

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
