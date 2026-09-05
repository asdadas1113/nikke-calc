from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.state import ENEMY


class PeriodicFiniteEnemyReceivedDamageTests(unittest.TestCase):
    TEAM = "레이드_헬름아쿠아스노우"
    EFFECT = "이지스 캐논 견제 사격 2"

    def _compiled(self):
        moris = spec.build_squad(list(snapshot.SQUADS[self.TEAM]["members"]))
        compiled = compile_moris_squad(moris)
        helm = next(i for i, m in enumerate(compiled.members) if m.name == "헬름 : 아쿠아마린")
        effect = next(e for e in compiled.members[helm].effects if e.name == self.EFFECT)
        return moris, compiled, effect

    @staticmethod
    def _fast_enemy(code: str, *, duration: float) -> EnemyStaticProfile:
        core_px = float(DEFAULT_ENEMY.get("core_px", 0.0) or 0.0)
        return EnemyStaticProfile(
            defense=float(DEFAULT_ENEMY.get("def", 31784.0)),
            element=code,
            core_px=core_px,
            core_uptime=1.0 if core_px > 0.0 else 0.0,
            duration=duration,
        )

    def test_public_helm_shape_removes_only_its_delivery_blockers(self):
        _moris, compiled, effect = self._compiled()
        self.assertTrue(
            TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(effect)
        )
        self.assertTrue(TriggerDispatcher.is_executable_effect(effect))
        blockers = set(static_score_blockers(compiled))
        self.assertNotIn(
            "normal_delivery:헬름 : 아쿠아마린:이지스 캐논 견제 사격 2:received_dmg_pct",
            blockers,
        )
        self.assertNotIn(
            "skill_state_delivery:헬름 : 아쿠아마린:이지스 캐논 견제 사격 2:received_dmg_pct",
            blockers,
        )
        self.assertIn(
            "periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval",
            blockers,
        )
        self.assertIn("weapon_change:스노우 화이트:세븐스 드워프 : I", blockers)
        self.assertIn(
            "normal_delivery:스노우 화이트:세븐스 드워프 : I 2:pierce_enabled",
            blockers,
        )

    def test_fast_activation_and_stack_trace_matches_moris(self):
        moris_squad, compiled, effect = self._compiled()
        duration = 25.0
        config = {"duration": duration, "rng_mode": "expected"}
        enemy = dict(DEFAULT_ENEMY)
        enemy["code"] = "전격"
        policy = compile_burst_policy(moris_squad, compiled, config)
        fast_trace = []
        original = TriggerDispatcher.dispatch_periodic

        def traced(dispatcher, effect_id, rule_index, *, time, context):
            result = original(
                dispatcher,
                effect_id,
                rule_index,
                time=time,
                context=context,
            )
            if effect_id == effect.effect_id and effect_id in result.activated_effect_ids:
                fast_trace.append(
                    (
                        time,
                        dispatcher.effects.named_stack(ENEMY, effect.name, now=time),
                        dispatcher.effects.sum_stat(ENEMY, "received_dmg_pct", now=time),
                    )
                )
            return result

        with patch.object(TriggerDispatcher, "dispatch_periodic", new=traced):
            BurstRuntime(
                compiled,
                policy,
                enemy=self._fast_enemy("전격", duration=duration),
            ).run(duration=duration)

        moris = simulate(moris_squad, config=config, enemy=enemy, verbose=True)
        rows = [
            row
            for row in moris.log.buff_events
            if row.kind == "activate" and row.name == self.EFFECT
        ]
        self.assertEqual(len(fast_trace), 6, fast_trace)
        self.assertEqual(len(rows), 6, rows)
        for (fast_t, fast_stack, fast_value), row in zip(fast_trace, rows):
            self.assertAlmostEqual(fast_t, row.t, places=9)
            self.assertAlmostEqual(fast_stack, float(row.stack), places=9)
            self.assertAlmostEqual(fast_value, float(row.value), places=9)

    def test_target_code_mismatch_activates_neither_runtime(self):
        moris_squad, compiled, effect = self._compiled()
        duration = 25.0
        config = {"duration": duration, "rng_mode": "expected"}
        enemy = dict(DEFAULT_ENEMY)
        enemy["code"] = "작열"
        policy = compile_burst_policy(moris_squad, compiled, config)
        fast_times = []
        original = TriggerDispatcher.dispatch_periodic

        def traced(dispatcher, effect_id, rule_index, *, time, context):
            result = original(
                dispatcher,
                effect_id,
                rule_index,
                time=time,
                context=context,
            )
            if effect_id == effect.effect_id and effect_id in result.activated_effect_ids:
                fast_times.append(time)
            return result

        with patch.object(TriggerDispatcher, "dispatch_periodic", new=traced):
            BurstRuntime(
                compiled,
                policy,
                enemy=self._fast_enemy("작열", duration=duration),
            ).run(duration=duration)
        moris = simulate(moris_squad, config=config, enemy=enemy, verbose=True)
        moris_times = [
            row.t
            for row in moris.log.buff_events
            if row.kind == "activate" and row.name == self.EFFECT
        ]
        self.assertEqual(fast_times, [])
        self.assertEqual(moris_times, [])

    def test_neighboring_enemy_periodic_shapes_remain_fail_closed(self):
        _moris, _compiled, effect = self._compiled()
        self.assertFalse(
            TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(
                replace(effect, condition_rules=())
            )
        )
        self.assertFalse(
            TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(
                replace(effect, max_stack=2.5)
            )
        )
        self.assertFalse(
            TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(
                replace(effect, polarity="beneficial")
            )
        )


if __name__ == "__main__":
    unittest.main()
