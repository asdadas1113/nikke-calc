from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from optimizer.automatic_search import (
    AutomaticDiscoveryPolicy,
    AutomaticPlacementMode,
    run_automatic_anytime_search_round,
)
from optimizer.budget import SearchBudget
from optimizer.candidate_generation import all_permutation_placements
from optimizer.discovery import generate_multi_view_candidate_discovery
from optimizer.proxy_views import ProxyView


class ProtectedCategoryFairnessTests(unittest.TestCase):
    def test_protected_stream_finishes_first_rank_before_second_rank(self):
        result = generate_multi_view_candidate_discovery(
            ("A", "B", "C", "D"),
            (
                ProxyView("first", {"A": 4, "B": 3, "C": 2, "D": 1}),
                ProxyView("deep", {"A": 1, "B": 2, "C": 3, "D": 4}),
            ),
            team_size=2,
            team_count=2,
            single_team_beam_width=4,
            single_team_global_limit=2,
            required_cores=(),
            single_team_per_core_limit=0,
            allocation_team_beam_width=4,
            allocation_team_options_per_state=2,
            allocation_beam_width=3,
            allocation_limit=1,
            placement_expander=all_permutation_placements,
        )

        channels = result.protected_channels
        self.assertGreaterEqual(len(channels), 2)
        expected_first_rank = []
        seen = set()
        for channel in channels:
            if channel and channel[0] not in seen:
                seen.add(channel[0])
                expected_first_rank.append(channel[0])
        self.assertEqual(
            result.protected_teams[: len(expected_first_rank)],
            tuple(expected_first_rank),
        )

    def test_automatic_controller_passes_one_protected_top_level_channel(self):
        protected = (("A", "B"), ("C", "D"), ("B", "A"))
        fake_discovery = SimpleNamespace(
            ordinary_teams=(("A", "C"),),
            protected_teams=protected,
        )
        captured = {}

        def fake_anytime(*args, **kwargs):
            context = SimpleNamespace(proxy_views=())
            built = tuple(kwargs["protected_candidate_channel_builder"](context))
            captured["built"] = built
            # The ordinary builder must still share the same discovery object.
            self.assertEqual(
                tuple(kwargs["candidate_builder"](context)),
                fake_discovery.ordinary_teams,
            )
            return SimpleNamespace(total_score=None)

        policy = AutomaticDiscoveryPolicy(
            team_size=2,
            single_team_beam_width=2,
            single_team_global_limit=1,
            single_team_per_core_limit=0,
            allocation_team_beam_width=2,
            allocation_team_options_per_state=1,
            allocation_beam_width=1,
            allocation_limit=1,
            placement_mode=AutomaticPlacementMode.CANONICAL_ONLY,
        )

        with patch(
            "optimizer.automatic_search.generate_multi_view_candidate_discovery",
            return_value=fake_discovery,
        ), patch(
            "optimizer.automatic_search.run_anytime_search_round",
            side_effect=fake_anytime,
        ):
            result = run_automatic_anytime_search_round(
                SimpleNamespace(),
                budget=SearchBudget(1),
                roster=("A", "B", "C", "D"),
                reference_teams=(("A", "B"),),
                discovery_policy=policy,
                positions_per_candidate=1,
                candidate_limit=1,
                team_count=2,
            )

        self.assertIs(result.discovery, fake_discovery)
        self.assertEqual(captured["built"], (protected,))


if __name__ == "__main__":
    unittest.main()
