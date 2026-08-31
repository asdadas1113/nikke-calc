from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from optimizer import CacheIdentity, CandidateTeam, MorisEvaluator
from optimizer.automatic_search import AutomaticPlacementMode


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tests" / "benchmark_optimizer_common_marginal_policy_sweep_worker.py"
SPEC = importlib.util.spec_from_file_location(
    "benchmark_optimizer_common_marginal_policy_sweep_worker",
    RUNNER_PATH,
)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


class AlwaysLegal:
    def __call__(self, team):
        return True

    def can_complete(self, partial, available, *, team_size):
        return True


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


def policy():
    return SimpleNamespace(
        team_size=2,
        single_team_beam_width=4,
        single_team_global_limit=4,
        single_team_per_core_limit=0,
        allocation_team_beam_width=4,
        allocation_team_options_per_state=2,
        allocation_beam_width=2,
        allocation_limit=1,
        placement_mode=AutomaticPlacementMode.CANONICAL_ONLY,
    )


def measurement(*rows):
    return SimpleNamespace(evaluated_candidates=tuple(rows))


class CommonMarginalPolicySweepTests(unittest.TestCase):
    def test_interleave_is_rank_round_robin_and_deduplicates(self):
        result = RUNNER._interleave_team_channels(
            (("A",), ("B",), ("C",)),
            (("D",), ("B",), ("E",)),
        )
        self.assertEqual(
            result,
            (("A",), ("D",), ("B",), ("C",), ("E",)),
        )

    def test_common_candidate_map_requires_actual_moris_scores(self):
        good = CandidateTeam(("A", "B"), 1.0, 100.0, "shared")
        mapped = RUNNER._common_candidate_map(measurement(good))
        self.assertEqual(mapped[("A", "B")].simulated_score, 100.0)

        bad = CandidateTeam(("C", "D"), 1.0, None, "proxy-only")
        with self.assertRaisesRegex(ValueError, "lacks actual Moris score"):
            RUNNER._common_candidate_map(measurement(bad))

    def test_policy_evaluator_must_start_fresh(self):
        evaluator = make_evaluator({("X", "Y"): 1.0})
        evaluator.evaluate(("X", "Y"))
        with self.assertRaisesRegex(ValueError, "fresh empty cache"):
            RUNNER.run_policy_after_common_marginal(
                evaluator,
                name="warm",
                policy=policy(),
                roster=("A", "B", "C", "D", "E", "F"),
                plan=SimpleNamespace(),
                measurement=measurement(
                    CandidateTeam(("A", "B"), 0.0, 100.0, "shared")
                ),
                candidate_call_budget=1,
                proxy_view_limit_per_view=1,
                team_count=1,
                legal=AlwaysLegal(),
                evaluate_kwargs={},
            )

    def test_shared_marginal_rows_are_free_and_only_new_candidates_count(self):
        evaluator = make_evaluator(
            {
                ("E", "F"): 120.0,
                ("A", "C"): 150.0,
            }
        )
        shared = measurement(
            CandidateTeam(("A", "B"), 0.0, 100.0, "shared"),
            CandidateTeam(("C", "D"), 0.0, 90.0, "shared"),
        )
        fake_discovery = SimpleNamespace(
            ordinary_teams=(("A", "C"),),
            protected_teams=(("E", "F"),),
            bundles=(
                (
                    "first",
                    SimpleNamespace(
                        ordinary=SimpleNamespace(expanded_states=7),
                        allocation=SimpleNamespace(expanded_states=11),
                    ),
                ),
            ),
        )
        proxy_rows = (SimpleNamespace(members=("A", "C")),)

        with patch.object(
            RUNNER,
            "build_planned_marginal_prefix_views",
            return_value=(SimpleNamespace(name="first"),),
        ), patch.object(
            RUNNER,
            "generate_multi_view_candidate_discovery",
            return_value=fake_discovery,
        ), patch.object(
            RUNNER,
            "select_proxy_view_candidates",
            return_value=proxy_rows,
        ):
            result = RUNNER.run_policy_after_common_marginal(
                evaluator,
                name="fixture",
                policy=policy(),
                roster=("A", "B", "C", "D", "E", "F"),
                plan=SimpleNamespace(),
                measurement=shared,
                candidate_call_budget=2,
                proxy_view_limit_per_view=1,
                team_count=2,
                legal=AlwaysLegal(),
                evaluate_kwargs={},
            )

        self.assertEqual(evaluator.stats.simulate_calls, 2)
        self.assertEqual(result.candidate_simulate_calls, 2)
        self.assertEqual(result.evaluated_candidate_count, 4)
        self.assertEqual(result.cheap_expanded_states, 18)
        self.assertEqual(result.final_damage, 270.0)
        self.assertEqual(
            {team for team, _score in result.allocation},
            {("A", "C"), ("E", "F")},
        )

    def test_policy_must_be_able_to_spend_full_candidate_budget(self):
        evaluator = make_evaluator({("E", "F"): 120.0})
        shared = measurement(
            CandidateTeam(("A", "B"), 0.0, 100.0, "shared"),
            CandidateTeam(("C", "D"), 0.0, 90.0, "shared"),
        )
        fake_discovery = SimpleNamespace(
            ordinary_teams=(),
            protected_teams=(("E", "F"),),
            bundles=(
                (
                    "first",
                    SimpleNamespace(
                        ordinary=SimpleNamespace(expanded_states=1),
                        allocation=SimpleNamespace(expanded_states=1),
                    ),
                ),
            ),
        )

        with patch.object(
            RUNNER,
            "build_planned_marginal_prefix_views",
            return_value=(SimpleNamespace(name="first"),),
        ), patch.object(
            RUNNER,
            "generate_multi_view_candidate_discovery",
            return_value=fake_discovery,
        ), patch.object(
            RUNNER,
            "select_proxy_view_candidates",
            return_value=(),
        ):
            with self.assertRaisesRegex(ValueError, "could spend only 1/2"):
                RUNNER.run_policy_after_common_marginal(
                    evaluator,
                    name="too-small",
                    policy=policy(),
                    roster=("A", "B", "C", "D", "E", "F"),
                    plan=SimpleNamespace(),
                    measurement=shared,
                    candidate_call_budget=2,
                    proxy_view_limit_per_view=1,
                    team_count=2,
                    legal=AlwaysLegal(),
                    evaluate_kwargs={},
                )

    def test_complete_allocation_is_required_even_when_budget_matches(self):
        evaluator = make_evaluator({("A", "C"): 150.0})
        shared = measurement(
            CandidateTeam(("A", "B"), 0.0, 100.0, "shared"),
        )
        fake_discovery = SimpleNamespace(
            ordinary_teams=(("A", "C"),),
            protected_teams=(),
            bundles=(
                (
                    "first",
                    SimpleNamespace(
                        ordinary=SimpleNamespace(expanded_states=1),
                        allocation=SimpleNamespace(expanded_states=1),
                    ),
                ),
            ),
        )

        with patch.object(
            RUNNER,
            "build_planned_marginal_prefix_views",
            return_value=(SimpleNamespace(name="first"),),
        ), patch.object(
            RUNNER,
            "generate_multi_view_candidate_discovery",
            return_value=fake_discovery,
        ), patch.object(
            RUNNER,
            "select_proxy_view_candidates",
            return_value=(SimpleNamespace(members=("A", "C")),),
        ):
            with self.assertRaisesRegex(ValueError, "complete 2-team allocation"):
                RUNNER.run_policy_after_common_marginal(
                    evaluator,
                    name="incomplete",
                    policy=policy(),
                    roster=("A", "B", "C"),
                    plan=SimpleNamespace(),
                    measurement=shared,
                    candidate_call_budget=1,
                    proxy_view_limit_per_view=1,
                    team_count=2,
                    legal=AlwaysLegal(),
                    evaluate_kwargs={},
                )


if __name__ == "__main__":
    unittest.main()
