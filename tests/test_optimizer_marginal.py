from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.marginal import measure_marginals, measure_marginals_with_candidates
from optimizer.pipeline import evaluate_allocation_with_one_swap_refinement


class FakeEvaluator:
    def __init__(self, scores):
        self.scores = {tuple(team): float(score) for team, score in scores.items()}
        self.calls = []

    def evaluate(self, members, **kwargs):
        team = tuple(members)
        self.calls.append((team, dict(kwargs)))
        return SimpleNamespace(score=self.scores[team])


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

        def build_squad(names, characters):
            return tuple(names)

        def build_config(squad, config):
            return dict(config)

        def simulate(squad, **kwargs):
            return SimpleNamespace(squad_total=scores[tuple(squad)])

        evaluator = MorisEvaluator(
            build_squad,
            build_config,
            simulate,
            cache_identity=CacheIdentity("engine", "account"),
        )
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


if __name__ == "__main__":
    unittest.main()
