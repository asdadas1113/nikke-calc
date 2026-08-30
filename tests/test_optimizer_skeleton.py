from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.candidates import CandidateTeam, select_diverse
from optimizer.constraints import ConstraintSet, teams_are_disjoint
from optimizer.evaluator import MorisEvaluator
from optimizer.global_search import select_global_allocation


class EvaluatorTest(unittest.TestCase):
    def test_expected_mode_verbose_false_and_exact_cache(self):
        calls = []

        def build_squad(names, overrides):
            calls.append(("squad", tuple(names), overrides))
            return list(names)

        def build_config(squad, config):
            calls.append(("config", tuple(squad), dict(config)))
            return dict(config)

        def simulate(squad, *, config, enemy, seed, verbose):
            calls.append(("simulate", tuple(squad), dict(config), seed, verbose))
            return SimpleNamespace(squad_total=123.0)

        evaluator = MorisEvaluator(build_squad, build_config, simulate)
        first = evaluator.evaluate(("A", "B"), config={"duration": 10})
        second = evaluator.evaluate(("A", "B"), config={"duration": 10})

        self.assertEqual(first.score, 123.0)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(evaluator.stats.simulate_calls, 1)
        sim_call = next(row for row in calls if row[0] == "simulate")
        self.assertEqual(sim_call[2]["rng_mode"], "expected")
        self.assertTrue(sim_call[2]["immune_blocks_burst"])
        self.assertFalse(sim_call[4])


class ConstraintTest(unittest.TestCase):
    def test_include_exclude_and_global_disjointness(self):
        constraints = ConstraintSet(
            team_size=3,
            include=frozenset({"A"}),
            exclude=frozenset({"X"}),
        )
        self.assertTrue(constraints.validate_team(("A", "B", "C")))
        self.assertFalse(constraints.validate_team(("A", "B", "X")))
        self.assertFalse(constraints.validate_team(("A", "A", "C")))
        self.assertTrue(teams_are_disjoint((("A", "B"), ("C", "D"))))
        self.assertFalse(teams_are_disjoint((("A", "B"), ("B", "C"))))


class GlobalSearchTest(unittest.TestCase):
    def test_global_allocation_beats_sequential_greedy_trap(self):
        # Greedy starts with AB=100 and can only add EF=1 => 101.
        # Global allocation chooses AC=60 + BD=60 => 120.
        candidates = [
            CandidateTeam(("A", "B"), 100, 100, "synthetic"),
            CandidateTeam(("A", "C"), 60, 60, "synthetic"),
            CandidateTeam(("B", "D"), 60, 60, "synthetic"),
            CandidateTeam(("E", "F"), 1, 1, "synthetic"),
        ]
        result = select_global_allocation(candidates, team_count=2)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.total_score, 120)
        self.assertEqual(
            {team.members for team in result.teams},
            {("A", "C"), ("B", "D")},
        )

    def test_unevaluated_candidates_are_excluded_by_default(self):
        candidates = [
            CandidateTeam(("A",), 999),
            CandidateTeam(("B",), 10, 10),
        ]
        self.assertIsNone(select_global_allocation(candidates, team_count=2))


class DiversityTest(unittest.TestCase):
    def test_diverse_selection_keeps_limit_and_top_candidate(self):
        candidates = [
            CandidateTeam(("A", "B", "C"), 100),
            CandidateTeam(("A", "B", "D"), 99),
            CandidateTeam(("E", "F", "G"), 95),
        ]
        selected = select_diverse(candidates, 2, similarity_penalty=2.0)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0].proxy_score, 100)
        self.assertIn(("E", "F", "G"), {item.members for item in selected})


if __name__ == "__main__":
    unittest.main()
