from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.anytime import run_anytime_search_round
from optimizer.budget import SearchBudget
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.seeds import CoreSeed


def make_evaluator():
    scores = {
        ("X", "Y"): 100,
        ("A", "Y"): 90,
        ("B", "Y"): 90,
        ("C", "Y"): 110,
        ("D", "Y"): 110,
        # A+B is the true best team even though each member looks bad in the
        # single-character reference context. The ordinary additive proxy ranks
        # C+D above it.
        ("A", "B"): 300,
        ("C", "D"): 200,
        ("A", "C"): 150,
        ("B", "D"): 150,
    }

    def build_squad(names, characters):
        return tuple(names)

    def build_config(squad, config):
        return dict(config)

    def simulate(squad, **kwargs):
        team = tuple(squad)
        if team not in scores:
            raise AssertionError(f"unexpected synthetic simulation: {team}")
        return SimpleNamespace(squad_total=float(scores[team]))

    return MorisEvaluator(
        build_squad,
        build_config,
        simulate,
        cache_identity=CacheIdentity("engine", "seed-recall"),
    )


def legal_pair(team):
    return len(team) == 2 and len(set(team)) == 2


class SeedRecallRegressionTests(unittest.TestCase):
    def test_core_seed_recovers_pair_missed_by_individual_marginal_proxy(self):
        candidate_teams = (
            ("A", "B"),
            ("C", "D"),
            ("A", "C"),
            ("B", "D"),
        )

        plain = run_anytime_search_round(
            make_evaluator(),
            budget=SearchBudget(6),
            roster=("A", "B", "C", "D"),
            reference_teams=(("X", "Y"),),
            candidate_teams=candidate_teams,
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=5,
        )
        self.assertEqual(plain.proxy_selected, (("C", "D"),))
        self.assertEqual(plain.total_score, 200.0)
        self.assertNotIn(
            ("A", "B"),
            {item.members for item in plain.evaluated_candidates},
        )

        protected = run_anytime_search_round(
            make_evaluator(),
            budget=SearchBudget(7),
            roster=("A", "B", "C", "D"),
            reference_teams=(("X", "Y"),),
            candidate_teams=candidate_teams,
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=5,
            core_seeds=(CoreSeed(("A", "B"), source="known-interaction"),),
        )

        self.assertEqual(
            tuple(item.members for item in protected.seed_selection.candidates),
            (("A", "B"),),
        )
        self.assertEqual(
            protected.candidate_evaluation_order,
            (("A", "B"), ("C", "D")),
        )
        self.assertEqual(protected.total_score, 300.0)
        self.assertEqual(protected.allocation.teams[0].members, ("A", "B"))


if __name__ == "__main__":
    unittest.main()
