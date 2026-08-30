from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.budget import BudgetedEvaluator, SearchBudget
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.marginal import (
    measure_marginals,
    measure_marginals_with_candidates,
    measure_planned_marginals_with_candidates,
    plan_candidate_specific_marginals,
)
from optimizer.pipeline import evaluate_allocation_with_one_swap_refinement


class FakeEvaluator:
    def __init__(self, scores):
        self.scores = {tuple(team): float(score) for team, score in scores.items()}
        self.calls = []

    def evaluate(self, members, **kwargs):
        team = tuple(members)
        self.calls.append((team, dict(kwargs)))
        return SimpleNamespace(score=self.scores[team])


def make_moris_evaluator(scores):
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


class MarginalCandidateReuseTests(unittest.TestCase):
    def test_retains_references_and_all_legal_trials_as_simulated_candidates(self):
        ref = ("A", "B")
        scores = {
            ref: 100,
            ("C", "B"): 130,
            ("A", "C"): 120,
        }
        evaluator = FakeEvaluator(scores)

        result = measure_marginals_with_candidates(evaluator, ("A", "B", "C"), (ref,))

        self.assertEqual(result.values["C"].best_delta, 30)
        candidates = {row.members: row for row in result.evaluated_candidates}
        self.assertEqual(set(candidates), set(scores))
        for team, expected in scores.items():
            self.assertEqual(candidates[team].simulated_score, expected)
            self.assertEqual(candidates[team].proxy_score, expected)
        self.assertEqual(candidates[ref].source, "marginal-reference")
        self.assertEqual(candidates[("C", "B")].source, "marginal-trial")

    def test_hard_illegal_trial_is_neither_evaluated_nor_emitted(self):
        ref = ("A", "B")
        scores = {ref: 100, ("C", "B"): 130}
        evaluator = FakeEvaluator(scores)

        result = measure_marginals_with_candidates(
            evaluator,
            ("A", "B", "C"),
            (ref,),
            legal=lambda team: team != ("A", "C"),
        )

        self.assertEqual(
            {row.members for row in result.evaluated_candidates},
            {ref, ("C", "B")},
        )
        self.assertNotIn(("A", "C"), [team for team, _ in evaluator.calls])

    def test_value_only_wrapper_preserves_existing_api(self):
        ref = ("A", "B")
        scores = {ref: 100, ("C", "B"): 130, ("A", "C"): 120}
        evaluator = FakeEvaluator(scores)

        values = measure_marginals(evaluator, ("A", "B", "C"), (ref,))

        self.assertEqual(set(values), {"C"})
        self.assertEqual(values["C"].mean_delta, 30)

    def test_pipeline_reuses_same_evaluator_cache_without_new_simulate_calls(self):
        scores = {
            ("A", "B"): 100.0,
            ("C", "B"): 130.0,
            ("A", "C"): 120.0,
        }
        evaluator = make_moris_evaluator(scores)
        measured = measure_marginals_with_candidates(
            evaluator, ("A", "B", "C"), (("A", "B"),)
        )
        calls_after_marginal = evaluator.stats.simulate_calls

        result = evaluate_allocation_with_one_swap_refinement(
            evaluator,
            measured.evaluated_candidates,
            team_count=1,
            refinement_max_new=0,
        )

        self.assertEqual(evaluator.stats.simulate_calls, calls_after_marginal)
        self.assertEqual(result.candidate_stage.simulate_calls, 0)
        self.assertEqual(
            result.candidate_stage.cache_hits, len(measured.evaluated_candidates)
        )
        self.assertEqual(result.initial_total, 130.0)

    def test_duplicate_ordered_team_is_emitted_once(self):
        refs = (("A", "B"), ("A", "B"))
        scores = {("A", "B"): 100, ("C", "B"): 130, ("A", "C"): 120}
        evaluator = FakeEvaluator(scores)

        result = measure_marginals_with_candidates(evaluator, ("C",), refs)

        self.assertEqual(len(result.evaluated_candidates), 3)
        self.assertEqual(
            len({row.members for row in result.evaluated_candidates}),
            len(result.evaluated_candidates),
        )


class CandidateSpecificMarginalPlanTests(unittest.TestCase):
    def test_reference_assignment_is_load_balanced_without_scores(self):
        refs = (("A", "B"), ("C", "D"), ("E", "F"))

        plan = plan_candidate_specific_marginals(
            ("X", "Y", "Z"),
            refs,
            positions_per_candidate=2,
        )

        self.assertEqual(
            tuple(entry.reference for entry in plan.entries),
            refs,
        )
        self.assertEqual(tuple(entry.positions for entry in plan.entries), ((0, 1),) * 3)
        self.assertEqual(plan.planned_probe_count, 6)
        self.assertEqual(plan.unplanned_candidates, ())

    def test_position_priority_is_structural_callback_not_damage_oracle(self):
        ref = ("A", "B", "C")
        priority = {"A": 2, "B": 0, "C": 1}

        plan = plan_candidate_specific_marginals(
            ("X",),
            (ref,),
            positions_per_candidate=2,
            position_priority=lambda candidate, reference, index, replaced: priority[replaced],
        )

        self.assertEqual(plan.entries[0].positions, (1, 2))

    def test_hard_legality_filters_slots_before_the_cap(self):
        ref = ("A", "B", "C")

        plan = plan_candidate_specific_marginals(
            ("X",),
            (ref,),
            positions_per_candidate=2,
            legal=lambda team: team != ("X", "B", "C"),
        )

        self.assertEqual(plan.entries[0].positions, (1, 2))

    def test_budgeted_execution_round_robins_first_probe_before_second_probe(self):
        ref = ("A", "B")
        scores = {
            ref: 100,
            ("C", "B"): 130,
            ("D", "B"): 125,
            ("A", "C"): 120,
            ("A", "D"): 110,
        }
        evaluator = make_moris_evaluator(scores)
        budgeted = BudgetedEvaluator(evaluator, SearchBudget(3))
        plan = plan_candidate_specific_marginals(
            ("C", "D"),
            (ref,),
            positions_per_candidate=2,
        )

        result = measure_planned_marginals_with_candidates(budgeted, plan)

        self.assertEqual(budgeted.used_simulate_calls, 3)
        self.assertEqual(result.planned_probe_count, 4)
        self.assertEqual(result.evaluated_probe_count, 2)
        self.assertTrue(result.budget_exhausted)
        self.assertFalse(result.plan_complete)
        self.assertEqual(result.unobserved_candidates, ())
        self.assertEqual(result.values["C"].best_delta, 30)
        self.assertEqual(result.values["D"].best_delta, 25)
        self.assertNotIn(("A", "C"), {row.members for row in result.evaluated_candidates})
        self.assertNotIn(("A", "D"), {row.members for row in result.evaluated_candidates})

    def test_cached_probe_remains_usable_after_new_call_budget_is_exhausted(self):
        ref = ("A", "B")
        scores = {
            ref: 100,
            ("C", "B"): 130,
            ("D", "B"): 125,
            ("A", "C"): 140,
            ("A", "D"): 110,
        }
        evaluator = make_moris_evaluator(scores)
        evaluator.evaluate(("A", "C"))
        budgeted = BudgetedEvaluator(evaluator, SearchBudget(3))
        plan = plan_candidate_specific_marginals(
            ("C", "D"),
            (ref,),
            positions_per_candidate=2,
        )

        result = measure_planned_marginals_with_candidates(budgeted, plan)

        self.assertEqual(budgeted.used_simulate_calls, 3)
        self.assertEqual(result.evaluated_probe_count, 3)
        self.assertTrue(result.budget_exhausted)
        self.assertEqual(result.values["C"].best_delta, 40)
        self.assertIn(("A", "C"), {row.members for row in result.evaluated_candidates})


if __name__ == "__main__":
    unittest.main()
