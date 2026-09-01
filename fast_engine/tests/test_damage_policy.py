from __future__ import annotations

import unittest
from dataclasses import replace

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import compile_condition
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.dispatcher import TriggerDispatcher


class DamageEffectPolicyTests(unittest.TestCase):
    def test_real_hit_count_damage_buff_is_executable(self):
        squad = compile_moris_squad(
            build_squad(["나가", "리타", "크라운", "홍련", "앨리스"])
        )
        effect = next(
            e for e in squad.members[0].effects
            if e.stat == "core_dmg_pct"
            and any(rule.event_key == "hit_count" for rule in e.triggers)
        )
        self.assertTrue(is_direct_damage_buff_runtime_supported(effect))
        self.assertTrue(TriggerDispatcher.is_executable_effect(effect))

    def test_raw_full_charge_hit_without_every_hit_producer_fails_closed(self):
        squad = compile_moris_squad(
            build_squad(["리버렐리오", "미카", "아니스", "라피", "폴리"])
        )
        effect = next(
            e for e in squad.members[0].effects
            if e.name == "격류"
            and any(rule.raw == "full_charge_hit" for rule in e.triggers)
        )
        self.assertEqual(effect.stat, "atk_dmg_pct")
        self.assertFalse(is_direct_damage_buff_runtime_supported(effect))
        self.assertFalse(TriggerDispatcher.is_executable_effect(effect))

    def test_gauge_condition_stays_fail_closed(self):
        squad = compile_moris_squad(
            build_squad(["나가", "리타", "크라운", "홍련", "앨리스"])
        )
        base = next(e for e in squad.members[0].effects if e.stat == "core_dmg_pct")
        gated = replace(
            base,
            conditions=("gauge_above:test:1",),
            condition_rules=(compile_condition("gauge_above:test:1"),),
        )
        self.assertFalse(is_direct_damage_buff_runtime_supported(gated))

    def test_periodic_damage_state_remains_outside_new_general_lane(self):
        squad = compile_moris_squad(
            build_squad(["밀크", "크라운", "홍련", "앨리스", "나가"])
        )
        milk = next(
            e for e in squad.members[0].effects
            if e.name == "밀크에겐 맡겨!"
            and any(rule.is_periodic for rule in e.triggers)
        )
        # Milk remains supported by the older, explicitly validated auxiliary
        # ATK lane. This new generic damage policy deliberately does not claim
        # periodic support for every damage stat yet.
        self.assertFalse(is_direct_damage_buff_runtime_supported(milk))
        self.assertTrue(TriggerDispatcher.is_executable_effect(milk))


if __name__ == "__main__":
    unittest.main()
