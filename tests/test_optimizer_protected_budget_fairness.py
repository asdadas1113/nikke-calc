from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

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


class ProtectedBudgetFairnessTests(unittest.TestCase):
    def test_two_remaining_calls_cover_one_protected_and_one_proxy_candidate(self):
        # One baseline + four first-slot probes consume five calls. Only two new
        # Moris calls remain for candidate evaluation.
        evaluator = make_evaluator(
            {
                ("A", "B"): 100,
                ("C", "B"): 140,
                ("D", "B"): 130,
                ("E", "B"): 120,
                ("F", "B"): 110,
                ("C", "D"): 210,  # protected rank 1
                ("C", "E"): 220,  # ordinary proxy
                # These must not consume the second call before the proxy.
                ("E", "F"): 205,
                ("D", "E"): 200,
            }
        )
        fake_discovery = SimpleNamespace(
            ordinary_teams=(("C", "E"),),
            protected_teams=(("C", "D"), ("E", "F"), ("D", "E")),
        )
        policy = AutomaticDiscoveryPolicy(
            team_size=2,
            single_team_beam_width=2,
            single_team_global_limit=1,
            single_team_per_core_limit=0,
            allocation_team_beam_width=2,
            allocation_team_options_per_state=1,
            allocation_beam_width=1,
            allocation_limit=1,
            placement_mode=AutomaticPlacementMode.CANONICAL_ONLY,
        )

        with patch(
            "optimizer.automatic_search.generate_multi_view_candidate_discovery",
            return_value=fake_discovery,
        ):
            result = run_automatic_anytime_search_round(
                evaluator,
                budget=SearchBudget(7),
                roster=("C", "D", "E", "F"),
                reference_teams=(("A", "B"),),
                discovery_policy=policy,
                positions_per_candidate=1,
                candidate_limit=1,
                team_count=2,
                legal=legal_pair,
            )

        evaluated = {
            row.members
            for row in result.search.evaluated_candidates
            if row.simulated_score is not None
        }
        self.assertIn(("C", "D"), evaluated)
        self.assertIn(("C", "E"), evaluated)
        self.assertNotIn(("E", "F"), evaluated)
        self.assertEqual(result.search.candidate_stage.simulate_calls, 2)
        self.assertEqual(evaluator.stats.simulate_calls, 7)


if __name__ == "__main__":
    unittest.main()
