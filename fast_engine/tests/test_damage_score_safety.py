from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_normal_score_blockers


class StaticScoreSafetyTests(unittest.TestCase):
    def test_real_winter_ludmilla_ammo_refill_blocks_static_shot_plan(self):
        squad = compile_moris_squad(
            build_squad(["루드밀라 : 윈터 오너"]),
            require_five=False,
        )
        blockers = static_normal_score_blockers(squad)

        self.assertTrue(
            any("ammo_charge_flat" in blocker for blocker in blockers),
            f"expected ammo refill cadence blocker, got: {blockers}",
        )


if __name__ == "__main__":
    unittest.main()
