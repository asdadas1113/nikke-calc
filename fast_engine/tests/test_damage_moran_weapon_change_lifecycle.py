from __future__ import annotations

from dataclasses import replace
import unittest

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.score import (
    _temporary_self_rapid_weapon_change_score_supported,
    static_score_blockers,
)


MORAN_TEAMS = (
    "스쿼드4",
    "레이드_이브레이븐",
    "레이드_아니스서머메이든",
    "레이드_브리드디젤",
    "레이드_트리나홍련",
)


class MoranWeaponChangeLifecycleTest(unittest.TestCase):
    def _compiled(self, team="스쿼드4"):
        case = snapshot.SQUADS[team]
        return compile_moris_squad(spec.build_squad(list(case["members"])))

    @staticmethod
    def _producer(compiled):
        return next(
            effect for effect in compiled.effects
            if effect.effect_type == "weapon_change"
            and compiled.members[effect.actor].name == "목단"
        )

    def test_exact_public_moran_weapon_change_blockers_are_owned(self):
        for team in MORAN_TEAMS:
            with self.subTest(team=team):
                compiled = self._compiled(team)
                self.assertFalse(any(
                    blocker.startswith("weapon_change:목단:")
                    for blocker in static_score_blockers(compiled)
                ))
                effect = self._producer(compiled)
                self.assertTrue(_temporary_self_rapid_weapon_change_score_supported(compiled, effect))

    def test_effective_smg_view_and_mode_edges_preserve_global_hit_phase(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        actor = effect.actor
        enemy = EnemyStaticProfile(defense=31784.0, duration=20.0, core_px=0.0)
        damage_sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(duration=20.0, first_burst_time=3.0),
            enemy,
            damage_sink=damage_sink,
        )
        runtime.weapons._rapid_reload.attach_score_sink((), lambda *_: None) if False else None
        # Score wiring normally selects the actor. Direct lifecycle tests attach it explicitly.
        runtime.weapons.attach_score_block_sink((actor,), lambda *_: None)
        runtime.weapons.start(0.0)
        rapid = runtime.weapons._rapid_reload
        st = rapid._states[actor]
        st.hit_count = 37
        st.pellet_count = 37
        st.dispatched_hit_count = 35
        st.dispatched_pellet_count = 35

        runtime.dispatcher.dispatch(BurstSignal(3.05, "burst_cast", actor, actor))
        runtime.weapons.sync(3.05)
        changed = runtime.weapons.effective_weapon(actor, 3.05)
        self.assertEqual(changed["weapon_type"], "SMG")
        self.assertEqual(changed["fire_mode"], "auto")
        self.assertEqual(changed["fire_rate"], 24.0)
        self.assertEqual(changed["max_ammo"], -1)
        self.assertEqual(changed["damage_coeff"], 14.7)
        self.assertTrue(changed["_moris_frame_observed"])
        self.assertEqual(st.hit_count, 37)
        self.assertEqual(st.ammo, 999999)
        self.assertAlmostEqual(st.phase_end, 3.05, places=9)

        next_boundary = rapid._predict_next_boundary(actor)
        self.assertIsNotNone(next_boundary)
        when, expected = next_boundary
        self.assertEqual(expected, 40)
        # 3.133333... is the nominal deadline; Moris repeated-add 60 Hz
        # observes it on the next representable outer tick, 3.15.
        self.assertAlmostEqual(when, 3.15, places=8)

        # Keep nominal deadline accumulation separate from observed shot ticks.
        # Otherwise 24/s drifts by extra frames after this first crossing.
        probe = replace(st)
        shot_times = []
        for _ in range(8):
            shot_times.append(probe.phase_end)
            rapid._after_shot(probe, probe.phase_end)
        self.assertEqual(probe.hit_count, 45)
        self.assertAlmostEqual(shot_times[-1], 3.35, places=8)

        expiry = next(
            event for event in runtime.scheduler._heap
            if abs(event.time - 13.05) < 1e-8
        )
        runtime.dispatcher.handle_expiry(expiry)
        runtime.weapons.sync(13.05)
        restored = runtime.weapons.effective_weapon(actor, 13.05)
        self.assertIs(restored, compiled.members[actor].weapon)
        self.assertEqual(st.hit_count, 37)
        # Finite mode exit is a reload-complete restore in Moris: refill to
        # the live effective base-weapon maximum, including active max-ammo buffs.
        self.assertEqual(st.ammo, rapid._full_ammo(actor, 13.05))
        self.assertAlmostEqual(st.phase_end, 13.05, places=9)

    def test_live_weapon_view_is_scoped_to_actual_weapon_change_actor(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        actor = effect.actor
        enemy = EnemyStaticProfile(defense=31784.0, duration=20.0, core_px=0.0)
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(duration=20.0, first_burst_time=3.0),
            enemy,
            damage_sink=SimpleDamageScoreSink(compiled, enemy),
        )
        rapid = runtime.weapons._rapid_reload
        self.assertEqual(rapid._effective_weapon_actors, frozenset({actor}))

        mast = next(
            i for i, member in enumerate(compiled.members)
            if member.name == "마스트 : 로망틱 메이드"
        )
        self.assertNotIn(mast, rapid._effective_weapon_actors)
        self.assertIs(rapid._weapon(mast, 0.0), compiled.members[mast].weapon)

    def test_shape_rejects_wider_weapon_modes(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        for params in (
            {**effect.parameters, "max_ammo": 60},
            {**effect.parameters, "weapon_type": "AR"},
            {**effect.parameters, "skill_damage": True},
            {**effect.parameters, "duration_bullets": 10},
        ):
            with self.subTest(params=params):
                self.assertFalse(
                    _temporary_self_rapid_weapon_change_score_supported(
                        compiled, replace(effect, parameters=params)
                    )
                )

    def test_dependency_graph_rejects_missing_or_mismatched_name(self):
        compiled = self._compiled()
        effect = self._producer(compiled)
        self.assertFalse(
            _temporary_self_rapid_weapon_change_score_supported(
                compiled, replace(effect, name="unreferenced weapon state")
            )
        )

    def test_other_class_changing_weapon_changes_remain_blocked(self):
        found = False
        for name, case in snapshot.SQUADS.items():
            if str(name).startswith("지그_") or "스노우 화이트" not in case["members"]:
                continue
            compiled = compile_moris_squad(spec.build_squad(list(case["members"])))
            if any(blocker.startswith("weapon_change:스노우 화이트:") for blocker in static_score_blockers(compiled)):
                found = True
                break
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
