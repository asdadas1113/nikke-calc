from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import ConditionMode
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.score import static_score_blockers


class BackRowDamageStateTests(unittest.TestCase):
    @staticmethod
    def _fixture(names):
        moris_squad = build_squad(names)
        compiled = compile_moris_squad(moris_squad)
        sword_coin = next(
            effect
            for effect in compiled.effects
            if compiled.names[effect.actor] == "루주"
            and effect.name == "소드 코인"
            and effect.stat == "atk_dmg_pct"
        )
        return moris_squad, compiled, sword_coin

    def test_real_rouge_sword_coin_is_certified_as_static_back_row_damage_state(self):
        names = ["아니스", "라피", "미하라", "루주", "프로덕트 08"]
        _moris_squad, compiled, sword_coin = self._fixture(names)

        self.assertEqual(sword_coin.actor, 3)
        self.assertEqual(
            tuple(rule.mode for rule in sword_coin.condition_rules),
            (ConditionMode.BACK_ROW,),
        )
        self.assertEqual(sword_coin.target, "allies_adjacent:2")
        self.assertTrue(is_direct_damage_buff_runtime_supported(sword_coin))
        self.assertFalse(
            any(
                "루주:소드 코인:atk_dmg_pct" in blocker
                for blocker in static_score_blockers(compiled)
            )
        )

    def test_real_rouge_sword_coin_activates_only_from_moris_back_row_slots(self):
        back_names = ["아니스", "라피", "미하라", "루주", "프로덕트 08"]
        moris_squad, compiled, sword_coin = self._fixture(back_names)
        policy = compile_burst_policy(moris_squad, compiled, {"duration": 0.1})
        runtime = BurstRuntime(compiled, policy)
        runtime.run(duration=0.1)

        value = float(sword_coin.value or 0.0)
        self.assertGreater(value, 0.0)
        # Rouge is slot 4 (index 3). Moris/Fast adjacent:2 resolves to slots 3/5.
        self.assertAlmostEqual(
            runtime.dispatcher.effects.sum_stat(2, "atk_dmg_pct", now=0.01),
            value,
            places=9,
        )
        self.assertAlmostEqual(
            runtime.dispatcher.effects.sum_stat(4, "atk_dmg_pct", now=0.01),
            value,
            places=9,
        )
        self.assertEqual(
            runtime.dispatcher.effects.sum_stat(3, "atk_dmg_pct", now=0.01),
            0.0,
        )

        front_names = ["루주", "아니스", "라피", "미하라", "프로덕트 08"]
        front_squad, front_compiled, _front_coin = self._fixture(front_names)
        front_policy = compile_burst_policy(
            front_squad, front_compiled, {"duration": 0.1}
        )
        front_runtime = BurstRuntime(front_compiled, front_policy)
        front_runtime.run(duration=0.1)
        self.assertTrue(
            all(
                front_runtime.dispatcher.effects.sum_stat(
                    actor, "atk_dmg_pct", now=0.01
                )
                == 0.0
                for actor in range(5)
            )
        )


if __name__ == "__main__":
    unittest.main()
