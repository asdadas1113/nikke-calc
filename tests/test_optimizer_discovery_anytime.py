from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer import CacheIdentity, MorisEvaluator, SearchBudget, run_anytime_search_round
from optimizer.discovery import generate_candidate_discovery_bundle


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


def legal_pair(team):
    return len(team) == 2 and len(set(team)) == 2


class DiscoveryAnytimeTests(unittest.TestCase):
    def test_non_overlap_proxy_path_is_only_coverage_then_moris_decides(self):
        scores = {
            ("A", "B"): 100,
            ("C", "B"): 140,
            ("D", "B"): 135,
            ("E", "B"): 102,
            ("F", "B"): 101,
            ("C", "D"): 250,
            ("E", "F"): 400,
        }
        evaluator = make_evaluator(scores)
        cache = {}

        def bundle(marginal):
            if "value" not in cache:
                proxy = {name: row.mean_delta for name, row in marginal.values.items()}
                cache["value"] = generate_candidate_discovery_bundle(
                    ("C", "D", "E", "F"),
                    proxy,
                    team_size=2,
                    team_count=2,
                    single_team_beam_width=6,
                    single_team_global_limit=2,
                    required_cores=(),
                    single_team_per_core_limit=0,
                    allocation_team_beam_width=6,
                    allocation_team_options_per_state=3,
                    allocation_beam_width=4,
                    allocation_limit=1,
                    legal=legal_pair,
                )
            return cache["value"]

        result = run_anytime_search_round(
            evaluator,
            budget=SearchBudget(7),
            roster=("C", "D", "E", "F"),
            reference_teams=(("A", "B"),),
            candidate_teams=(),
            candidate_builder=lambda marginal: bundle(marginal).ordinary_teams,
            protected_candidate_channel_builder=lambda marginal: bundle(marginal).protected_channels,
            positions_per_candidate=1,
            candidate_limit=1,
            team_count=2,
            legal=legal_pair,
        )

        self.assertEqual(result.proxy_selected, (("C", "D"),))
        self.assertEqual(
            result.candidate_evaluation_order,
            (("C", "D"), ("E", "F")),
        )
        self.assertIsNotNone(result.allocation)
        self.assertEqual(
            {row.members for row in result.allocation.teams},
            {("C", "D"), ("E", "F")},
        )
        self.assertEqual(result.total_score, 650.0)
        self.assertEqual(evaluator.stats.simulate_calls, 7)

        ef = next(row for row in result.evaluated_candidates if row.members == ("E", "F"))
        self.assertEqual(ef.source, "budgeted-protected-channel:1")
        self.assertEqual(ef.simulated_score, 400.0)


if __name__ == "__main__":
    unittest.main()
