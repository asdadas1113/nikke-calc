from __future__ import annotations

from dataclasses import replace
import unittest

from context.spec import build_squad
from fast_engine.engine.burst import BurstSignal, compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import SignalContext
from fast_engine.engine.model import CompiledSquad
from fast_engine.engine.targets import TargetMode
from fast_engine.engine.triggers import TriggerIndex


NAMES = [
    "미란다",
    "브리드 : 사일런트 트랙",
    "헬름",
    "루주",
    "미하라 : 본딩 체인",
]


class GaugeRuntimeTests(unittest.TestCase):
    @staticmethod
    def _fixture():
        moris_squad = build_squad(NAMES)
        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(
            moris_squad,
            compiled,
            {"duration": 30.0, "first_burst_time": 3.0, "rng_mode": "expected"},
        )
        runtime = BurstRuntime(compiled, policy)
        mihara = 4
        by_name = {
            effect.name: effect
            for effect in compiled.effects
            if effect.actor == mihara
        }
        return compiled, runtime, by_name

    def test_real_mihara_battle_start_charge_then_consume_preserves_source_order(self):
        _compiled, runtime, by_name = self._fixture()
        charge = by_name["바디 컨텍"]
        consume = by_name["바디 컨텍 5"]

        self.assertTrue(runtime.dispatcher.is_runtime_executable_effect(charge))
        self.assertTrue(runtime.dispatcher.is_runtime_executable_effect(consume))

        result = runtime.dispatcher.dispatch(BurstSignal(0.0, "battle_start", 4, 4))
        self.assertIn(charge.effect_id, result.activated_effect_ids)
        self.assertIn(consume.effect_id, result.activated_effect_ids)

        # Moris evaluates effects in source order. 바디 컨텍 first creates a
        # capped 10-point gauge; later gauge-dependent effects see it; 바디 컨텍 5
        # finally consumes the entire gauge through fixed_value=-1.
        self.assertEqual(
            runtime.state.actors[4].gauges.get("포획 사슬", 0.0),
            0.0,
        )

    def test_real_mihara_gauge_charge_caps_at_ten_and_consume_minus_one_clears(self):
        _compiled, runtime, by_name = self._fixture()
        charge = by_name["바디 컨텍"]
        consume = by_name["바디 컨텍 5"]
        context = SignalContext()

        self.assertTrue(
            runtime.dispatcher._activate(charge, now=0.0, context=context)
        )
        self.assertEqual(runtime.state.actors[4].gauges["포획 사슬"], 10.0)

        # A second +10 activation must remain capped by gauge_max=10.
        self.assertTrue(
            runtime.dispatcher._activate(charge, now=0.1, context=context)
        )
        self.assertEqual(runtime.state.actors[4].gauges["포획 사슬"], 10.0)

        self.assertTrue(
            runtime.dispatcher._activate(consume, now=0.2, context=context)
        )
        self.assertEqual(runtime.state.actors[4].gauges["포획 사슬"], 0.0)

    def test_patternless_unreachable_writer_does_not_poison_real_mihara_family(self):
        _compiled, runtime, by_name = self._fixture()
        enemy_death_writer = next(
            effect
            for effect in by_name.values()
            if (effect.stat or "") == "gauge_charge"
            and any(rule.event_key == "enemy_death" for rule in effect.triggers)
        )
        charge = by_name["바디 컨텍"]

        self.assertTrue(runtime.dispatcher._gauge_patternless_unreachable(enemy_death_writer))
        self.assertFalse(runtime.dispatcher.is_runtime_executable_effect(enemy_death_writer))
        self.assertTrue(runtime.dispatcher.is_runtime_executable_effect(charge))
        self.assertNotIn((4, "포획 사슬"), runtime.dispatcher._unsafe_gauge_families)

    def test_reachable_unsupported_same_gauge_writer_poisons_entire_family(self):
        compiled, _runtime, by_name = self._fixture()
        charge = by_name["바디 컨텍"]

        # Make a synthetic reachable writer for the same gauge but with a target
        # shape this narrow slice intentionally does not implement. The whole
        # actor+gauge family must fail closed; otherwise a partial writer set could
        # silently produce a wrong gauge trajectory.
        bad_target = replace(charge.target_spec, mode=TargetMode.ALL_ALLIES, raw="all_allies")
        bad = replace(
            charge,
            effect_id=len(compiled.effects),
            actor_effect_index=max(e.actor_effect_index for e in compiled.members[4].effects) + 1,
            name="synthetic bad gauge writer",
            target="all_allies",
            target_spec=bad_target,
        )
        members = list(compiled.members)
        members[4] = replace(members[4], effects=members[4].effects + (bad,))
        effects = tuple(effect for member in members for effect in member.effects)
        poisoned = CompiledSquad(tuple(members), TriggerIndex.from_effects(effects, actor_count=5))

        moris_squad = build_squad(NAMES)
        policy = compile_burst_policy(
            moris_squad,
            poisoned,
            {"duration": 10.0, "first_burst_time": 3.0, "rng_mode": "expected"},
        )
        runtime = BurstRuntime(poisoned, policy)
        original_charge = next(
            e for e in poisoned.effects if e.actor == 4 and e.name == "바디 컨텍"
        )
        self.assertIn((4, "포획 사슬"), runtime.dispatcher._unsafe_gauge_families)
        self.assertFalse(runtime.dispatcher.is_runtime_executable_effect(original_charge))
        self.assertFalse(runtime.dispatcher.is_runtime_executable_effect(bad))


if __name__ == "__main__":
    unittest.main()
