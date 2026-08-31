from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.anytime import run_anytime_search_round
from optimizer.budget import SearchBudget
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.seeds import CoreSeed, ExactCompSeed


def evaluator_for(scores):
    table = {tuple(team): float(score) for team, score in scores.items()}

    def build_squad(names, characters):
        return tuple(names)

    def build_config(squad, config):
        return dict(config)

    def simulate(squad, **kwargs):
        team = tuple(squad)
        if team not in table:
            raise AssertionError(f"unexpected simulation: {team}")
        return SimpleNamespace(squad_total=table[team])

    return MorisEvaluator(
        build_squad,
        build_config,
        simulate,
        cache_identity=CacheIdentity("engine", "cold-seed"),
    )


def legal_pair(team):
    return len(team) == 2 and len(set(team)) == 2


class SeedColdBypassTests(unittest.TestCase):
    def test_exact_seed_can_use_owned_character_outside_primary_roster(self):
        evaluator = evaluator_for({("D", "E"): 175})

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(1),
            roster=("C", "D"),  # Primary-only marginal roster; E is deferred.
            reference_teams=(("A", "B"),),
            candidate_teams=(),
            positions_per_candidate=1,
            candidate_limit=0,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=0,
            exact_seeds=(ExactCompSeed(("D", "E"), source="exact"),),
            seed_roster=("C", "D", "E"),
        )

        self.assertEqual(result.marginal_stage.simulate_calls, 0)
        self.assertEqual(
            tuple(item.members for item in result.seed_selection.candidates),
            (("D", "E"),),
        )
        self.assertEqual(result.candidate_stage.simulate_calls, 1)
        self.assertEqual(result.total_score, 175.0)

    def test_core_seed_can_use_small_seed_specific_candidate_stream(self):
        evaluator = evaluator_for({("D", "E"): 180})

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(1),
            roster=("C", "D"),
            reference_teams=(("A", "B"),),
            candidate_teams=(),  # ordinary Primary universe intentionally empty
            positions_per_candidate=1,
            candidate_limit=0,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=0,
            core_seeds=(CoreSeed(("D", "E"), source="known-core"),),
            seed_roster=("C", "D", "E"),
            seed_candidate_teams=(("D", "E"),),
        )

        self.assertEqual(result.proxy_selected, ())
        self.assertEqual(
            tuple(item.members for item in result.seed_selection.candidates),
            (("D", "E"),),
        )
        self.assertEqual(result.total_score, 180.0)


if __name__ == "__main__":
    unittest.main()
