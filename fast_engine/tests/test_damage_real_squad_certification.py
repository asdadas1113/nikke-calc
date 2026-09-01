from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import SignalContext
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.last_bullet import simulate_static_last_bullet_boundaries
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers
from fast_engine.engine.shot_blocks import next_static_shot_after
from fast_engine.engine.state import ENEMY

NAMES = ["미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인"]
CONFIG = {"duration": 180.0, "first_burst_time": 3.0, "rng_mode": "expected"}


class RealSquadCertificationTests(unittest.TestCase):
    @staticmethod
    def _fixture():
        moris = build_squad(NAMES)
        compiled = compile_moris_squad(moris)
        policy = compile_burst_policy(moris, compiled, CONFIG)
        enemy = EnemyStaticProfile(defense=31784.0, element=None, core_uptime=0.0, core_px=0.0, duration=180.0)
        return moris, compiled, policy, enemy

    def test_miranda_mihara_control_fails_closed(self):
        _moris, compiled, policy, enemy = self._fixture()
        self.assertEqual(compiled.members[4].weapon.get("control"), {"cover": {"policy": "own_full_burst"}})
        self.assertIn("control:미하라 : 본딩 체인", static_score_blockers(compiled))
        with self.assertRaisesRegex(NotImplementedError, "control:미하라 : 본딩 체인"):
            score_static_squad(compiled, policy, enemy)

    def test_miranda_wakeup_one_shot_crit_expires_after_recipient_shot(self):
        moris = build_squad(NAMES)
        # Remove the independently unsupported Mihara cover control so this test
        # isolates Miranda's target-side one-shot lifetime.
        next(c for c in moris if c["name"] == "미하라 : 본딩 체인")["control"] = {}
        compiled = compile_moris_squad(moris)
        wakeup = next(
            e for e in compiled.effects
            if e.name == "웨이크업! 4" and e.stat == "crit_rate"
        )
        policy = compile_burst_policy(moris, compiled, {**CONFIG, "duration": 5.0})
        enemy = EnemyStaticProfile(
            defense=31784.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=5.0,
        )

        self.assertEqual(wakeup.parameters.get("duration_bullets"), 1)
        self.assertIsNone(wakeup.duration)
        self.assertEqual(wakeup.target, "allies_top_atk_excl:1")
        self.assertTrue(is_direct_damage_buff_runtime_supported(wakeup))
        blockers = static_score_blockers(compiled)
        self.assertNotIn(
            "normal_delivery:미란다:웨이크업! 4:crit_rate",
            blockers,
        )
        self.assertNotIn(
            "skill_state_delivery:미란다:웨이크업! 4:crit_rate",
            blockers,
        )

        timing_probe = BurstRuntime(compiled, policy, enemy)
        result = timing_probe.run(duration=5.0)
        self.assertTrue(result.full_burst_starts)
        full_burst_start = result.full_burst_starts[0]

        active_runtime = BurstRuntime(compiled, policy, enemy)
        active_runtime.run(duration=full_burst_start + 1e-6)
        active_rows = [
            active
            for effect, active in active_runtime.dispatcher.effects.iter_stat(
                "crit_rate", now=full_burst_start + 1e-7
            )
            if effect.effect_id == wakeup.effect_id
        ]
        self.assertEqual(len(active_rows), 1)
        recipient = active_rows[0].target
        self.assertGreater(
            active_runtime.dispatcher.effects.sum_stat(
                recipient, "crit_rate", now=full_burst_start + 1e-7
            ),
            0.0,
        )

        consuming_shot = next_static_shot_after(
            compiled, recipient, full_burst_start
        )
        self.assertGreater(consuming_shot, full_burst_start)

        expired_runtime = BurstRuntime(compiled, policy, enemy)
        expired_runtime.run(duration=consuming_shot + 1e-6)
        lingering = [
            active
            for effect, active in expired_runtime.dispatcher.effects.iter_stat(
                "crit_rate", now=consuming_shot + 1e-7
            )
            if effect.effect_id == wakeup.effect_id
        ]
        self.assertEqual(lingering, [])

    def test_mihara_body_contact_uses_live_gauge_as_hit_count(self):
        moris, compiled, _policy, enemy = self._fixture()
        policy = compile_burst_policy(moris, compiled, {**CONFIG, "duration": 1.0})
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        effect = next(e for e in compiled.effects if e.actor == 4 and e.name == "바디 컨텍 3")
        runtime.state.set_gauge(4, "포획 사슬", 1.0)
        before = sink.char_total[4]
        self.assertTrue(runtime.dispatcher._activate(effect, now=0.0, context=SignalContext()))
        one = sink.char_total[4] - before
        runtime.state.set_gauge(4, "포획 사슬", 3.0)
        before = sink.char_total[4]
        self.assertTrue(runtime.dispatcher._activate(effect, now=0.1, context=SignalContext()))
        self.assertAlmostEqual(sink.char_total[4] - before, one * 3.0, places=6)

    def test_mihara_burst_end_recharge_sees_cast_state(self):
        moris, compiled, _policy, enemy = self._fixture()
        policy = compile_burst_policy(moris, compiled, {**CONFIG, "duration": 26.41})
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        runtime.run(duration=26.41)
        mihara = [e for e in compiled.effects if e.actor == 4]
        by_name = {e.name: e for e in mihara}
        self.assertEqual(runtime.dispatcher._activation_counts[by_name["바디 컨텍 2"].effect_id], 1)
        self.assertEqual(runtime.dispatcher._activation_counts[by_name["바디 컨텍 3"].effect_id], 2)
        self.assertEqual(runtime.dispatcher._activation_counts[by_name["사슬 감기"].effect_id], 2)
        self.assertEqual(runtime.dispatcher._activation_counts[by_name["바디 컨텍 5"].effect_id], 2)

    def test_mihara_dot_chain_state_survives_named_removal(self):
        moris, compiled, _policy, enemy = self._fixture()
        policy = compile_burst_policy(moris, compiled, {**CONFIG, "duration": 5.0})
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        rows = [e for e in compiled.effects if e.actor == 4]
        chain = next(e for e in rows if e.name == "사슬 감기")
        pull = next(e for e in rows if e.name == "사슬 당기기")
        stack_add = next(e for e in rows if e.stat == "debuff_stack_add" and e.parameters.get("target_effect") == "사슬 감기" and any(r.event_key == "hit_count" for r in e.triggers))
        remove = next(e for e in rows if e.stat == "remove_named_buff" and e.parameters.get("target_effect") == "사슬 감기")
        runtime.state.set_gauge(4, "포획 사슬", 10.0)
        self.assertTrue(runtime.dispatcher._activate(chain, now=0.0, context=SignalContext()))
        self.assertTrue(sink.activate_state_operation(stack_add, now=0.1, targets=(ENEMY,)))
        self.assertEqual(runtime.dispatcher.effects.named_stack(ENEMY, "사슬 감기", now=0.1), 11.0)
        self.assertTrue(runtime.dispatcher._activate(pull, now=0.2, context=SignalContext()))
        self.assertTrue(runtime.dispatcher._activate(remove, now=0.2, context=SignalContext()))
        self.assertFalse(runtime.dispatcher.effects.has_named_state(ENEMY, "사슬 감기", now=0.2))
        self.assertEqual(runtime.dispatcher.effects.named_stack(ENEMY, "사슬 당기기", now=0.2), 11.0)

    def test_real_helm_last_bullet_still_activates(self):
        moris, compiled, _policy, enemy = self._fixture()
        helm = next(e for e in compiled.effects if e.actor == 2 and e.name == "진두지휘" and e.stat == "normal_atk_crit_rate")
        rows = simulate_static_last_bullet_boundaries(compiled, duration=30.0, effect_filter=lambda e: e.effect_id == helm.effect_id)
        self.assertTrue(rows)
        first = rows[0].time
        policy = compile_burst_policy(moris, compiled, {**CONFIG, "duration": first + 0.01})
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        runtime.run(duration=first + 0.01)
        helm_value = runtime.dispatcher.effects.sum_stat(2, "normal_atk_crit_rate", now=first + 0.001)
        ally_value = runtime.dispatcher.effects.sum_stat(0, "normal_atk_crit_rate", now=first + 0.001)
        self.assertGreater(helm_value, 0.0)
        self.assertAlmostEqual(ally_value, helm_value, places=9)


if __name__ == "__main__":
    unittest.main()
