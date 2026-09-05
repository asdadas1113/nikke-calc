from __future__ import annotations

from dataclasses import replace
import unittest

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy, BurstSignal, compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.last_bullet import simulate_static_last_bullet_boundaries
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.state import ENEMY
from fast_engine.engine.triggers import TriggerMode, TriggerRule


class LastBulletDamageStateTests(unittest.TestCase):
    @staticmethod
    def _helm_fixture():
        names = ["헬름", "아니스", "라피", "미하라", "프로덕트 08"]
        moris_squad = build_squad(names)
        compiled = compile_moris_squad(moris_squad)
        helm = next(
            effect
            for effect in compiled.effects
            if effect.actor == 0
            and effect.name == "진두지휘"
            and effect.stat == "normal_atk_crit_rate"
        )
        return moris_squad, compiled, helm

    def test_post_shot_last_bullet_delivery_is_owned_but_cross_actor_order_fails_closed(self):
        _moris_squad, compiled, helm = self._helm_fixture()

        self.assertEqual(tuple(rule.event_key for rule in helm.triggers), ("last_bullet",))
        self.assertTrue(is_direct_damage_buff_runtime_supported(helm))
        blockers = static_score_blockers(compiled)
        self.assertIn("normal_state:헬름:진두지휘:same_timestamp_actor_order", blockers)
        self.assertNotIn("normal_delivery:헬름:진두지휘:normal_atk_crit_rate", blockers)
        self.assertNotIn("skill_state_delivery:헬름:진두지휘:normal_atk_crit_rate", blockers)

        # Moris last_bullet_fire is a different pre-shot notification. It must not
        # become score-safe merely because post-shot last_bullet is now supported.
        pre_shot = replace(
            helm,
            triggers=(
                TriggerRule(
                    "last_bullet_fire",
                    "last_bullet_fire",
                    TriggerMode.EVENT,
                ),
            ),
        )
        self.assertFalse(is_direct_damage_buff_runtime_supported(pre_shot))

    def test_static_boundary_keeps_exact_last_bullet_event_key(self):
        _moris_squad, compiled, helm = self._helm_fixture()
        rows = simulate_static_last_bullet_boundaries(
            compiled,
            duration=30.0,
            effect_filter=lambda effect: effect.effect_id == helm.effect_id,
        )
        self.assertTrue(rows)
        self.assertTrue(all(row.actor == 0 for row in rows))
        self.assertEqual({row.event_key for row in rows}, {"last_bullet"})

    def test_real_helm_last_bullet_buff_activates_after_first_magazine_end(self):
        moris_squad, compiled, helm = self._helm_fixture()
        rows = simulate_static_last_bullet_boundaries(
            compiled,
            duration=30.0,
            effect_filter=lambda effect: effect.effect_id == helm.effect_id,
        )
        first = rows[0].time
        horizon = first + 0.01
        policy = compile_burst_policy(
            moris_squad,
            compiled,
            {"duration": horizon},
        )
        runtime = BurstRuntime(compiled, policy)
        runtime.run(duration=horizon)

        # The effect targets all allies, so both Helm and another ally should see
        # the same post-shot normal-attack crit-rate contribution immediately
        # after the first magazine-ending shot.
        helm_value = runtime.dispatcher.effects.sum_stat(
            0, "normal_atk_crit_rate", now=first + 0.001
        )
        ally_value = runtime.dispatcher.effects.sum_stat(
            1, "normal_atk_crit_rate", now=first + 0.001
        )
        self.assertGreater(helm_value, 0.0)
        self.assertAlmostEqual(ally_value, helm_value, places=9)

    def test_last_bullet_damage_support_respects_named_enemy_state_gate(self):
        moris_squad = build_squad(["프리바티"])
        compiled = compile_moris_squad(moris_squad, require_five=False)
        ld2 = next(effect for effect in compiled.effects if effect.name == "LD 어설트 2")
        ld3 = next(effect for effect in compiled.effects if effect.name == "LD 어설트 3")

        enemy = EnemyStaticProfile(defense=0.0, duration=20.0)
        sink = SimpleDamageScoreSink(compiled, enemy)
        self.assertTrue(sink.supports(ld2))
        self.assertTrue(sink.supports(ld3))

        runtime = BurstRuntime(
            compiled,
            BurstPolicy(
                duration=20.0,
                first_burst_time=20.0,
                max_burst_count=0,
                no_burst_actors=frozenset({0}),
            ),
            enemy,
            damage_sink=sink,
        )
        runtime._broadcast(0.0, "battle_start")

        runtime.dispatcher.dispatch(BurstSignal(1.0, "last_bullet", 0, 0))
        self.assertEqual(runtime.dispatcher._activation_counts.get(ld2.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(ld3.effect_id, 0), 0)

        runtime.dispatcher.dispatch(BurstSignal(3.0, "burst_cast", 0, 0))
        self.assertTrue(
            runtime.dispatcher.effects.has_named_state(ENEMY, "타겟 지정", now=3.1)
        )
        runtime.dispatcher.dispatch(BurstSignal(3.1, "last_bullet", 0, 0))
        self.assertEqual(runtime.dispatcher._activation_counts.get(ld2.effect_id, 0), 2)
        self.assertEqual(runtime.dispatcher._activation_counts.get(ld3.effect_id, 0), 1)

        self.assertFalse(
            runtime.dispatcher.effects.has_named_state(ENEMY, "타겟 지정", now=13.1)
        )
        runtime.dispatcher.dispatch(BurstSignal(13.1, "last_bullet", 0, 0))
        self.assertEqual(runtime.dispatcher._activation_counts.get(ld2.effect_id, 0), 3)
        self.assertEqual(runtime.dispatcher._activation_counts.get(ld3.effect_id, 0), 1)


if __name__ == "__main__":
    unittest.main()
