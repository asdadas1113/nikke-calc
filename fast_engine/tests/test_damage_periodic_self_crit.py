from __future__ import annotations

import unittest
from unittest.mock import patch

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.score import static_score_blockers


class PeriodicFiniteSelfCritTests(unittest.TestCase):
    TEAM = '레이드_헬름아쿠아스노우'

    def _compiled(self):
        moris = spec.build_squad(list(snapshot.SQUADS[self.TEAM]['members']))
        compiled = compile_moris_squad(moris)
        sw = next(i for i, m in enumerate(compiled.members) if m.name == '스노우 화이트')
        effect = next(
            e for e in compiled.members[sw].effects
            if e.name == '세븐스 드워프 : V&VI 2'
        )
        return moris, compiled, effect

    def test_real_shape_removes_only_periodic_crit_delivery_blockers(self):
        _moris, compiled, effect = self._compiled()
        self.assertTrue(
            TriggerDispatcher._periodic_finite_self_crit_shape_supported(effect)
        )
        blockers = set(static_score_blockers(compiled))
        self.assertNotIn(
            'normal_delivery:스노우 화이트:세븐스 드워프 : V&VI 2:crit_rate',
            blockers,
        )
        self.assertNotIn(
            'skill_state_delivery:스노우 화이트:세븐스 드워프 : V&VI 2:crit_rate',
            blockers,
        )
        self.assertIn(
            'weapon_change:스노우 화이트:세븐스 드워프 : I', blockers
        )
        self.assertIn(
            'normal_delivery:스노우 화이트:세븐스 드워프 : I 2:pierce_enabled',
            blockers,
        )
        self.assertIn(
            'normal_delivery:헬름 : 아쿠아마린:이지스 캐논 견제 사격 2:received_dmg_pct',
            blockers,
        )

    def test_fast_activation_times_match_moris_outer_tick_observation(self):
        moris_squad, compiled, effect = self._compiled()
        duration = 70.0
        policy = compile_burst_policy(
            moris_squad, compiled, {'duration': duration}
        )
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
            if (
                effect_id == effect.effect_id
                and effect_id in result.activated_effect_ids
            ):
                fast_times.append(time)
            return result

        with patch.object(TriggerDispatcher, 'dispatch_periodic', new=traced):
            BurstRuntime(compiled, policy).run(duration=duration)

        moris = simulate(
            moris_squad,
            config={'duration': duration, 'rng_mode': 'expected'},
            verbose=True,
        )
        moris_times = [
            row.t
            for row in moris.log.buff_events
            if row.kind == 'activate'
            and row.name == '세븐스 드워프 : V&VI 2'
        ]
        self.assertEqual(len(fast_times), 3, fast_times)
        self.assertEqual(len(moris_times), 3, moris_times)
        for actual, expected in zip(fast_times, moris_times):
            self.assertAlmostEqual(actual, expected, places=9)

    def test_other_periodic_shapes_remain_fail_closed(self):
        _moris, compiled, _effect = self._compiled()
        helm = next(
            i for i, m in enumerate(compiled.members)
            if m.name == '헬름 : 아쿠아마린'
        )
        enemy_stack = next(
            e for e in compiled.members[helm].effects
            if e.name == '이지스 캐논 견제 사격 2'
        )
        self.assertFalse(
            TriggerDispatcher._periodic_finite_self_crit_shape_supported(
                enemy_stack
            )
        )
        self.assertFalse(TriggerDispatcher.is_executable_effect(enemy_stack))


if __name__ == '__main__':
    unittest.main()
