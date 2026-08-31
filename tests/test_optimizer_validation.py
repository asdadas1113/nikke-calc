from __future__ import annotations

import unittest

from optimizer.candidates import select_diverse
from optimizer.constraints import ConstraintSet
from optimizer.validation import enumerate_legal_teams, run_exhaustive_validation


class ExhaustiveValidationTest(unittest.TestCase):
    def test_ordered_enumeration_keeps_placement_variants_distinct(self):
        teams = enumerate_legal_teams(
            ("A", "B", "C"),
            ConstraintSet(team_size=2),
        )
        self.assertEqual(len(teams), 6)
        self.assertIn(("A", "B"), teams)
        self.assertIn(("B", "A"), teams)

    def test_diverse_proxy_pool_preserves_global_optimum_in_small_fixture(self):
        # AB is the strongest single team, but locking it first is globally bad:
        # AC + BD = 184 beats AB + any disjoint fallback (= at most 120 here).
        roster = tuple("ABCDEFGH")
        legal = enumerate_legal_teams(
            roster,
            ConstraintSet(team_size=2),
            ordered=False,
        )

        true_scores = {
            ("A", "B"): 100,
            ("A", "C"): 92,
            ("B", "D"): 92,
            ("E", "F"): 20,
            ("G", "H"): 20,
            ("C", "D"): 5,
        }
        proxy_scores = {
            ("A", "B"): 100,
            ("A", "C"): 95,
            ("A", "D"): 94,
            ("A", "E"): 93,
            ("A", "F"): 92,
            ("B", "D"): 90,
            ("E", "F"): 40,
            ("G", "H"): 39,
        }

        def canonical(team):
            return tuple(sorted(team))

        def true_score(team):
            return true_scores.get(canonical(team), 1)

        def proxy_score(team):
            return proxy_scores.get(canonical(team), 0)

        metrics = run_exhaustive_validation(
            legal,
            true_score=true_score,
            proxy_score=proxy_score,
            select_candidates=lambda candidates: select_diverse(
                candidates,
                6,
                similarity_penalty=0.5,
            ),
            team_count=2,
            top_n=5,
        )

        self.assertEqual(metrics.legal_team_count, 28)
        self.assertEqual(metrics.candidate_count, 6)
        self.assertEqual(metrics.exhaustive_evaluator_calls, 28)
        self.assertEqual(metrics.optimizer_evaluator_calls, 6)
        self.assertEqual(metrics.exhaustive_optimum, 184)
        self.assertEqual(metrics.final_score, 184)
        self.assertEqual(metrics.true_optimum_survival, 1.0)
        self.assertEqual(metrics.top_n_recall, 0.6)
        self.assertEqual(metrics.final_to_optimum, 1.0)
        self.assertGreaterEqual(metrics.exhaustive_runtime_s, 0.0)
        self.assertGreaterEqual(metrics.optimizer_runtime_s, 0.0)

    def test_selector_cannot_smuggle_in_non_legal_team(self):
        legal = [("A", "B"), ("C", "D")]

        with self.assertRaisesRegex(ValueError, "outside legal space"):
            run_exhaustive_validation(
                legal,
                true_score=lambda team: 1,
                proxy_score=lambda team: 1,
                select_candidates=lambda candidates: [
                    *candidates,
                    type(candidates[0])(("X", "Y"), 999),
                ],
                team_count=2,
                top_n=1,
            )


if __name__ == "__main__":
    unittest.main()
