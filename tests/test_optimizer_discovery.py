from __future__ import annotations

import unittest

from optimizer.candidate_generation import all_permutation_placements
from optimizer.discovery import generate_candidate_discovery_bundle


class CandidateDiscoveryBundleTests(unittest.TestCase):
    def test_bundle_uses_one_proxy_mapping_without_score_bonus(self):
        scores = {name: 8 - i for i, name in enumerate("ABCDEFGH")}
        bundle = generate_candidate_discovery_bundle(
            tuple(scores),
            scores,
            team_size=2,
            team_count=4,
            single_team_beam_width=8,
            single_team_global_limit=4,
            required_cores=(("G", "H"),),
            single_team_per_core_limit=1,
            allocation_team_beam_width=8,
            allocation_team_options_per_state=3,
            allocation_beam_width=6,
            allocation_limit=1,
        )

        core = next(row for row in bundle.ordinary.candidates if row.required_members)
        self.assertEqual(core.proxy_score, scores["G"] + scores["H"])
        self.assertEqual(bundle.core_channels, ((("G", "H"),),))
        self.assertEqual(bundle.protected_channels[0], (("G", "H"),))

        allocation = bundle.allocation.allocations[0]
        self.assertEqual(
            allocation.proxy_total,
            sum(scores[name] for team in allocation.teams for name in team),
        )
        self.assertEqual(
            bundle.protected_channels[1:],
            bundle.allocation_channels,
        )

    def test_protected_channels_keep_order_variants_per_membership(self):
        scores = {"A": 4, "B": 3, "C": 2, "D": 1}
        bundle = generate_candidate_discovery_bundle(
            tuple(scores),
            scores,
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

        self.assertEqual(bundle.core_channels, ())
        self.assertEqual(len(bundle.protected_channels), 2)
        self.assertTrue(all(len(channel) == 2 for channel in bundle.protected_channels))
        for channel in bundle.protected_channels:
            self.assertEqual(set(channel[0]), set(channel[1]))
            self.assertNotEqual(channel[0], channel[1])


if __name__ == "__main__":
    unittest.main()
