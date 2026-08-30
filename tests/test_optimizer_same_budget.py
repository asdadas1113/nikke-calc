from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.anytime import run_anytime_search_round
from optimizer.evaluator import CacheIdentity, MorisEvaluator
from optimizer.same_budget import (
    InvalidSameBudgetComparison,
    run_same_budget_comparison,
)


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


class SameBudgetComparisonTests(unittest.TestCase):
    def test_equal_fresh_independent_runs_expose_meta_minus_pure_damage_delta(self):
        result = run_same_budget_comparison(
            make_evaluator,
            make_evaluator,
            runner(("C", "D")),
            runner(("C", "E")),
            simulate_call_budget=5,
        )

        self.assertEqual(result.identity, CacheIdentity("engine", "account"))
        self.assertEqual(result.simulate_calls, 5)
        self.assertEqual(result.pure.final_damage, 200.0)
        self.assertEqual(result.meta.final_damage, 250.0)
        self.assertEqual(result.damage_delta, 50.0)
        self.assertEqual(result.relative_damage_delta, 0.25)
        self.assertEqual(result.pure.stage_calls.total, 5)
        self.assertEqual(result.meta.stage_calls.total, 5)
        self.assertEqual(result.pure.stage_calls.marginal, 4)
        self.assertEqual(result.pure.stage_calls.candidate, 1)
        self.assertEqual(result.pure.stage_calls.refinement, 0)
        self.assertEqual(result.pure.stage_calls.unattributed, 0)

    def test_shared_evaluator_instance_is_rejected_before_search(self):
        shared = make_evaluator()
        with self.assertRaisesRegex(
            InvalidSameBudgetComparison,
            "independent evaluator",
        ):
            run_same_budget_comparison(
                lambda: shared,
                lambda: shared,
                runner(("C", "D")),
                runner(("C", "E")),
                simulate_call_budget=5,
            )

    def test_different_engine_or_account_identity_is_rejected(self):
        with self.assertRaisesRegex(
            InvalidSameBudgetComparison,
            "CacheIdentity must match",
        ):
            run_same_budget_comparison(
                make_evaluator,
                lambda: make_evaluator(account="other-account"),
                runner(("C", "D")),
                runner(("C", "E")),
                simulate_call_budget=5,
            )

    def test_warm_cache_or_prior_simulation_is_rejected(self):
        def warm_factory():
            evaluator = make_evaluator()
            evaluator.evaluate(("A", "B"))
            return evaluator

        with self.assertRaisesRegex(
            InvalidSameBudgetComparison,
            "must be fresh",
        ):
            run_same_budget_comparison(
                warm_factory,
                make_evaluator,
                runner(("C", "D")),
                runner(("C", "E")),
                simulate_call_budget=5,
            )

    def test_equal_caps_but_unequal_actual_new_calls_are_rejected(self):
        def underusing_runner(evaluator, budget):
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
            run_same_budget_comparison(
                make_evaluator,
                make_evaluator,
                underusing_runner,
                runner(("C", "E")),
                simulate_call_budget=5,
                require_complete_allocations=False,
            )

    def test_uncached_evaluators_are_rejected_because_identity_cannot_be_audited(self):
        def uncached_factory():
            def build_squad(names, characters):
                return tuple(names)

            def build_config(squad, config):
                return dict(config)

            def simulate(squad, **kwargs):
                return SimpleNamespace(squad_total=1)

            return MorisEvaluator(
                build_squad,
                build_config,
                simulate,
                use_cache=False,
            )

        with self.assertRaisesRegex(
            InvalidSameBudgetComparison,
            "identity-partitioned cache",
        ):
            run_same_budget_comparison(
                uncached_factory,
                uncached_factory,
                runner(("C", "D")),
                runner(("C", "E")),
                simulate_call_budget=5,
            )


if __name__ == "__main__":
    unittest.main()
