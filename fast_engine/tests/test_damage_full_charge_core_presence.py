from __future__ import annotations

import unittest
from dataclasses import replace

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.triggers import compile_trigger_rule


class FullChargeCorePresenceDamageStateTests(unittest.TestCase):
    STATE = "차분한 수심 2"

    def setUp(self):
        self.moris_squad = build_squad(["리버렐리오"])
        self.compiled = compile_moris_squad(self.moris_squad, require_five=False)
        self.effect = next(
            effect
            for effect in self.compiled.members[0].effects
            if effect.name == self.STATE and (effect.stat or "") == "atk_dmg_pct"
        )

    def _policy(self, duration: float):
        return compile_burst_policy(
            self.moris_squad,
            self.compiled,
            {
                "duration": duration,
                "first_burst_time": 99.0,
                "rng_mode": "expected",
            },
        )

    def _shot_state_trace(self, core_px: float, duration: float):
        enemy = EnemyStaticProfile(
            core_px=core_px,
            core_uptime=1.0 if core_px >= 1.0 else 0.0,
            duration=duration,
        )
        runtime = BurstRuntime(self.compiled, self._policy(duration), enemy)
        rows = []

        def observe(actor: int, now: float) -> None:
            rows.append(
                (
                    now,
                    runtime.dispatcher.effects.has_named_state(
                        actor, self.STATE, now=now
                    ),
                )
            )

        runtime.weapons.attach_score_shot_sink((0,), observe)
        runtime.run(duration=duration)
        return rows

    def test_only_raw_full_charge_core_presence_shape_is_opened(self):
        self.assertTrue(is_direct_damage_buff_runtime_supported(self.effect))
        self.assertTrue(TriggerDispatcher.is_executable_effect(self.effect))

        burst_cast = replace(
            self.effect,
            triggers=(compile_trigger_rule("burst_cast"),),
        )
        self.assertFalse(is_direct_damage_buff_runtime_supported(burst_cast))

        charge_count = replace(
            self.effect,
            triggers=(compile_trigger_rule("full_charge_count:2"),),
        )
        self.assertFalse(is_direct_damage_buff_runtime_supported(charge_count))

    def test_missing_explicit_core_geometry_fails_closed(self):
        with self.assertRaisesRegex(
            NotImplementedError,
            "requires explicit enemy.core_px",
        ):
            BurstRuntime(
                self.compiled,
                self._policy(3.0),
                EnemyStaticProfile(duration=3.0),
            )

    def test_core_absent_never_activates_state(self):
        rows = self._shot_state_trace(0.0, 3.0)
        self.assertGreaterEqual(len(rows), 2)
        self.assertFalse(any(active for _time, active in rows))

    def test_core_present_activates_after_triggering_shot(self):
        rows = self._shot_state_trace(10.0, 3.0)
        self.assertGreaterEqual(len(rows), 2)
        self.assertFalse(rows[0][1], rows[:2])
        self.assertTrue(rows[1][1], rows[:2])

    def test_repeated_full_charge_hits_refresh_sixty_second_state(self):
        rows = self._shot_state_trace(10.0, 66.0)
        first_time = rows[0][0]
        after_original_expiry = [
            (time, active) for time, active in rows if time > first_time + 60.0
        ]
        self.assertTrue(after_original_expiry)
        self.assertTrue(all(active for _time, active in after_original_expiry))


if __name__ == "__main__":
    unittest.main()
