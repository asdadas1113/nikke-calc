from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer import CacheIdentity, MorisEvaluator, SearchBudget, run_anytime_search_round


def make_evaluator(scores):
    table = {tuple(team): float(score) for team, score in scores.items()}

    def build_squad(names, characters):
        return tuple(names)

    def build_config(squad, config):
        return dict(config)

    def simulate(squad, **kwargs):
        team = tuple(squad)
        if team not in table:
            raise AssertionError(f"unexpected synthetic simulation: {team}")
        return SimpleNamespace(squad_total=table[team])

    return MorisEvaluator(
        build_squad,
        build_config,
        simulate,
        cache_identity=CacheIdentity("engine", "account"),
    )


def legal_pair(team):
    return len(team) == 2 and len(set(team)) == 2


class ProtectedCandidateChannelTests(unittest.TestCase):
    def test_low_proxy_protected_team_still_receives_actual_moris_evaluation(self):
        scores = {
            ("A", "B"): 100,
            ("C", "B"): 140,
            ("D", "B"): 135,
            ("E", "B"): 102,
            ("F", "B"): 101,
            ("C", "D"): 250,
            ("E", "F"): 400,
        }
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(7),
            roster=("C", "D", "E", "F"),
            reference_teams=(("A", "B"),),
            candidate_teams=(("C", "D"), ("E", "F")),
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
            protected_candidate_channel_builder=lambda marginal: ((("E", "F"),),),
        )

        self.assertEqual(result.proxy_selected, (("C", "D"),))
        self.assertEqual(
            result.candidate_evaluation_order,
            (("E", "F"), ("C", "D")),
        )
        self.assertEqual(result.total_score, 400.0)
        protected = next(row for row in result.evaluated_candidates if row.members == ("E", "F"))
        self.assertEqual(protected.source, "budgeted-protected-channel:0")
        self.assertEqual(protected.simulated_score, 400.0)

    def test_multiple_protected_channels_are_rank_round_robin(self):
        scores = {
            ("A", "B"): 100,
            ("C", "B"): 120,
            ("D", "B"): 119,
            ("E", "B"): 118,
            ("F", "B"): 117,
            ("C", "D"): 210,
            ("E", "F"): 205,
            ("C", "E"): 200,
        }
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(8),
            roster=("C", "D", "E", "F"),
            reference_teams=(("A", "B"),),
            candidate_teams=(("C", "E"),),
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
            protected_candidate_channel_builder=lambda marginal: (
                (("C", "D"),),
                (("E", "F"),),
            ),
        )

        self.assertEqual(
            result.candidate_evaluation_order,
            (("C", "D"), ("E", "F"), ("C", "E")),
        )

    def test_protected_channel_cannot_assign_fake_zero_to_unobserved_member(self):
        scores = {
            ("A", "B"): 100,
            ("C", "B"): 120,
        }
        evaluator = make_evaluator(scores)

        with self.assertRaisesRegex(ValueError, "without marginal evidence"):
            run_anytime_search_round(
                evaluator,
                budget=SearchBudget(2),
                roster=("C",),
                reference_teams=(("A", "B"),),
                candidate_teams=(),
                positions_per_candidate=1,
                candidate_limit=0,
                team_count=1,
                legal=legal_pair,
                protected_candidate_channel_builder=lambda marginal: ((("C", "D"),),),
            )


if __name__ == "__main__":
    unittest.main()
