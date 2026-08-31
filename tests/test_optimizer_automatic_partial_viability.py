from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from optimizer.automatic_search import (
    AutomaticDiscoveryPolicy,
    AutomaticPlacementMode,
    _resolve_partial_viability,
    run_automatic_anytime_search_round,
)
from optimizer.budget import SearchBudget
from optimizer.constraints import BurstMetadata, BurstStructureValidator


class AutomaticPartialViabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = BurstStructureValidator(
            {
                "b3a": BurstMetadata("3"),
                "b3b": BurstMetadata("3"),
                "b1": BurstMetadata("1"),
                "b2": BurstMetadata("2"),
            }
        )
        self.roster = ("b3a", "b3b", "b1", "b2")

    def test_burst_validator_can_opt_in_automatically(self):
        viable = _resolve_partial_viability(
            self.validator,
            None,
            team_size=3,
        )
        self.assertIsNotNone(viable)
        assert viable is not None

        # One B3 leaves two slots, so B1+B2 can still complete the structure.
        self.assertTrue(viable(("b3a",), self.roster))
        # Two B3s leave only one slot, so both missing B1 and B2 cannot be covered.
        self.assertFalse(viable(("b3a", "b3b"), self.roster))
        self.assertTrue(viable(("b3a", "b1", "b2"), self.roster))

    def test_plain_final_team_callable_does_not_gain_inferred_partial_semantics(self):
        viable = _resolve_partial_viability(
            lambda team: len(team) == 3,
            None,
            team_size=3,
        )
        self.assertIsNone(viable)

    def test_explicit_partial_viability_always_wins(self):
        explicit = lambda partial, roster: True
        viable = _resolve_partial_viability(
            self.validator,
            explicit,
            team_size=3,
        )
        self.assertIs(viable, explicit)
        self.assertTrue(viable(("b3a", "b3b"), self.roster))

    def test_dynamic_stage_possibility_remains_fail_open(self):
        validator = BurstStructureValidator(
            {
                "dynamic": BurstMetadata("3", dynamic_stages=frozenset({"1", "2"})),
                "b3": BurstMetadata("3"),
            }
        )
        viable = _resolve_partial_viability(validator, None, team_size=2)
        assert viable is not None
        self.assertTrue(viable(("dynamic", "b3"), ("dynamic", "b3")))

    def test_controller_passes_resolved_viability_into_discovery(self):
        captured = {}
        fake_discovery = SimpleNamespace(
            ordinary_teams=(("b3a", "b1", "b2"),),
            protected_teams=(),
        )

        def fake_generate(*args, **kwargs):
            captured["partial_viable"] = kwargs["partial_viable"]
            return fake_discovery

        def fake_anytime(*args, **kwargs):
            context = SimpleNamespace(proxy_views=())
            self.assertEqual(
                tuple(kwargs["candidate_builder"](context)),
                fake_discovery.ordinary_teams,
            )
            return SimpleNamespace(total_score=None)

        policy = AutomaticDiscoveryPolicy(
            team_size=3,
            single_team_beam_width=4,
            single_team_global_limit=2,
            single_team_per_core_limit=0,
            allocation_team_beam_width=4,
            allocation_team_options_per_state=2,
            allocation_beam_width=2,
            allocation_limit=1,
            placement_mode=AutomaticPlacementMode.CANONICAL_ONLY,
        )
        with patch(
            "optimizer.automatic_search.generate_multi_view_candidate_discovery",
            side_effect=fake_generate,
        ), patch(
            "optimizer.automatic_search.run_anytime_search_round",
            side_effect=fake_anytime,
        ):
            result = run_automatic_anytime_search_round(
                SimpleNamespace(),
                budget=SearchBudget(0),
                roster=self.roster,
                reference_teams=(("b3a", "b1", "b2"),),
                discovery_policy=policy,
                positions_per_candidate=1,
                candidate_limit=1,
                team_count=1,
                legal=self.validator,
            )

        self.assertIs(result.discovery, fake_discovery)
        viable = captured["partial_viable"]
        self.assertIsNotNone(viable)
        self.assertFalse(viable(("b3a", "b3b"), self.roster))


if __name__ == "__main__":
    unittest.main()
