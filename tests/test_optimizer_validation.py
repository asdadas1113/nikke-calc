from __future__ import annotations

import unittest

from optimizer.candidates import select_diverse
from optimizer.constraints import ConstraintSet
from optimizer.validation import (
    RankingObservation,
    analyze_fast_moris_ranking,
    enumerate_legal_teams,
    run_exhaustive_validation,
)


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


class FastMorisRankingDiagnosticsTest(unittest.TestCase):
    def test_separates_blocked_top_team_from_scored_rank_miss(self):
        observations = [
            RankingObservation(
                ("A",),
                moris_score=100,
                fast_score=90,
                groups=("weapon:AR",),
            ),
            RankingObservation(
                ("B",),
                moris_score=95,
                fast_score=None,
                blockers=("cadence:ammo_charge_flat",),
                groups=("mechanic:ammo",),
            ),
            RankingObservation(
                ("C",),
                moris_score=90,
                fast_score=95,
                unsupported=("skill_damage:complex",),
                groups=("weapon:MG",),
            ),
            RankingObservation(("D",), moris_score=80, fast_score=89),
            RankingObservation(("E",), moris_score=70, fast_score=88),
        ]

        metrics = analyze_fast_moris_ranking(
            observations,
            top_n=3,
            top_k=2,
        )

        self.assertEqual(metrics.candidate_count, 5)
        self.assertEqual(metrics.fast_scored_count, 4)
        self.assertEqual(metrics.blocked_count, 1)
        self.assertEqual(metrics.top_n_recalled, 2)
        self.assertAlmostEqual(metrics.top_n_recall, 2 / 3)
        self.assertEqual(metrics.top_n_blocked, 1)
        self.assertEqual(metrics.top_n_ranked_out, 0)
        self.assertAlmostEqual(metrics.catastrophic_false_negative_rate, 1 / 3)
        self.assertEqual(metrics.best_missed_true_rank, 2)
        self.assertEqual(metrics.best_missed_team, ("B",))
        self.assertEqual(metrics.comparable_pairs, 6)
        self.assertAlmostEqual(metrics.pairwise_accuracy, 5 / 6)
        self.assertEqual(
            metrics.blocker_counts,
            (("cadence:ammo_charge_flat", 1),),
        )
        self.assertEqual(
            metrics.unsupported_counts,
            (("skill_damage:complex", 1),),
        )

        by_group = {row.group: row for row in metrics.groups}
        self.assertEqual(by_group["mechanic:ammo"].blocked_count, 1)
        self.assertEqual(by_group["mechanic:ammo"].top_n_count, 1)
        self.assertEqual(by_group["mechanic:ammo"].top_n_recall, 0.0)
        # C is third by Moris but first by Fast among supported rows: negative
        # percentile error means this group is being promoted, not suppressed.
        self.assertLess(
            by_group["weapon:MG"].mean_rank_percentile_error,
            0.0,
        )

    def test_scored_top_n_miss_is_not_misclassified_as_blocked(self):
        metrics = analyze_fast_moris_ranking(
            [
                RankingObservation(("A",), 100, 100),
                RankingObservation(("B",), 90, 1),
                RankingObservation(("C",), 80, 99),
            ],
            top_n=2,
            top_k=2,
        )

        self.assertEqual(metrics.top_n_recalled, 1)
        self.assertEqual(metrics.top_n_blocked, 0)
        self.assertEqual(metrics.top_n_ranked_out, 1)
        self.assertEqual(metrics.best_missed_true_rank, 2)
        self.assertEqual(metrics.best_missed_team, ("B",))

    def test_fast_pairwise_tie_gets_half_credit_and_moris_tie_is_ignored(self):
        metrics = analyze_fast_moris_ranking(
            [
                RankingObservation(("A",), 100, 50),
                RankingObservation(("B",), 90, 50),
                RankingObservation(("C",), 90, 40),
            ],
            top_n=2,
            top_k=2,
        )

        # A/B is comparable and tied by Fast => 0.5; A/C is concordant => 1.0;
        # B/C is a Moris tie and contributes no pair.
        self.assertEqual(metrics.comparable_pairs, 2)
        self.assertAlmostEqual(metrics.pairwise_accuracy, 0.75)

    def test_duplicate_candidate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate ranking candidate"):
            analyze_fast_moris_ranking(
                [
                    RankingObservation(("A",), 10, 9),
                    RankingObservation(("A",), 8, 7),
                ],
                top_n=1,
                top_k=1,
            )


if __name__ == "__main__":
    unittest.main()
