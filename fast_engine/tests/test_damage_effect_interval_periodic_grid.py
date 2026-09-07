from __future__ import annotations

import unittest
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers


TEAM = '레이드_헬름아쿠아스노우'


def _compiled():
    moris = spec.build_squad(list(snapshot.SQUADS[TEAM]['members']))
    return moris, compile_moris_squad(moris)


class EffectIntervalPeriodicGridTests(unittest.TestCase):
    def test_public_modifier_is_exact_owned_shape(self):
        _moris, squad = _compiled()
        ada = next(i for i, member in enumerate(squad.members) if member.name == '에이다')
        modifier = next(
            effect for effect in squad.members[ada].effects
            if (effect.stat or '') == 'effect_interval'
        )
        self.assertTrue(
            TriggerDispatcher._finite_self_effect_interval_shape_supported(modifier)
        )
        blockers = static_score_blockers(squad)
        self.assertNotIn(
            'periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval',
            blockers,
        )
        self.assertNotIn('normal_state:미란다:웨이크업! 4:rank_target_timing', blockers)
        self.assertEqual(blockers, ())

    def test_public_fast_grenade_activation_frames_match_moris(self):
        moris, squad = _compiled()
        ada = next(i for i, member in enumerate(squad.members) if member.name == '에이다')
        grenade = next(
            effect for effect in squad.members[ada].effects
            if effect.name == '섬광 수류탄 투척'
        )
        duration = 35.0
        config = {'duration': duration, 'rng_mode': 'expected'}
        enemy = dict(DEFAULT_ENEMY)
        policy = compile_burst_policy(moris, squad, config)
        enemy_profile = EnemyStaticProfile(
            defense=float(enemy.get('def', 31784.0)),
            element=enemy.get('code'),
            core_px=float(enemy.get('core_px', 0.0) or 0.0),
            duration=duration,
        )

        fast: list[float] = []
        sink = SimpleDamageScoreSink(squad, enemy_profile)
        original_fast = TriggerDispatcher.dispatch_periodic

        def traced_fast(dispatcher, effect_id, rule_index, *, time, context):
            result = original_fast(
                dispatcher, effect_id, rule_index, time=time, context=context
            )
            if effect_id == grenade.effect_id and effect_id in result.activated_effect_ids:
                fast.append(float(time))
            return result

        with patch.object(TriggerDispatcher, 'dispatch_periodic', new=traced_fast):
            BurstRuntime(
                squad, policy, enemy_profile, damage_sink=sink
            ).run(duration=duration)

        moris_times: list[float] = []
        original_activate = BuffManager._activate

        def traced_moris(self, eff, caster, t, suppress_event=False):
            if caster == '에이다' and eff.get('name') == '섬광 수류탄 투척':
                moris_times.append(float(t))
            return original_activate(
                self, eff, caster, t, suppress_event=suppress_event
            )

        with patch.object(BuffManager, '_activate', new=traced_moris):
            simulate(moris, config=config, enemy=enemy, verbose=False)

        self.assertEqual(len(fast), len(moris_times))
        for fast_time, moris_time in zip(fast, moris_times):
            self.assertAlmostEqual(fast_time, moris_time, places=9)
        self.assertAlmostEqual(fast[5], 21.783333333333378, places=9)
        self.assertAlmostEqual(fast[6], 22.78333333333332, places=9)

    def test_neighboring_interval_shapes_remain_unowned(self):
        _moris, squad = _compiled()
        ada = next(i for i, member in enumerate(squad.members) if member.name == '에이다')
        modifier = next(
            effect for effect in squad.members[ada].effects
            if (effect.stat or '') == 'effect_interval'
        )
        from dataclasses import replace

        for changed in (
            replace(modifier, target_spec=replace(modifier.target_spec, mode=__import__('fast_engine.engine.targets', fromlist=['TargetMode']).TargetMode.ALL_ALLIES)),
            replace(modifier, duration=None),
            replace(modifier, parameters={}),
            replace(modifier, max_stack=2.0),
        ):
            with self.subTest(changed=changed):
                self.assertFalse(
                    TriggerDispatcher._finite_self_effect_interval_shape_supported(changed)
                )


if __name__ == '__main__':
    unittest.main()
