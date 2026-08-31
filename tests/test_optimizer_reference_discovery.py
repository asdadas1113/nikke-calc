from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer import CacheIdentity, MorisEvaluator, SearchBudget
from optimizer.reference_discovery import (
    ReferenceComposition,
    balanced_placement_order,
    discover_reference_placements,
    ensure_marginal_reference_coverage,
)


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


class ReferenceDiscoveryTests(unittest.TestCase):
    def test_first_n_balanced_placements_cover_every_member_slot_once(self):
        members = ("A", "B", "C", "D", "E")
        order = balanced_placement_order(members)
        self.assertEqual(len(order), 120)

        counts = {(name, slot): 0 for name in members for slot in range(len(members))}
        for team in order[: len(members)]:
            for slot, name in enumerate(team):
                counts[(name, slot)] += 1
        self.assertEqual(set(counts.values()), {1})

    def test_unknown_order_uses_actual_moris_to_choose_reference(self):
        evaluator = make_evaluator({("A", "B"): 10, ("B", "A"): 100})
        result = discover_reference_placements(
            evaluator,
            (ReferenceComposition(("A", "B"), source="external", order_known=False),),
            budget=SearchBudget(2),
            max_per_composition=2,
        )

        self.assertEqual(result.selected_references, (("B", "A"),))
        self.assertEqual(result.simulate_calls, 2)
        self.assertEqual([row.score for row in result.evaluated], [10.0, 100.0])

    def test_tight_budget_round_robins_sources_before_second_placement(self):
        evaluator = make_evaluator(
            {
                ("A", "B"): 10,
                ("B", "A"): 100,
                ("C", "D"): 50,
                ("D", "C"): 60,
            }
        )
        result = discover_reference_placements(
            evaluator,
            (
                ReferenceComposition(("A", "B"), source="one"),
                ReferenceComposition(("C", "D"), source="two"),
            ),
            budget=SearchBudget(2),
            max_per_composition=2,
        )

        self.assertEqual(
            [row.members for row in result.evaluated],
            [("A", "B"), ("C", "D")],
        )
        self.assertEqual(result.selected_references, (("A", "B"), ("C", "D")))
        self.assertEqual(result.unfulfilled_sources, ())

    def test_budget_too_small_for_one_look_per_source_fails_before_simulation(self):
        evaluator = make_evaluator({("A", "B"): 10, ("C", "D"): 50})
        with self.assertRaisesRegex(ValueError, "cannot give every viable composition one placement"):
            discover_reference_placements(
                evaluator,
                (
                    ReferenceComposition(("A", "B"), source="one", order_known=True),
                    ReferenceComposition(("C", "D"), source="two", order_known=True),
                ),
                budget=SearchBudget(1),
                max_per_composition=1,
            )
        self.assertEqual(evaluator.stats.simulate_calls, 0)

    def test_cached_first_placement_does_not_consume_fairness_budget(self):
        evaluator = make_evaluator({("A", "B"): 10, ("C", "D"): 50})
        evaluator.evaluate(("A", "B"))
        before = evaluator.stats.simulate_calls
        result = discover_reference_placements(
            evaluator,
            (
                ReferenceComposition(("A", "B"), source="one", order_known=True),
                ReferenceComposition(("C", "D"), source="two", order_known=True),
            ),
            budget=SearchBudget(1),
            max_per_composition=1,
        )
        self.assertEqual(result.unfulfilled_sources, ())
        self.assertEqual(result.simulate_calls, 1)
        self.assertEqual(evaluator.stats.simulate_calls - before, 1)


    @staticmethod
    def _three_stage_legal(team):
        members = set(team)
        return (
            bool(members & {"A", "D"})
            and bool(members & {"B", "E"})
            and bool(members & {"C", "F"})
        )

    def test_score_blind_coverage_repairs_single_reference_members(self):
        roster = ("A", "B", "C", "D", "E", "F", "G", "H")
        refs, added = ensure_marginal_reference_coverage(
            roster,
            (("A", "B", "C", "G"),),
            positions_per_candidate=1,
            team_size=4,
            legal=self._three_stage_legal,
            beam_width=32,
            candidates_per_rotation=8,
            max_rotations=6,
        )
        self.assertGreaterEqual(len(added), 1)
        self.assertEqual(set(added[0]), {"D", "E", "F", "H"})

        from optimizer.marginal import plan_candidate_specific_marginals

        plan = plan_candidate_specific_marginals(
            roster, refs, positions_per_candidate=1, legal=self._three_stage_legal
        )
        self.assertEqual(plan.unplanned_candidates, ())

    def test_zero_reference_case_builds_diverse_coverage_instead_of_shared_core_loop(self):
        roster = ("A", "B", "C", "D", "E", "F", "G", "H")
        refs, added = ensure_marginal_reference_coverage(
            roster,
            (),
            positions_per_candidate=1,
            team_size=4,
            legal=self._three_stage_legal,
            beam_width=32,
            candidates_per_rotation=8,
            max_rotations=8,
        )
        self.assertGreaterEqual(len(added), 2)
        self.assertEqual(refs, added)
        self.assertLess(
            max(len(set(left) & set(right)) for left in refs for right in refs if left != right),
            3,
        )

        from optimizer.marginal import plan_candidate_specific_marginals

        plan = plan_candidate_specific_marginals(
            roster, refs, positions_per_candidate=1, legal=self._three_stage_legal
        )
        self.assertEqual(plan.unplanned_candidates, ())

    def test_impossible_full_roster_reference_coverage_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "cannot construct bounded score-blind"):
            ensure_marginal_reference_coverage(
                ("A", "B", "C"),
                (("A", "B", "C"),),
                positions_per_candidate=1,
                team_size=3,
                legal=self._three_stage_legal,
                beam_width=8,
                candidates_per_rotation=4,
                max_rotations=3,
            )

    def test_known_order_never_invents_permutations(self):
        evaluator = make_evaluator({("A", "B"): 10})
        result = discover_reference_placements(
            evaluator,
            (ReferenceComposition(("A", "B"), source="ordered", order_known=True),),
            budget=SearchBudget(5),
            max_per_composition=5,
        )
        self.assertEqual([row.members for row in result.evaluated], [("A", "B")])
        self.assertEqual(result.simulate_calls, 1)


if __name__ == "__main__":
    unittest.main()
