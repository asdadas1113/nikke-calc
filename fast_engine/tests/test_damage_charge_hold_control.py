from __future__ import annotations

import unittest
from dataclasses import replace

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.frame_lattice import moris_observed_tick
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.scheduler import EventKind
from fast_engine.engine.score import (
    StaticNormalAttackObserver,
    static_normal_score_blockers,
    static_score_blockers,
)
from fast_engine.engine.triggers import TriggerIndex
from fast_engine.engine.weapon import is_supported_charge_hold_control
from fast_engine.tests.test_damage_dynamic_charge_scoring import (
    _charge_speed_effect,
    _squad,
)


def _controlled_squad(
    *,
    mixed: bool = False,
    cover_during_delay: bool = False,
    include_speed: bool = False,
) -> CompiledSquad:
    effect = _charge_speed_effect()
    base = _squad(effect).members[0]
    control = {"hold": {"policy": "own_full_burst", "lead": 0.5}}
    if mixed:
        control["tap_fire"] = {"rate": 3.6, "release": 0.03}
    effects = (effect,) if include_speed else ()
    member = replace(
        base,
        effects=effects,
        weapon={
            **base.weapon,
            "control": control,
            "cover_during_delay": cover_during_delay,
        },
    )
    return CompiledSquad(
        (member,),
        TriggerIndex.from_effects(effects, actor_count=1),
    )


class ChargeHoldControlTests(unittest.TestCase):
    def test_pure_hold_latches_until_observed_release_and_survives_speed_change(self):
        squad = _controlled_squad(include_speed=True)
        self.assertTrue(is_supported_charge_hold_control(squad.members[0]))
        self.assertEqual(static_normal_score_blockers(squad), ())

        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=4.0, first_burst_time=10.0),
            EnemyStaticProfile(
                defense=0.0,
                core_uptime=0.0,
                core_px=0.0,
                duration=4.0,
            ),
        )
        observer = StaticNormalAttackObserver(runtime, duration=4.0)
        self.assertEqual(observer.dynamic_charge_actors, (0,))

        shot_times: list[float] = []
        original_sink = runtime.weapons._score_shot_sink
        self.assertIsNotNone(original_sink)
        runtime.weapons._score_shot_sink = lambda actor, t: (
            shot_times.append(t),
            original_sink(actor, t),
        )[1]

        runtime.weapons.start(0.0)
        self.assertEqual(
            runtime.weapons.begin_full_burst(0.2, (True,), 3.0),
            (0,),
        )
        runtime.weapons.advance_to(1.2, inclusive=False)
        st = runtime.weapons._states[0]
        self.assertTrue(st.charge_latched)
        release = st.phase_end
        self.assertAlmostEqual(
            release,
            moris_observed_tick(2.5, horizon=4.0),
            places=9,
        )
        self.assertEqual(st.ammo, 20)

        speed = squad.members[0].effects[0]
        runtime.dispatcher.effects.activate(
            speed,
            0,
            1.2,
            runtime.scheduler,
        )
        runtime.weapons.sync(1.2)
        self.assertTrue(st.charge_latched)
        self.assertAlmostEqual(st.phase_end, release, places=9)

        while (
            runtime.scheduler
            and (runtime.scheduler.peek_time() or 99.0) <= release + 1e-9
        ):
            event = runtime.scheduler.pop()
            if event.kind is EventKind.WEAPON_BOUNDARY:
                boundary = runtime.weapons.handle_boundary(event)
                if boundary is not None:
                    runtime.weapons.sync(event.time)

        self.assertEqual(len(shot_times), 1)
        self.assertAlmostEqual(shot_times[0], release, places=9)
        self.assertEqual(st.ammo, 19)

    def test_cover_during_delay_is_not_blanket_rejected(self):
        squad = _controlled_squad(cover_during_delay=True)
        self.assertTrue(is_supported_charge_hold_control(squad.members[0]))
        self.assertEqual(static_normal_score_blockers(squad), ())

    def test_mixed_tap_and_hold_stays_fail_closed(self):
        squad = _controlled_squad(mixed=True)
        self.assertFalse(is_supported_charge_hold_control(squad.members[0]))
        self.assertEqual(
            static_normal_score_blockers(squad),
            ("control:synthetic-charge",),
        )

    def test_hold_only_applies_when_actor_cast_in_cycle(self):
        squad = _controlled_squad()
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=4.0, first_burst_time=10.0),
            EnemyStaticProfile(
                defense=0.0,
                core_uptime=0.0,
                core_px=0.0,
                duration=4.0,
            ),
        )
        observer = StaticNormalAttackObserver(runtime, duration=4.0)
        runtime.weapons.start(0.0)
        self.assertEqual(
            runtime.weapons.begin_full_burst(0.2, (False,), 3.0),
            (),
        )
        runtime.weapons.advance_to(1.2, inclusive=False)
        self.assertFalse(runtime.weapons._states[0].charge_latched)

    def test_public_ada_control_unlocks_existing_one_shot_damage_delivery(self):
        for name in ("레이드_미하라에이다", "레이드_헬름아쿠아스노우"):
            compiled = compile_moris_squad(
                spec.build_squad(list(snapshot.SQUADS[name]["members"]))
            )
            ada = next(
                member for member in compiled.members if member.name == "에이다"
            )
            self.assertTrue(is_supported_charge_hold_control(ada))
            blockers = set(static_score_blockers(compiled))
            self.assertNotIn("control:에이다", blockers)
            self.assertNotIn(
                "cadence:에이다:특수 개조:charge_speed_pct",
                blockers,
            )
            self.assertNotIn(
                "normal_delivery:에이다:특수 개조 2:charge_dmg_pct",
                blockers,
            )
            self.assertNotIn(
                "skill_state_delivery:에이다:특수 개조 2:charge_dmg_pct",
                blockers,
            )


if __name__ == "__main__":
    unittest.main()
