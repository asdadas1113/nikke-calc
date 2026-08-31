from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.anytime import run_anytime_search_round
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.policy_sweep import run_equal_budget_policy_sweep
from optimizer.same_budget import InvalidSameBudgetComparison


SCORES = {
    ("A", "B"): 100,
    ("C", "B"): 110,
    ("D", "B"): 105,
    ("E", "B"): 115,
    ("C", "D"): 200,
    ("C", "E"): 250,
}


def make_evaluator(*, account: str = "account") -> MorisEvaluator:
    def build_squad(names, characters):
        return tuple(names)

    def build_config(squad, config):
        return dict(config)

    def simulate(squad, **kwargs):
        team = tuple(squad)
        if team not in SCORES:
            raise AssertionError(f"unexpected synthetic simulation: {team}")
        return SimpleNamespace(squad_total=SCORES[team])

    return MorisEvaluator(
        build_squad,
        build_config,
        simulate,
        cache_identity=CacheIdentity("engine", account),
    )


def runner(candidate_team):
    def run(evaluator, budget):
        return run_anytime_search_round(
            evaluator,
            budget=budget,
            roster=("C", "D", "E"),
            reference_teams=(("A", "B"),),
            candidate_teams=(candidate_team,),
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=1,
            legal=lambda team: len(team) == 2 and len(set(team)) == 2,
        )

    return run


class PolicySweepTests(unittest.TestCase):
    def test_multiple_variants_share_identity_and_actual_call_count(self):
        result = run_equal_budget_policy_sweep(
            make_evaluator,
            {
                "narrow": runner(("C", "D")),
                "wide": runner(("C", "E")),
            },
            simulate_call_budget=5,
        )

        self.assertEqual(result.identity, CacheIdentity("engine", "account"))
        self.assertEqual(result.simulate_calls, 5)
        rows = result.by_name()
        self.assertEqual(rows["narrow"].final_damage, 200.0)
        self.assertEqual(rows["wide"].final_damage, 250.0)
        self.assertEqual(rows["narrow"].simulate_calls, rows["wide"].simulate_calls)

    def test_equal_caps_but_different_actual_calls_are_rejected(self):
        def underusing(evaluator, budget):
            return run_anytime_search_round(
                evaluator,
                budget=budget,
                roster=("C", "D", "E"),
                reference_teams=(("A", "B"),),
                candidate_teams=(),
                positions_per_candidate=1,
                candidate_limit=0,
                team_count=1,
                legal=lambda team: len(team) == 2 and len(set(team)) == 2,
            )

        with self.assertRaisesRegex(
            InvalidSameBudgetComparison,
            "different numbers of new Moris",
        ):
            run_equal_budget_policy_sweep(
                make_evaluator,
                {
                    "under": underusing,
                    "full": runner(("C", "E")),
                },
                simulate_call_budget=5,
                require_complete_allocations=False,
            )

    def test_sweep_requires_more_than_one_policy(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            run_equal_budget_policy_sweep(
                make_evaluator,
                {"only": runner(("C", "D"))},
                simulate_call_budget=5,
            )


if __name__ == "__main__":
    unittest.main()
