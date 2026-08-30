from __future__ import annotations

import unittest

from optimizer.candidates import CandidateTeam
from optimizer.marginal import (
    CandidateMarginalPlan,
    CandidateMarginalPlanEntry,
    MarginalMeasurement,
)
from optimizer.proxy_views import (
    ProxyView,
    build_planned_marginal_prefix_views,
    select_proxy_view_candidates,
)


class ProxyViewCandidateTests(unittest.TestCase):
    def test_union_preserves_team_lost_by_another_view(self):
        teams = (("A", "B"), ("A", "C"), ("B", "C"), ("C", "D"))
        views = (
            ProxyView("first", {"A": 10, "B": 9, "C": 1, "D": 0}),
            ProxyView("deeper", {"A": 1, "B": 0, "C": 9, "D": 10}),
        )

        selected = select_proxy_view_candidates(teams, views, limit_per_view=1)

        self.assertEqual(
            tuple(item.members for item in selected),
            (("A", "B"), ("C", "D")),
        )
        self.assertEqual(selected[0].source_views, ("first",))
        self.assertEqual(selected[1].source_views, ("deeper",))

    def test_same_team_records_every_selecting_view_without_duplicate_candidate(self):
        teams = (("A", "B"), ("A", "C"), ("B", "C"))
        views = (
            ProxyView("one", {"A": 10, "B": 9, "C": 1}),
            ProxyView("two", {"A": 8, "B": 7, "C": 0}),
        )

        selected = select_proxy_view_candidates(teams, views, limit_per_view=1)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].members, ("A", "B"))
        self.assertEqual(selected[0].source_views, ("one", "two"))
        self.assertEqual(tuple(hit.rank for hit in selected[0].hits), (1, 1))

    def test_scans_one_shot_stream_once_and_union_is_bounded(self):
        iterations = 0

        def stream():
            nonlocal iterations
            iterations += 1
            if iterations > 1:
                raise AssertionError("candidate stream was iterated twice")
            yield from (("A", "B"), ("A", "C"), ("B", "C"), ("C", "D"))

        views = (
            ProxyView("one", {"A": 4, "B": 3, "C": 2, "D": 1}),
            ProxyView("two", {"A": 1, "B": 2, "C": 3, "D": 4}),
            ProxyView("three", {"A": 0, "B": 5, "C": 5, "D": 0}),
        )

        selected = select_proxy_view_candidates(stream(), views, limit_per_view=2)

        self.assertEqual(iterations, 1)
        self.assertLessEqual(len(selected), 6)

    def test_missing_values_illegal_teams_and_exact_ties_are_deterministic(self):
        teams = (("A", "B"), ("A", "C"), ("B", "C"), ("A", "D"))
        view = ProxyView("view", {"A": 1, "B": 1, "C": 1})

        selected = select_proxy_view_candidates(
            teams,
            (view,),
            limit_per_view=2,
            legal=lambda team: team != ("A", "C"),
        )

        # A/B and B/C tie at 2. A/B appeared earlier and remains rank 1.
        self.assertEqual(
            tuple(item.members for item in selected),
            (("A", "B"), ("B", "C")),
        )
        self.assertEqual(tuple(item.hits[0].rank for item in selected), (1, 2))

    def test_prefix_views_keep_first_interpretation_when_second_probe_changes_it(self):
        plan = CandidateMarginalPlan(
            reference_teams=(("A", "B"),),
            entries=(
                CandidateMarginalPlanEntry("C", ("A", "B"), (0, 1)),
                CandidateMarginalPlanEntry("D", ("A", "B"), (0, 1)),
            ),
        )
        measurement = MarginalMeasurement(
            values={},
            evaluated_candidates=(
                CandidateTeam(("A", "B"), 100, 100, "marginal-reference"),
                CandidateTeam(("C", "B"), 80, 80, "marginal-trial"),
                CandidateTeam(("A", "C"), 130, 130, "marginal-trial"),
                CandidateTeam(("D", "B"), 110, 110, "marginal-trial"),
                # D's second probe is intentionally absent: SearchBudget ended.
            ),
        )

        views = build_planned_marginal_prefix_views(plan, measurement)

        self.assertEqual(tuple(view.name for view in views), ("marginal-prefix-1", "marginal-prefix-2"))
        self.assertEqual(views[0].values, {"C": -20.0, "D": 10.0})
        self.assertEqual(views[1].values, {"C": 30.0, "D": 10.0})

    def test_prefix_view_depth_limit_does_not_require_deeper_measurement(self):
        plan = CandidateMarginalPlan(
            reference_teams=(("A", "B"),),
            entries=(CandidateMarginalPlanEntry("C", ("A", "B"), (0, 1)),),
        )
        measurement = MarginalMeasurement(
            values={},
            evaluated_candidates=(
                CandidateTeam(("A", "B"), 100, 100),
                CandidateTeam(("C", "B"), 90, 90),
            ),
        )

        views = build_planned_marginal_prefix_views(plan, measurement, max_depth=1)

        self.assertEqual(len(views), 1)
        self.assertEqual(views[0].values, {"C": -10.0})
        with self.assertRaises(ValueError):
            build_planned_marginal_prefix_views(plan, measurement, max_depth=0)

    def test_rejects_duplicate_view_names_and_negative_limit(self):
        with self.assertRaises(ValueError):
            select_proxy_view_candidates(
                (("A",),),
                (ProxyView("x", {"A": 1}), ProxyView("x", {"A": 2})),
                limit_per_view=1,
            )
        with self.assertRaises(ValueError):
            select_proxy_view_candidates(
                (("A",),),
                (ProxyView("x", {"A": 1}),),
                limit_per_view=-1,
            )


if __name__ == "__main__":
    unittest.main()
