from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer import CacheIdentity, MorisEvaluator, SearchBudget
from optimizer.automatic_search import (
    AutomaticDiscoveryPolicy,
    AutomaticPlacementMode,
    run_automatic_anytime_search_round,
)


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


def policy():
    return AutomaticDiscoveryPolicy(
        team_size=2,
        single_team_beam_width=6,
        single_team_global_limit=2,
        single_team_per_core_limit=1,
        allocation_team_beam_width=6,
        allocation_team_options_per_state=3,
        allocation_beam_width=4,
        allocation_limit=1,
        placement_mode=AutomaticPlacementMode.CANONICAL_ONLY,
    )


class AutomaticSearchTests(unittest.TestCase):
    def test_automatic_discovery_recovers_non_overlap_candidate_then_moris_decides(self):
        evaluator = make_evaluator(
            {
                ("A", "B"): 100,
                ("C", "B"): 140,
                ("D", "B"): 135,
                ("E", "B"): 102,
                ("F", "B"): 101,
                ("C", "D"): 250,
                ("E", "F"): 400,
            }
        )
        result = run_automatic_anytime_search_round(
            evaluator,
            budget=SearchBudget(7),
            roster=("C", "D", "E", "F"),
            reference_teams=(("A", "B"),),
            discovery_policy=policy(),
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=2,
            legal=legal_pair,
        )

        self.assertEqual(result.search.proxy_selected, (("C", "D"),))
        self.assertEqual(
            result.search.candidate_evaluation_order,
            (("C", "D"), ("E", "F")),
        )
        self.assertEqual(result.total_score, 650.0)
        self.assertTrue(result.discovery.source_views)
        self.assertEqual(evaluator.stats.simulate_calls, 7)

    def test_insufficient_marginal_coverage_fails_instead_of_zero_filling(self):
        evaluator = make_evaluator(
            {
                ("A", "B"): 100,
                ("C", "B"): 140,
            }
        )
        with self.assertRaisesRegex(ValueError, "no proxy view covers the full discovery roster"):
            run_automatic_anytime_search_round(
                evaluator,
                budget=SearchBudget(2),
                roster=("C", "D", "E", "F"),
                reference_teams=(("A", "B"),),
                discovery_policy=policy(),
                positions_per_candidate=1,
                candidate_limit=1,
                team_count=2,
                legal=legal_pair,
                marginal_max_simulate_calls=2,
            )

    def test_policy_has_no_implicit_numeric_widths(self):
        with self.assertRaises(TypeError):
            AutomaticDiscoveryPolicy(team_size=5)  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
