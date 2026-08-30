from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.anytime import run_anytime_search_round
from optimizer.budget import SearchBudget
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.seeds import CoreSeed, ExactCompSeed


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
        cache_identity=CacheIdentity("engine", "seed-account"),
    )


def legal_pair(team):
    return len(team) == 2 and len(set(team)) == 2


MARGINAL_SCORES = {
    ("A", "B"): 100,
    ("C", "B"): 110,
    ("A", "C"): 105,
    ("D", "B"): 109,
    ("A", "D"): 105,
    ("E", "B"): 101,
    ("A", "E"): 120,
    ("C", "D"): 150,
    ("C", "E"): 200,
}


class AnytimeSeedTests(unittest.TestCase):
    def test_exact_seed_and_proxy_candidates_are_rank_interleaved(self):
        scores = {**MARGINAL_SCORES, ("D", "E"): 175}
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(9),
            roster=("C", "D", "E"),
            reference_teams=(("A", "B"),),
            candidate_teams=(("C", "D"), ("C", "E"), ("D", "E")),
            positions_per_candidate=2,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=7,
            proxy_view_limit_per_view=1,
            exact_seeds=(ExactCompSeed(("D", "E"), source="ranking"),),
        )

        self.assertEqual(result.marginal_stage.simulate_calls, 7)
        self.assertEqual(result.proxy_selected, (("C", "D"), ("C", "E")))
        self.assertEqual(
            tuple(item.members for item in result.seed_selection.candidates),
            (("D", "E"),),
        )
        self.assertEqual(
            result.candidate_evaluation_order,
            (("D", "E"), ("C", "D"), ("C", "E")),
        )
        # Only two new calls remain: one protected seed and one proxy candidate
        # get a real look instead of one source consuming both calls first.
        self.assertEqual(result.candidate_stage.simulate_calls, 2)
        evaluated = {item.members for item in result.evaluated_candidates}
        self.assertIn(("D", "E"), evaluated)
        self.assertIn(("C", "D"), evaluated)
        self.assertNotIn(("C", "E"), evaluated)

    def test_seed_receives_no_strength_bonus_and_can_lose_normally(self):
        scores = {**MARGINAL_SCORES, ("D", "E"): 50}
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(10),
            roster=("C", "D", "E"),
            reference_teams=(("A", "B"),),
            candidate_teams=(("C", "D"), ("C", "E"), ("D", "E")),
            positions_per_candidate=2,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=7,
            proxy_view_limit_per_view=1,
            exact_seeds=(ExactCompSeed(("D", "E"), source="ranking"),),
        )

        seeded = next(
            item for item in result.evaluated_candidates if item.members == ("D", "E")
        )
        self.assertEqual(seeded.proxy_score, 0.0)
        self.assertEqual(seeded.simulated_score, 50.0)
        self.assertEqual(result.total_score, 200.0)
        self.assertEqual(result.allocation.teams[0].members, ("C", "E"))

    def test_core_seed_reuses_candidate_universe_without_inventing_team(self):
        scores = {**MARGINAL_SCORES, ("D", "E"): 175}
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(8),
            roster=("C", "D", "E"),
            reference_teams=(("A", "B"),),
            candidate_teams=(("C", "D"), ("D", "E")),
            positions_per_candidate=2,
            candidate_limit=0,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=7,
            core_seeds=(CoreSeed(("D", "E"), source="known-core"),),
        )

        self.assertEqual(
            tuple(item.members for item in result.seed_selection.candidates),
            (("D", "E"),),
        )
        self.assertEqual(result.candidate_stage.simulate_calls, 1)
        self.assertEqual(result.total_score, 175.0)

    def test_core_seed_missing_from_candidate_universe_is_diagnostic_only(self):
        evaluator = make_evaluator(MARGINAL_SCORES)
        seed = CoreSeed(("D", "E"), source="known-core")

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(7),
            roster=("C", "D", "E"),
            reference_teams=(("A", "B"),),
            candidate_teams=(("C", "D"),),
            positions_per_candidate=2,
            candidate_limit=0,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=7,
            core_seeds=(seed,),
        )

        self.assertEqual(result.seed_selection.candidates, ())
        self.assertEqual(result.seed_selection.unfulfilled_cores, (seed,))
        self.assertEqual(result.candidate_stage.simulate_calls, 0)


if __name__ == "__main__":
    unittest.main()
