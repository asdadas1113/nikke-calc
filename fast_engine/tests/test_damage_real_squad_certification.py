from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import SignalContext
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.last_bullet import simulate_static_last_bullet_boundaries
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers
from fast_engine.engine.state import ENEMY


NAMES = [
    "미란다",
    "브리드 : 사일런트 트랙",
    "헬름",
    "루주",
    "미하라 : 본딩 체인",
]
CONFIG = {
    "duration": 180.0,
    "first_burst_time": 3.0,
    "rng_mode": "expected",
}


class RealSquadCertificationTests(unittest.TestCase):
    @staticmethod
    def _fixture():
        moris_squad = build_squad(NAMES)
        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(moris_squad, compiled, CONFIG)
        enemy = EnemyStaticProfile(
            defense=31784.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=180.0,
        )
        return moris_squad, compiled, policy, enemy

    def test_control_miranda_mihara_is_first_fully_certified_real_squad(self):
        _moris_squad, compiled, policy, enemy = self._fixture()

        self.assertEqual(static_score_blockers(compiled), ())
        score = score_static_squad(compiled, policy, enemy)
        self.assertGreater(score.squad_total, 0.0)
        self.assertGreater(score.events_processed, 0)
        self.assertEqual(score.unsupported, ())

    def test_mihara_body_contact_uses_live_gauge_as_direct_hit_count(self):
        moris_squad, compiled, _policy, enemy = self._fixture()
        policy = compile_burst_policy(
            moris_squad,
            compiled,
            {**CONFIG, "duration": 1.0},
        )
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        effect = next(
            row
            for row in compiled.effects
            if row.actor == 4 and row.name == "바디 컨텍 3"
        )

        self.assertTrue(sink.supports(effect))
        self.assertIn(effect.effect_id, sink.stack_specs)

        runtime.state.set_gauge(4, "포획 사슬", 1.0)
        before = sink.char_total[4]
        self.assertTrue(
            runtime.dispatcher._activate(
                effect,
                now=0.0,
                context=SignalContext(),
            )
        )
        one_stack = sink.char_total[4] - before
        self.assertGreater(one_stack, 0.0)

        runtime.state.set_gauge(4, "포획 사슬", 3.0)
        before = sink.char_total[4]
        self.assertTrue(
            runtime.dispatcher._activate(
                effect,
                now=0.1,
                context=SignalContext(),
            )
        )
        three_stack = sink.char_total[4] - before
        self.assertAlmostEqual(three_stack, one_stack * 3.0, places=6)

    def test_mihara_dot_chain_captures_mutates_and_survives_named_removal(self):
        moris_squad, compiled, _policy, enemy = self._fixture()
        policy = compile_burst_policy(
            moris_squad,
            compiled,
            {**CONFIG, "duration": 5.0},
        )
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        mihara = [effect for effect in compiled.effects if effect.actor == 4]
        chain = next(effect for effect in mihara if effect.name == "사슬 감기")
        pull = next(effect for effect in mihara if effect.name == "사슬 당기기")
        stack_add = next(
            effect
            for effect in mihara
            if (effect.stat or "") == "debuff_stack_add"
            and effect.parameters.get("target_effect") == "사슬 감기"
            and any(rule.event_key == "hit_count" for rule in effect.triggers)
        )
        remove = next(
            effect
            for effect in mihara
            if (effect.stat or "") == "remove_named_buff"
            and effect.parameters.get("target_effect") == "사슬 감기"
        )

        self.assertTrue(sink.supports(chain))
        self.assertTrue(sink.supports(pull))
        self.assertTrue(sink.supports_state_operation(stack_add))
        self.assertTrue(sink.supports_state_operation(remove))

        runtime.state.set_gauge(4, "포획 사슬", 10.0)
        self.assertTrue(
            runtime.dispatcher._activate(
                chain,
                now=0.0,
                context=SignalContext(),
            )
        )
        self.assertTrue(
            runtime.dispatcher.effects.has_named_state(
                ENEMY, "사슬 감기", now=0.0
            )
        )
        self.assertEqual(
            runtime.dispatcher.effects.named_stack(ENEMY, "사슬 감기", now=0.0),
            10.0,
        )

        # The real hit_count:40 mutator is normally gated by full burst. Its state
        # operation itself is tested directly here so the stack semantic is not
        # entangled with weapon timing in this unit.
        self.assertTrue(
            sink.activate_state_operation(
                stack_add,
                now=0.1,
                targets=(ENEMY,),
            )
        )
        self.assertEqual(
            runtime.dispatcher.effects.named_stack(ENEMY, "사슬 감기", now=0.1),
            11.0,
        )

        # Chain Pull captures the current 11-stack Chain Wind into its own DoT.
        self.assertTrue(
            runtime.dispatcher._activate(
                pull,
                now=0.2,
                context=SignalContext(),
            )
        )
        self.assertEqual(
            runtime.dispatcher.effects.named_stack(ENEMY, "사슬 당기기", now=0.2),
            11.0,
        )

        # The following real burst-cast state operation removes Chain Wind only.
        # Chain Pull must retain its captured stack and continue its finite timer.
        self.assertTrue(
            runtime.dispatcher._activate(
                remove,
                now=0.2,
                context=SignalContext(),
            )
        )
        self.assertFalse(
            runtime.dispatcher.effects.has_named_state(
                ENEMY, "사슬 감기", now=0.2
            )
        )
        self.assertEqual(
            runtime.dispatcher.effects.named_stack(ENEMY, "사슬 당기기", now=0.2),
            11.0,
        )
        self.assertTrue(sink.supports(pull))

    def test_real_helm_last_bullet_still_activates_on_dynamic_charge_score_path(self):
        moris_squad, compiled, _policy, enemy = self._fixture()
        helm = next(
            effect
            for effect in compiled.effects
            if effect.actor == 2
            and effect.name == "진두지휘"
            and effect.stat == "normal_atk_crit_rate"
        )
        rows = simulate_static_last_bullet_boundaries(
            compiled,
            duration=30.0,
            effect_filter=lambda effect: effect.effect_id == helm.effect_id,
        )
        self.assertTrue(rows)
        first = rows[0].time
        policy = compile_burst_policy(
            moris_squad,
            compiled,
            {**CONFIG, "duration": first + 0.01},
        )

        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        runtime.run(duration=first + 0.01)

        self.assertTrue(runtime.weapons.emits_every_charge_shot(2))
        helm_value = runtime.dispatcher.effects.sum_stat(
            2, "normal_atk_crit_rate", now=first + 0.001
        )
        ally_value = runtime.dispatcher.effects.sum_stat(
            0, "normal_atk_crit_rate", now=first + 0.001
        )
        self.assertGreater(helm_value, 0.0)
        self.assertAlmostEqual(ally_value, helm_value, places=9)


if __name__ == "__main__":
    unittest.main()
