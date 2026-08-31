from __future__ import annotations

import unittest

from optimizer.automatic_search import _resolve_partial_viability
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


if __name__ == "__main__":
    unittest.main()
