from __future__ import annotations

from dataclasses import replace
import unittest

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dynamic_rapid import DynamicRapidResidualToken
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import (
    _temporary_self_charge_to_rapid_weapon_change_score_supported,
    static_score_blockers,
)
from fast_engine.engine.weapon import DynamicWeaponToken

TEAM = "레이드_네온벨벳"


class ChargeToRapidWeaponChangeTest(unittest.TestCase):
    def _compiled(self):
        case = snapshot.SQUADS[TEAM]
        return compile_moris_squad(spec.build_squad(list(case["members"])))

    @staticmethod
    def _producer(compiled):
        return next(
            effect for effect in compiled.effects
            if effect.effect_type == "weapon_change"
            and compiled.members[effect.actor].name == "벨벳"
        )

    def _runtime(self, duration=20.0):
        compiled = self._compiled()
        effect = self._producer(compiled)
        actor = effect.actor
        enemy = EnemyStaticProfile(defense=31784.0, duration=duration, core_px=0.0)
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(duration=duration, first_burst_time=3.0),
            enemy,
            damage_sink=SimpleDamageScoreSink(compiled, enemy),
        )
        charge_times = []
        runtime.weapons.attach_score_shot_sink(
            (actor,), lambda _a, t: charge_times.append(float(t))
        )
        runtime.weapons.attach_score_block_sink((actor,), lambda *_: None)
        runtime.weapons.start(0.0)
        return compiled, effect, actor, runtime, charge_times

    def _enter_first_mode(self, runtime, actor):
        charge = runtime.weapons._states[actor]
        charge.full_charge_count = 2
        charge.dispatched_count = 2
        charge.ammo = 12
        charge.phase = "charging"
        charge.charge_start = 2.8
        charge.phase_end = 3.8
        runtime.weapons._invalidate(charge)
        runtime.dispatcher.dispatch(
            BurstSignal(3.0, "hit_count", actor, actor, count_increment=2)
        )
        runtime.dispatcher.dispatch(BurstSignal(3.2, "burst_cast", actor, actor))
        runtime.weapons.sync(3.2)
        return charge

    def test_exact_public_shape_owned_and_modernia_stays_blocked(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        self.assertTrue(
            _temporary_self_charge_to_rapid_weapon_change_score_supported(compiled, effect)
        )
        self.assertNotIn("weapon_change:벨벳:깔끔한 마무리", static_score_blockers(compiled))
        case = snapshot.SQUADS["레이드_작열짬"]
        modernia = compile_moris_squad(spec.build_squad(list(case["members"])))
        self.assertIn("weapon_change:모더니아:섬멸 모드", static_score_blockers(modernia))

    def test_effective_mg_view_and_whole_hit_phase_seed(self):
        compiled, effect, actor, runtime, _ = self._runtime()
        charge = self._enter_first_mode(runtime, actor)
        changed = runtime.weapons.effective_weapon(actor, 3.2)
        self.assertEqual(changed["weapon_type"], "MG")
        self.assertEqual(changed["fire_mode"], "auto_warmup")
        self.assertEqual(changed["fire_rate"], 1.0)
        self.assertEqual(changed["fire_rate_max"], 70.0)
        self.assertAlmostEqual(changed["warmup_bullets"], 41.39917201655967)
        self.assertEqual(changed["max_ammo"], -1)
        self.assertEqual(changed["damage_coeff"], 7.0)
        self.assertTrue(changed["_moris_frame_observed"])
        rapid = runtime.weapons._rapid_reload
        st = rapid._states[actor]
        self.assertEqual((st.hit_count, st.dispatched_hit_count), (2, 2))
        self.assertEqual(st.ammo, 999999)
        self.assertAlmostEqual(st.phase_end, 3.2, places=8)
        self.assertEqual(charge.phase, "charging")
        self.assertAlmostEqual(charge.phase_end, 3.8, places=8)

    def test_first_session_matches_moris_451_shots_and_first_hit50(self):
        _, _, actor, runtime, _ = self._runtime()
        self._enter_first_mode(runtime, actor)
        rapid = runtime.weapons._rapid_reload
        st = rapid._states[actor]
        row = rapid._predict_next_boundary(actor)
        self.assertIsNotNone(row)
        when, expected = row
        self.assertEqual(expected, 50)
        self.assertAlmostEqual(when, 6.466666666666649, places=8)
        probe = replace(st)
        times = []
        while probe.phase_end < 13.2 - 1e-9:
            times.append(probe.phase_end)
            rapid._after_shot(probe, probe.phase_end)
        self.assertEqual(len(times), 451)
        self.assertAlmostEqual(times[0], 3.1999999999999935, places=8)
        self.assertAlmostEqual(times[-1], 13.183333333333568, places=8)
        self.assertEqual(probe.hit_count, 453)

    def test_exit_flushes_residual_before_live_full_same_frame_sr_resume(self):
        _, effect, actor, runtime, charge_times = self._runtime()
        charge = self._enter_first_mode(runtime, actor)
        rapid = runtime.weapons._rapid_reload
        st = rapid._states[actor]
        st.hit_count = 453
        st.dispatched_hit_count = 450
        st.ammo = 999548
        st.phase = "firing"
        st.phase_end = 13.2
        # In a real session the nine 50-hit crossings have already advanced
        # dispatcher count from the pre-mode 2 to 450. This direct fixture
        # jumps the cadence state, so mirror that already-dispatched phase.
        runtime.dispatcher._event_counts[(actor, "hit_count")] = 450
        expiry = next(
            event for event in runtime.scheduler._heap
            if getattr(event.payload, "effect_id", None) == effect.effect_id
        )
        runtime.dispatcher.handle_expiry(expiry)
        runtime.weapons.sync(expiry.time)
        residual = next(
            event for event in runtime.scheduler._heap
            if isinstance(event.payload, DynamicRapidResidualToken)
        )
        resumed = next(
            event for event in runtime.scheduler._heap
            if isinstance(event.payload, DynamicWeaponToken)
            and event.payload.actor == actor
            and event.time >= 13.2 - 1e-8
        )
        self.assertLess(residual.time, resumed.time)
        self.assertAlmostEqual(resumed.time, 13.200000000000236, places=8)
        self.assertEqual(charge.ammo, 14)
        boundary = runtime.weapons.handle_boundary(residual)
        self.assertEqual(
            [(x.event_key, x.count_increment) for x in boundary.signals],
            [("hit_count", 3)],
        )
        runtime.dispatcher.dispatch(
            BurstSignal(residual.time, "hit_count", actor, actor, count_increment=3)
        )
        self.assertEqual(runtime.dispatcher.event_count(actor, "hit_count"), 453)
        shot = runtime.weapons.handle_boundary(resumed)
        self.assertIsNotNone(shot)
        self.assertEqual(charge.ammo, 13)
        self.assertEqual(charge_times, [resumed.time])

    def test_raw_second_expiry_reanchors_to_next_outer_tick(self):
        _, effect, actor, runtime, _ = self._runtime(duration=30.0)
        charge = runtime.weapons._states[actor]
        charge.weapon_change_id = effect.effect_id
        charge.phase = "charging"
        charge.charge_start = 14.733333333333695
        charge.phase_end = 15.733333333333695
        charge.ammo = 13
        runtime.weapons._invalidate(charge)
        runtime.weapons.sync(25.733333333333697)
        self.assertAlmostEqual(charge.phase_end, 25.74999999999982, places=8)
        self.assertEqual(charge.ammo, 14)

    def test_neighboring_wider_modes_fail_closed(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        variants = (
            replace(effect, duration=None),
            replace(effect, duration=0.0),
            replace(effect, parameters={**effect.parameters, "max_ammo": 300}),
            replace(effect, parameters={**effect.parameters, "weapon_type": "SMG"}),
            replace(effect, parameters={**effect.parameters, "skill_damage": True}),
            replace(effect, parameters={**effect.parameters, "favorite": 1}),
        )
        for candidate in variants:
            with self.subTest(candidate=candidate):
                self.assertFalse(
                    _temporary_self_charge_to_rapid_weapon_change_score_supported(
                        compiled, candidate
                    )
                )


if __name__ == "__main__":
    unittest.main()
