from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.scheduler import EventScheduler
from fast_engine.engine.score import StaticNormalAttackObserver, static_score_blockers
from fast_engine.engine.state import StateStore
from fast_engine.engine.target_scope import possible_ally_targets


class MirandaLazyRankBulletLifetimeTests(unittest.TestCase):
    TEAM = "레이드_헬름아쿠아스노우"
    ORACLE = (
        (3.399999999999993, "스노우 화이트"),
        (21.58333333333339, "에이다"),
        (37.56666666666582, "스노우 화이트"),
        (50.94999999999839, "에이다"),
        (64.33333333333097, "스노우 화이트"),
    )

    @classmethod
    def _compiled(cls):
        moris = spec.build_squad(list(snapshot.SQUADS[cls.TEAM]["members"]))
        compiled = compile_moris_squad(moris)
        miranda = next(i for i,m in enumerate(compiled.members) if m.name == "미란다")
        wake = next(e for e in compiled.members[miranda].effects if e.name == "웨이크업! 4")
        return moris, compiled, wake

    def test_public_shape_closes_rank_timing_blocker(self):
        _moris, compiled, wake = self._compiled()
        self.assertTrue(TriggerDispatcher._lazy_rank_one_bullet_shape_supported(wake))
        self.assertEqual(wake.parameters.get("duration_bullets"), 1)
        self.assertEqual(static_score_blockers(compiled), ())

    def test_public_target_trace_and_one_shot_consumption_match_oracle(self):
        moris, compiled, wake = self._compiled()
        duration = 70.0
        policy = compile_burst_policy(moris, compiled, {"duration": duration, "rng_mode": "expected"})
        enemy = EnemyStaticProfile(defense=31784.0, duration=duration)
        sink = SimpleDamageScoreSink(compiled, enemy)
        activations = []
        removals = []
        orig_activate_one = ActiveEffectStore._activate_one
        orig_consume = ActiveEffectStore.consume_dynamic_bullet

        def traced_activate_one(store, effect, target, cohort, now, scheduler, **kwargs):
            row = orig_activate_one(store, effect, target, cohort, now, scheduler, **kwargs)
            if effect.effect_id == wake.effect_id:
                activations.append((float(now), store.squad.members[target].name))
            return row

        def traced_consume(store, target, *, now, count=1):
            removed = orig_consume(store, target, now=now, count=count)
            if wake.effect_id in removed:
                removals.append((float(now), store.squad.members[target].name))
            return removed

        with patch.object(ActiveEffectStore, "_activate_one", new=traced_activate_one), patch.object(ActiveEffectStore, "consume_dynamic_bullet", new=traced_consume):
            runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
            observer = StaticNormalAttackObserver(runtime, duration=duration)
            for actor in possible_ally_targets(compiled, wake):
                self.assertTrue(runtime.dispatcher.effects.dynamic_bullet_lifetime_supported(actor))
            runtime.run(duration=duration, score_observer=observer)

        self.assertEqual(len(activations), len(self.ORACLE))
        for actual, expected in zip(activations, self.ORACLE):
            self.assertAlmostEqual(actual[0], expected[0], places=9)
            self.assertEqual(actual[1], expected[1])
        self.assertEqual([name for _,name in removals], [name for _,name in self.ORACLE])
        self.assertEqual(len(removals), len(self.ORACLE))
        for (activated, name), (expired, expired_name) in zip(activations, removals):
            self.assertEqual(name, expired_name)
            self.assertGreater(expired, activated)

    def test_neighboring_bullet_rank_shapes_remain_fail_closed(self):
        _moris, _compiled, wake = self._compiled()
        two = replace(wake, parameters={**wake.parameters, "duration_bullets": 2})
        timed = replace(wake, duration=5.0)
        two_targets = replace(wake, target_spec=replace(wake.target_spec, count=2))
        self.assertFalse(TriggerDispatcher._lazy_rank_one_bullet_shape_supported(two))
        self.assertFalse(TriggerDispatcher._lazy_rank_one_bullet_shape_supported(timed))
        self.assertFalse(TriggerDispatcher._lazy_rank_one_bullet_shape_supported(two_targets))

    def test_deferred_bullet_target_without_live_cadence_fails_closed(self):
        _moris, compiled, wake = self._compiled()
        store = ActiveEffectStore(compiled, StateStore.from_compiled_squad(compiled))
        scheduler = EventScheduler()
        target = next(i for i,m in enumerate(compiled.members) if m.name == "스노우 화이트")
        store.attach_lazy_target_resolver(lambda _effect, _activated, _now: (target,))
        store.defer_target_group(wake, 3.4, scheduler)
        with self.assertRaisesRegex(NotImplementedError, "lazy duration_bullets requires live recipient cadence"):
            store.sum_stat(target, "crit_rate", now=3.4)


if __name__ == "__main__":
    unittest.main()
