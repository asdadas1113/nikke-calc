from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.budget import BudgetedEvaluator, SearchBudget
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.marginal import (
    measure_planned_marginals_with_candidates,
    plan_candidate_specific_marginals,
)
from optimizer.priority import reorder_candidate_marginal_plan


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


class MarginalPriorityTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan_candidate_specific_marginals(
            ("A", "B", "C", "D"),
            (("A", "B"), ("C", "D")),
            positions_per_candidate=1,
        )

    def test_reorders_only_execution_not_context_or_slots(self):
        original = {entry.candidate: entry for entry in self.plan.entries}

        reordered = reorder_candidate_marginal_plan(self.plan, ("D", "A"))

        self.assertEqual(
            tuple(entry.candidate for entry in reordered.entries),
            ("D", "A", "B", "C"),
        )
        self.assertEqual(reordered.reference_teams, self.plan.reference_teams)
        self.assertEqual(reordered.unplanned_candidates, self.plan.unplanned_candidates)
        for entry in reordered.entries:
            self.assertEqual(entry.reference, original[entry.candidate].reference)
            self.assertEqual(entry.positions, original[entry.candidate].positions)

    def test_low_budget_observes_prioritized_candidates_first(self):
        reordered = reorder_candidate_marginal_plan(self.plan, ("D", "A"))
        evaluator = make_evaluator(
            {
                ("A", "B"): 100,
                ("C", "D"): 90,
                ("D", "B"): 80,
                ("A", "D"): 70,
                ("B", "D"): 60,
                ("C", "B"): 50,
            }
        )
        budgeted = BudgetedEvaluator(evaluator, SearchBudget(4))

        result = measure_planned_marginals_with_candidates(budgeted, reordered)

        self.assertEqual(set(result.values), {"D", "A"})
        self.assertEqual(result.unobserved_candidates, ("B", "C"))
        self.assertTrue(result.budget_exhausted)
        self.assertEqual(budgeted.used_simulate_calls, 4)

    def test_rejects_duplicate_or_unknown_priority_names(self):
        with self.assertRaises(ValueError):
            reorder_candidate_marginal_plan(self.plan, ("A", "A"))
        with self.assertRaises(ValueError):
            reorder_candidate_marginal_plan(self.plan, ("Z",))


if __name__ == "__main__":
    unittest.main()
