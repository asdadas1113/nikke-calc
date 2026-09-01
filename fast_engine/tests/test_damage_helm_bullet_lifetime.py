from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import BurstMachine, compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import SignalContext
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.scheduler import EventKind, EventScheduler
from fast_engine.engine.shot_blocks import next_static_shot_after
from fast_engine.engine.state import StateStore


NAMES = ["미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인"]


class HelmTenShotLifetimeTests(unittest.TestCase):
    @staticmethod
    def _fixture():
        squad = build_squad(NAMES)
        next(c for c in squad if c["name"] == "미하라 : 본딩 체인")["control"] = {}
        compiled = compile_moris_squad(squad)
        policy = compile_burst_policy(
            squad,
            compiled,
            {"duration": 180.0, "first_burst_time": 3.0, "rng_mode": "expected"},
        )
        helm = next(
            e for e in compiled.effects
            if e.actor == 2 and e.name == "이지스 캐논 3" and e.stat == "charge_dmg_mag_pct"
        )
        return compiled, policy, helm

    def test_helm_charge_magnitude_expires_after_tenth_shot(self):
        compiled, policy, helm = self._fixture()
        self.assertEqual(helm.parameters.get("duration_bullets"), 10)
        self.assertEqual(helm.value, 158.4)
        self.assertTrue(is_direct_damage_buff_runtime_supported(helm))

        state = StateStore.from_compiled_squad(compiled)
        scheduler = EventScheduler()
        burst = BurstMachine(compiled, policy)
        dispatcher = TriggerDispatcher(
            compiled,
            state,
            EnemyStaticProfile(defense=31784.0, duration=180.0),
            burst,
            scheduler,
        )
        now = 0.1
        self.assertTrue(dispatcher._activate(helm, now=now, context=SignalContext()))
        self.assertAlmostEqual(
            dispatcher.effects.sum_stat(2, "charge_dmg_mag_pct", now=now),
            158.4,
            places=9,
        )

        tenth = now
        for _ in range(10):
            tenth = next_static_shot_after(compiled, 2, tenth)

        expiry = scheduler.pop()
        self.assertEqual(expiry.kind, EventKind.STATE_EXPIRE)
        self.assertAlmostEqual(expiry.time, tenth, places=9)
        self.assertGreater(expiry.phase, 30)
        self.assertAlmostEqual(
            dispatcher.effects.sum_stat(2, "charge_dmg_mag_pct", now=tenth),
            158.4,
            places=9,
        )
        dispatcher.handle_expiry(expiry)
        self.assertEqual(
            dispatcher.effects.sum_stat(2, "charge_dmg_mag_pct", now=tenth),
            0.0,
        )

    def test_reactivation_resets_ten_shot_generation(self):
        compiled, policy, helm = self._fixture()
        state = StateStore.from_compiled_squad(compiled)
        scheduler = EventScheduler()
        dispatcher = TriggerDispatcher(
            compiled,
            state,
            EnemyStaticProfile(defense=31784.0, duration=180.0),
            BurstMachine(compiled, policy),
            scheduler,
        )

        self.assertTrue(dispatcher._activate(helm, now=0.1, context=SignalContext()))
        first_expiry = scheduler.pop()
        refresh = first_expiry.time - 0.01
        scheduler.now = refresh
        self.assertTrue(dispatcher._activate(helm, now=refresh, context=SignalContext()))
        second_expiry = scheduler.pop()

        dispatcher.handle_expiry(first_expiry)
        self.assertGreater(
            dispatcher.effects.sum_stat(2, "charge_dmg_mag_pct", now=first_expiry.time),
            0.0,
        )
        self.assertGreater(second_expiry.time, first_expiry.time)
        dispatcher.handle_expiry(second_expiry)
        self.assertEqual(
            dispatcher.effects.sum_stat(2, "charge_dmg_mag_pct", now=second_expiry.time),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
