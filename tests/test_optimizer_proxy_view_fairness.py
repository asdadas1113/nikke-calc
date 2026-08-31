from __future__ import annotations

import unittest

from optimizer.proxy_views import ProxyView, select_proxy_view_candidates


class ProxyViewFairnessTests(unittest.TestCase):
    def test_union_order_is_rank_round_robin_across_views(self):
        teams = (("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"))
        views = (
            ProxyView("first", {"A": 10, "B": 9, "C": 1, "D": 0}),
            ProxyView("deeper", {"A": 0, "B": 1, "C": 9, "D": 10}),
        )

        selected = select_proxy_view_candidates(teams, views, limit_per_view=2)

        # first ranks: A/B and C/D; second ranks: A/C and B/D.
        # A tight downstream budget therefore sees both views before either
        # view's second-ranked team.
        self.assertEqual(
            tuple(item.members for item in selected),
            (("A", "B"), ("C", "D"), ("A", "C"), ("B", "D")),
        )
        self.assertEqual(tuple(item.hits[0].rank for item in selected), (1, 1, 2, 2))


if __name__ == "__main__":
    unittest.main()
