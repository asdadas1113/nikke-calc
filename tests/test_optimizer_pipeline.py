from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.candidates import CandidateTeam
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.pipeline import evaluate_allocation_with_one_swap_refinement


SCORES = {
    ("A", "B"): 100.0,
    ("C", "D"): 90.0,
    ("A", "C"): 95.0,
    ("B", "D"): 80.0,
    ("A", "E"): 120.0,
    ("C", "E"): 10.0,
}


def evaluator() -> MorisEvaluator:
    def build_squad(names, characters):
        return tuple(names)

    def build_config(squad, config):
        return dict(config)

    def simulate(squad, **kwargs):
        return SimpleNamespace(squad_total=SCORES.get(tuple(squad), -1000.0))

    return MorisEvaluator(
        build_squad,
        build_config,
        simulate,
        cache_identity=CacheIdentity("engine", "account"),
    )


def candidates() -> list[CandidateTeam]:
    return [
        CandidateTeam(("A", "B"), proxy_score=1.0, simulated_score=9999.0),
        CandidateTeam(("C", "D"), proxy_score=0.9, simulated_score=9999.0),
        CandidateTeam(("A", "C"), proxy_score=0.8, simulated_score=9999.0),
        CandidateTeam(("B", "D"), proxy_score=0.7, simulated_score=9999.0),
    ]


class AllocationRefinementPipelineTests(unittest.TestCase):
    def test_rebuilds_scores_then_refines_current_allocation(self):
        ev = evaluator()
        result = evaluate_allocation_with_one_swap_refinement(
            ev,
            candidates(),
            team_count=2,
            refinement_incoming=("E",),
            refinement_positions=(1,),
            refinement_max_new=2,
        )

        self.assertEqual(result.initial_total, 190.0)
        self.assertEqual(result.refined_total, 210.0)
        self.assertEqual(result.refine_gain, 20.0)
        self.assertAlmostEqual(result.refine_gain_pct, 20.0 / 190.0 * 100.0)
        self.assertEqual(result.candidate_stage.simulate_calls, 4)
        self.assertEqual(result.refinement_stage.simulate_calls, 2)
        self.assertEqual(
            [row.members for row in result.refinement_neighbors],
            [("A", "E"), ("C", "E")],
        )
        self.assertEqual(
            {row.members for row in result.refined_allocation.teams},
            {("A", "E"), ("C", "D")},
        )
        self.assertEqual(
            next(row for row in result.initial_candidates if row.members == ("A", "B")).score,
            100.0,
        )

    def test_positive_refine_budget_requires_explicit_incoming_order(self):
        with self.assertRaisesRegex(ValueError, "refinement_incoming must be explicit"):
            evaluate_allocation_with_one_swap_refinement(
                evaluator(), candidates(), team_count=2, refinement_max_new=1
            )

    def test_duplicate_ordered_initial_team_is_rejected(self):
        pool = candidates()
        pool.append(CandidateTeam(("A", "B"), proxy_score=0.0))
        with self.assertRaisesRegex(ValueError, "ordered teams must be unique"):
            evaluate_allocation_with_one_swap_refinement(
                evaluator(), pool, team_count=2
            )

    def test_hard_illegal_initial_team_is_rejected_before_simulation(self):
        ev = evaluator()
        with self.assertRaisesRegex(ValueError, "hard-illegal"):
            evaluate_allocation_with_one_swap_refinement(
                ev,
                candidates(),
                team_count=2,
                legal=lambda team: team != ("A", "B"),
            )
        self.assertEqual(ev.stats.simulate_calls, 0)

    def test_insufficient_pool_returns_without_refinement(self):
        ev = evaluator()
        result = evaluate_allocation_with_one_swap_refinement(
            ev,
            [CandidateTeam(("A", "B"), proxy_score=1.0)],
            team_count=2,
            refinement_incoming=("E",),
            refinement_max_new=2,
        )
        self.assertIsNone(result.initial_allocation)
        self.assertIsNone(result.refined_allocation)
        self.assertFalse(result.refinement_neighbors)
        self.assertEqual(result.candidate_stage.simulate_calls, 1)
        self.assertEqual(result.refinement_stage.simulate_calls, 0)


if __name__ == "__main__":
    unittest.main()
