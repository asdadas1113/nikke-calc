from __future__ import annotations

import unittest
from dataclasses import replace

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy, compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.normal_attack import expected_normal_block_damage
from fast_engine.engine.score import (
    StaticNormalAttackObserver,
    score_static_squad,
    static_normal_score_blockers,
    static_score_blockers,
)
from fast_engine.engine.triggers import TriggerIndex
from fast_engine.tests.test_damage_dynamic_reload_scoring import _member


REAL_NAMES = [
    "미란다",
    "브리드 : 사일런트 트랙",
    "헬름",
    "루주",
    "미하라 : 본딩 체인",
]


def _controlled_squad(*, extra_control: dict | None = None) -> CompiledSquad:
    base = _member(())
    control = {"cover": {"policy": "own_full_burst"}}
    if extra_control:
        control.update(extra_control)
    weapon = {
        **base.weapon,
        "control": control,
        "reload_start_delay": 1.0,
    }
    member = replace(base, weapon=weapon)
    return CompiledSquad(
        (member,),
        TriggerIndex.from_effects((), actor_count=1),
    )


class RapidCoverControlTests(unittest.TestCase):
    def test_supported_control_becomes_dynamic_and_manual_cover_reload_has_no_empty_delay(self):
        squad = _controlled_squad()
        self.assertEqual(static_normal_score_blockers(squad), ())

        duration = 3.5
        enemy = EnemyStaticProfile(
            defense=0.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=duration,
        )
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=duration, first_burst_time=10.0),
            enemy,
        )
        observer = StaticNormalAttackObserver(runtime, duration=duration)
        self.assertEqual(observer.dynamic_reload_actors, (0,))
        runtime.weapons.start(0.0)

        # Two shots at 0.0 and 0.5 empty the two-round magazine. The ordinary
        # empty-magazine path would wait until 1.0 and then pay the synthetic
        # 1.0s reload-start delay. Entering cover at 0.75 instead starts the
        # manual reload immediately and intentionally skips that empty delay.
        observer.consume_until(0.75, inclusive=False)
        entered = runtime.weapons.begin_full_burst(0.75, (True,), 2.75)
        self.assertEqual(entered, (0,))
        observer.consume_until(duration, inclusive=False)
        score = observer.finish(events_processed=0)

        terms = observer.resolver.resolve(0, now=0.25)
        per_shot = expected_normal_block_damage(
            observer.specs[0],
            shot_count=1,
            base_atk=squad.members[0].base_atk,
            enemy_def=enemy.defense,
            terms=terms,
            core_prob=0.0,
            is_full_burst=False,
            is_optimal_range=False,
        )
        # Cover reload completes exactly at 2.75, where cover also ends, so the
        # actor may fire on that same boundary. Shots: 0.0, 0.5, 2.75, 3.25.
        self.assertAlmostEqual(score.char_total[0], per_shot * 4.0, places=6)

    def test_other_control_shapes_stay_fail_closed(self):
        squad = _controlled_squad(extra_control={"tap_fire": {"rate": 3.6}})
        self.assertEqual(
            static_normal_score_blockers(squad),
            ("control:synthetic-reload",),
        )

    def test_real_miranda_mihara_squad_clears_last_static_blocker(self):
        moris = build_squad(REAL_NAMES)
        compiled = compile_moris_squad(moris)
        policy = compile_burst_policy(
            moris,
            compiled,
            {"duration": 30.0, "first_burst_time": 3.0, "rng_mode": "expected"},
        )
        enemy = EnemyStaticProfile(
            defense=31784.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=30.0,
        )

        self.assertEqual(
            compiled.members[4].weapon.get("control"),
            {"cover": {"policy": "own_full_burst"}},
        )
        self.assertEqual(static_score_blockers(compiled), ())
        score = score_static_squad(compiled, policy, enemy, duration=30.0)
        self.assertGreater(score.squad_total, 0.0)


if __name__ == "__main__":
    unittest.main()
