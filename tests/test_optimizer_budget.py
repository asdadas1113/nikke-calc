from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.budget import BudgetedEvaluator, SearchBudget, SearchBudgetExhausted
from optimizer.candidates import CandidateTeam
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.pipeline import evaluate_allocation_with_one_swap_refinement


def make_evaluator(scores):
    table = {tuple(team): float(score) for team, score in scores.items()}

    def build_squad(names, characters):
        return tuple(names)

    def build_config(squad, config):
        return dict(config)

    def simulate(squad, **kwargs):
        return SimpleNamespace(squad_total=table[tuple(squad)])

    return MorisEvaluator(
        build_squad,
        build_config,
        simulate,
        cache_identity=CacheIdentity("engine", "account"),
    )


class SearchBudgetTests(unittest.TestCase):
    def test_rejects_negative_budget(self):
        with self.assertRaises(ValueError):
            SearchBudget(-1)

    def test_counts_actual_simulate_calls_and_allows_cache_hits_after_exhaustion(self):
        evaluator = make_evaluator({("A",): 10, ("B",): 20, ("C",): 30})
        budgeted = BudgetedEvaluator(evaluator, SearchBudget(2))

        budgeted.evaluate(("A",))
        budgeted.evaluate(("B",))

        self.assertEqual(budgeted.used_simulate_calls, 2)
        self.assertEqual(budgeted.remaining_simulate_calls, 0)
        self.assertTrue(budgeted.exhausted)
        self.assertTrue(budgeted.can_evaluate(("A",)))
        self.assertFalse(budgeted.can_evaluate(("C",)))

        cached = budgeted.evaluate(("A",))
        self.assertTrue(cached.cache_hit)
        self.assertEqual(evaluator.stats.simulate_calls, 2)

        with self.assertRaises(SearchBudgetExhausted):
            budgeted.evaluate(("C",))
        self.assertEqual(evaluator.stats.simulate_calls, 2)

    def test_zero_new_call_budget_can_reuse_cache_created_before_session(self):
        evaluator = make_evaluator({("A",): 10})
        evaluator.evaluate(("A",))
        budgeted = BudgetedEvaluator(evaluator, SearchBudget(0))

        result = budgeted.evaluate(("A",))

        self.assertTrue(result.cache_hit)
        self.assertEqual(budgeted.used_simulate_calls, 0)
        self.assertEqual(budgeted.remaining_simulate_calls, 0)

    def test_nested_stage_budget_reserves_parent_budget_for_later_stages(self):
        evaluator = make_evaluator({("A",): 10, ("B",): 20, ("C",): 30})
        whole_search = BudgetedEvaluator(evaluator, SearchBudget(3))
        stage = BudgetedEvaluator(whole_search, SearchBudget(1))

        stage.evaluate(("A",))
        cached = stage.evaluate(("A",))
        self.assertTrue(cached.cache_hit)
        self.assertEqual(stage.used_simulate_calls, 1)
        self.assertEqual(whole_search.used_simulate_calls, 1)

        with self.assertRaises(SearchBudgetExhausted):
            stage.evaluate(("B",))

        # The stage cap is exhausted, but the parent still has two calls left.
        whole_search.evaluate(("B",))
        whole_search.evaluate(("C",))
        self.assertEqual(whole_search.used_simulate_calls, 3)
        self.assertEqual(whole_search.remaining_simulate_calls, 0)

    def test_parent_budget_still_blocks_nested_stage(self):
        evaluator = make_evaluator({("A",): 10})
        whole_search = BudgetedEvaluator(evaluator, SearchBudget(0))
        stage = BudgetedEvaluator(whole_search, SearchBudget(5))

        self.assertFalse(stage.can_evaluate(("A",)))
        with self.assertRaises(SearchBudgetExhausted):
            stage.evaluate(("A",))
        self.assertEqual(evaluator.stats.simulate_calls, 0)

    def test_cache_preflight_matches_evaluate_defaults_and_inputs(self):
        evaluator = make_evaluator({("A",): 10})
        evaluator.evaluate(("A",), config={"duration": 30}, enemy={"def": 123})

        self.assertTrue(
            evaluator.is_cached(("A",), config={"duration": 30}, enemy={"def": 123})
        )
        self.assertFalse(
            evaluator.is_cached(("A",), config={"duration": 60}, enemy={"def": 123})
        )

    def test_existing_pipeline_can_use_budgeted_evaluator_without_rework(self):
        scores = {("A", "B"): 100, ("C", "D"): 90}
        evaluator = make_evaluator(scores)
        evaluator.evaluate(("A", "B"))
        evaluator.evaluate(("C", "D"))
        budgeted = BudgetedEvaluator(evaluator, SearchBudget(0))
        candidates = [
            CandidateTeam(("A", "B"), proxy_score=100, simulated_score=100),
            CandidateTeam(("C", "D"), proxy_score=90, simulated_score=90),
        ]

        result = evaluate_allocation_with_one_swap_refinement(
            budgeted,
            candidates,
            team_count=2,
            refinement_max_new=0,
        )

        self.assertEqual(budgeted.used_simulate_calls, 0)
        self.assertEqual(result.candidate_stage.simulate_calls, 0)
        self.assertEqual(result.candidate_stage.cache_hits, 2)
        self.assertEqual(result.initial_total, 190.0)


if __name__ == "__main__":
    unittest.main()
