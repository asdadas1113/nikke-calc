from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.anytime import run_anytime_search_round
from optimizer.budget import SearchBudget
from optimizer.evaluator import CacheIdentity, MorisEvaluator


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


class AnytimeSearchTests(unittest.TestCase):
    def test_partial_marginal_budget_never_overruns_or_invents_values(self):
        scores = {
            ("A", "B"): 100,
            ("C", "D"): 90,
            ("A", "D"): 80,
        }
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(3),
            roster=("A", "B", "C", "D"),
            reference_teams=(("A", "B"), ("C", "D")),
            candidate_teams=(("A", "C"), ("B", "D")),
            positions_per_candidate=1,
            candidate_limit=2,
            team_count=1,
            legal=legal_pair,
        )

        self.assertEqual(result.budget_used, 3)
        self.assertEqual(result.budget_remaining, 0)
        self.assertEqual(evaluator.stats.simulate_calls, 3)
        self.assertTrue(result.marginal_measurement.budget_exhausted)
        self.assertEqual(set(result.marginal_measurement.values), {"A"})
        self.assertEqual(
            set(result.marginal_measurement.unobserved_candidates),
            {"B", "C", "D"},
        )
        self.assertEqual(result.proxy_selected, ())

    def test_marginal_stage_cap_reserves_parent_budget_for_candidate_evaluation(self):
        scores = {
            ("A", "B"): 100,
            ("C", "D"): 90,
            ("A", "D"): 80,
            ("C", "B"): 85,
            ("A", "C"): 200,
        }
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(5),
            roster=("A", "C", "B", "D"),
            reference_teams=(("A", "B"), ("C", "D")),
            candidate_teams=(("A", "C"),),
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=4,
        )

        self.assertEqual(result.marginal_stage.simulate_calls, 4)
        self.assertEqual(result.candidate_stage.simulate_calls, 1)
        self.assertEqual(result.budget_used, 5)
        self.assertEqual(result.proxy_selected, (("A", "C"),))
        self.assertEqual(result.total_score, 200.0)
        self.assertTrue(result.marginal_measurement.budget_exhausted)

    def test_multi_view_union_keeps_first_view_and_adds_deeper_view_candidate(self):
        scores = {
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
        )

        self.assertEqual(result.marginal_stage.simulate_calls, 7)
        self.assertEqual(result.proxy_selected, (("C", "D"), ("C", "E")))
        self.assertEqual(result.candidate_stage.simulate_calls, 2)
        self.assertEqual(result.total_score, 200.0)
        sources = {
            item.members: item.source
            for item in result.evaluated_candidates
            if item.members in {("C", "D"), ("C", "E")}
        }
        self.assertEqual(
            sources[("C", "D")],
            "budgeted-proxy-views:marginal-prefix-1",
        )
        self.assertEqual(
            sources[("C", "E")],
            "budgeted-proxy-views:marginal-prefix-2",
        )

    def test_multi_view_candidate_union_still_obeys_whole_search_budget(self):
        scores = {
            ("A", "B"): 100,
            ("C", "B"): 110,
            ("A", "C"): 105,
            ("D", "B"): 109,
            ("A", "D"): 105,
            ("E", "B"): 101,
            ("A", "E"): 120,
            ("C", "D"): 150,
        }
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(8),
            roster=("C", "D", "E"),
            reference_teams=(("A", "B"),),
            candidate_teams=(("C", "D"), ("C", "E"), ("D", "E")),
            positions_per_candidate=2,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
            marginal_max_simulate_calls=7,
            proxy_view_limit_per_view=1,
        )

        self.assertEqual(result.budget_used, 8)
        self.assertEqual(result.budget_remaining, 0)
        self.assertEqual(evaluator.stats.simulate_calls, 8)
        self.assertEqual(result.candidate_stage.attempted_teams, 2)
        self.assertEqual(result.candidate_stage.evaluated_teams, 1)
        self.assertEqual(result.candidate_stage.simulate_calls, 1)
        self.assertEqual(result.total_score, 150.0)

    def test_continuation_reuses_cache_keeps_prior_and_can_improve(self):
        scores = {
            ("A", "B"): 100,
            ("C", "D"): 95,
            ("A", "D"): 90,
            ("B", "D"): 85,
            ("C", "B"): 80,
            ("D", "B"): 75,
            ("A", "C"): 200,
        }
        evaluator = make_evaluator(scores)

        first = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(6),
            roster=("A", "B", "C", "D"),
            reference_teams=(("A", "B"), ("C", "D")),
            candidate_teams=(),
            positions_per_candidate=1,
            candidate_limit=0,
            team_count=1,
            legal=legal_pair,
        )
        self.assertEqual(first.budget_used, 6)
        self.assertEqual(first.total_score, 100.0)
        calls_after_first = evaluator.stats.simulate_calls

        second = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(1),
            roster=("A", "B", "C", "D"),
            reference_teams=(("A", "B"), ("C", "D")),
            candidate_teams=(("A", "C"),),
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=1,
            legal=legal_pair,
            prior_candidates=first.evaluated_candidates,
            marginal_max_simulate_calls=0,
            proxy_view_limit_per_view=1,
        )

        self.assertEqual(second.budget_used, 1)
        self.assertEqual(evaluator.stats.simulate_calls, calls_after_first + 1)
        self.assertEqual(second.marginal_stage.simulate_calls, 0)
        self.assertEqual(second.total_score, 200.0)
        self.assertGreaterEqual(second.total_score or 0, first.total_score or 0)
        second_keys = {item.members for item in second.evaluated_candidates}
        self.assertTrue(
            {item.members for item in first.evaluated_candidates}.issubset(second_keys)
        )

    def test_refinement_uses_remaining_budget_and_reallocates(self):
        scores = {
            ("A", "B"): 100,
            ("C", "B"): 90,
            ("A", "C"): 150,
        }
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(3),
            roster=("A", "B", "C"),
            reference_teams=(("A", "B"),),
            candidate_teams=(),
            positions_per_candidate=1,
            candidate_limit=0,
            team_count=1,
            legal=legal_pair,
            refinement_incoming=("C",),
            refinement_max_new=10,
        )

        self.assertEqual(result.budget_used, 3)
        self.assertEqual(result.marginal_stage.simulate_calls, 2)
        self.assertEqual(result.refinement_stage.simulate_calls, 1)
        self.assertEqual(result.allocation_before_refine.total_score, 100.0)
        self.assertEqual(result.total_score, 150.0)
        self.assertIn(
            ("A", "C"),
            {item.members for item in result.evaluated_candidates},
        )

    def test_global_allocation_is_exact_within_retained_candidate_pool(self):
        scores = {
            ("A", "B"): 100,
            ("C", "D"): 99,
            ("A", "D"): 120,
            ("B", "D"): 10,
            ("C", "B"): 10,
            ("D", "B"): 10,
        }
        evaluator = make_evaluator(scores)

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(6),
            roster=("A", "B", "C", "D"),
            reference_teams=(("A", "B"), ("C", "D")),
            candidate_teams=(),
            positions_per_candidate=1,
            candidate_limit=0,
            team_count=2,
            legal=legal_pair,
        )

        self.assertIsNotNone(result.allocation)
        chosen = {item.members for item in result.allocation.teams}
        # The strongest single team A,D cannot coexist with either complementary
        # probe in this fixture, so exact set-packing keeps A,B + C,D = 199.
        self.assertEqual(chosen, {("A", "B"), ("C", "D")})
        self.assertEqual(result.total_score, 199.0)

    def test_rejects_negative_optional_stage_limits(self):
        evaluator = make_evaluator({("A", "B"): 100})
        common = dict(
            evaluator=evaluator,
            budget=SearchBudget(0),
            roster=(),
            reference_teams=(("A", "B"),),
            candidate_teams=(),
            positions_per_candidate=1,
            candidate_limit=0,
            team_count=1,
            legal=legal_pair,
        )
        with self.assertRaises(ValueError):
            run_anytime_search_round(
                **common,
                marginal_max_simulate_calls=-1,
            )
        with self.assertRaises(ValueError):
            run_anytime_search_round(
                **common,
                proxy_view_limit_per_view=-1,
            )


if __name__ == "__main__":
    unittest.main()
