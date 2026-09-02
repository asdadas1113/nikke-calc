from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_normal_score_blockers


class StaticScoreSafetyTests(unittest.TestCase):
    def test_real_winter_ludmilla_reducible_ammo_refill_is_dynamic(self):
        squad = compile_moris_squad(
            build_squad(["루드밀라 : 윈터 오너"]),
            require_five=False,
        )
        blockers = static_normal_score_blockers(squad)

        self.assertFalse(
            any("ammo_charge_flat" in blocker for blocker in blockers),
            f"expected reducible weapon-count ammo refill to be dynamic, got: {blockers}",
        )


if __name__ == "__main__":
    unittest.main()
