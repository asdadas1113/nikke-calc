from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer import CacheIdentity, CoreSeed, MorisEvaluator, SearchBudget, run_anytime_search_round


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


class CandidateBuilderAnytimeTests(unittest.TestCase):
    def test_builder_runs_after_marginal_and_supplies_proxy_universe(self):
        scores = {
            ("A", "B"): 100,
            ("C", "B"): 120,
            ("A", "D"): 115,
            ("C", "D"): 250,
        }
        evaluator = make_evaluator(scores)
        seen = {}

        def builder(marginal):
            seen["values"] = set(marginal.values)
            return (("C", "D"),)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(4),
            roster=("C", "D"),
            reference_teams=(("A", "B"),),
            candidate_teams=(),
            candidate_builder=builder,
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
        )

        self.assertEqual(seen["values"], {"C", "D"})
        self.assertEqual(result.proxy_selected, (("C", "D"),))
        self.assertEqual(result.total_score, 250.0)
        self.assertEqual(evaluator.stats.simulate_calls, 4)

    def test_builder_output_can_feed_core_seed_without_static_universe(self):
        scores = {
            ("A", "B"): 100,
            ("C", "B"): 120,
            ("A", "D"): 115,
            ("C", "D"): 250,
        }
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(4),
            roster=("C", "D"),
            reference_teams=(("A", "B"),),
            candidate_teams=(),
            candidate_builder=lambda marginal: (("C", "D"),),
            positions_per_candidate=1,
            candidate_limit=0,
            team_count=1,
            legal=legal_pair,
            core_seeds=(CoreSeed(("C", "D"), source="fixture"),),
            seed_roster=("C", "D"),
        )

        self.assertEqual(
            tuple(row.members for row in result.seed_selection.candidates),
            (("C", "D"),),
        )
        self.assertEqual(result.total_score, 250.0)


if __name__ == "__main__":
    unittest.main()
