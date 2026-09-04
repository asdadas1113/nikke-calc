from __future__ import annotations

import unittest
from dataclasses import replace

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import CapabilityDisposition
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import (
    StaticNormalAttackObserver,
    static_normal_score_blockers,
    static_score_blockers,
)
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerMode, TriggerRule
from fast_engine.tests.test_damage_dynamic_charge_scoring import (
    _charge_speed_effect,
    _squad,
)


class ChargeSpeedBulletLifetimeTests(unittest.TestCase):
    @staticmethod
    def _one_shot_effect():
        base = _charge_speed_effect()
        return replace(
            base,
            value=-300.0,
            duration=None,
            parameters={"duration_bullets": 1},
            triggers=(
                TriggerRule("burst_cast", "burst_cast", TriggerMode.EVENT),
            ),
            capability=replace(
                base.capability,
                disposition=CapabilityDisposition.PLANNED,
                blockers=("field:duration_bullets",),
            ),
        )

    def test_self_burst_cast_one_shot_slows_consuming_charge_then_expires(self):
        effect = self._one_shot_effect()
        squad = _squad(effect)
        self.assertNotIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_pct",
            static_normal_score_blockers(squad),
        )
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=4.05, first_burst_time=30.0),
            EnemyStaticProfile(
                defense=0.0,
                core_uptime=0.0,
                core_px=0.0,
                duration=4.05,
            ),
        )
        observer = StaticNormalAttackObserver(runtime, duration=4.05)
        self.assertEqual(observer.dynamic_charge_actors, (0,))
        self.assertTrue(
            runtime.dispatcher.effects.dynamic_bullet_lifetime_supported(0)
        )
        runtime.dispatcher.effects.activate(
            effect, 0, 0.0, runtime.scheduler
        )

        # -300% on a 1.0 s base charge makes a 4.0 s charge. Moris
        # observes that deadline on the following outer tick, so the
        # one-shot state is still live at exactly 4.0 s.
        runtime.run(duration=4.0, score_observer=observer)
        self.assertAlmostEqual(
            runtime.dispatcher.effects.sum_stat(
                0, "charge_speed_pct", now=4.0
            ),
            -300.0,
            places=9,
        )

        # The consuming physical charge shot is scored with the state,
        # then the bullet lifetime is removed post-shot.
        result = runtime.run(duration=4.05, score_observer=observer)
        self.assertEqual(
            runtime.dispatcher.effects.sum_stat(
                0, "charge_speed_pct", now=4.05
            ),
            0.0,
        )
        score = observer.finish(events_processed=result.events_processed)
        self.assertGreater(score.char_total[0], 0.0)

    def test_weapon_bound_trigger_remains_fail_closed(self):
        effect = replace(
            self._one_shot_effect(),
            triggers=(
                TriggerRule("full_charge", "full_charge", TriggerMode.EVENT),
            ),
        )
        self.assertIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_pct",
            static_normal_score_blockers(_squad(effect)),
        )

    def test_non_integer_lifetime_remains_fail_closed(self):
        effect = replace(
            self._one_shot_effect(), parameters={"duration_bullets": 1.5}
        )
        self.assertIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_pct",
            static_normal_score_blockers(_squad(effect)),
        )

    def test_multi_bullet_lifetime_remains_fail_closed(self):
        effect = replace(
            self._one_shot_effect(), parameters={"duration_bullets": 2}
        )
        self.assertIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_pct",
            static_normal_score_blockers(_squad(effect)),
        )

    def test_non_self_target_remains_fail_closed(self):
        effect = self._one_shot_effect()
        effect = replace(
            effect,
            target="all_allies",
            target_spec=compile_target(
                "all_allies", actor_by_name={"synthetic-charge": 0}
            ),
        )
        self.assertIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_pct",
            static_normal_score_blockers(_squad(effect)),
        )

    def test_public_ada_only_removes_charge_speed_lifetime_blocker(self):
        for name in ("레이드_미하라에이다", "레이드_헬름아쿠아스노우"):
            compiled = compile_moris_squad(
                spec.build_squad(list(snapshot.SQUADS[name]["members"]))
            )
            blockers = set(static_score_blockers(compiled))
            self.assertNotIn(
                "cadence:에이다:특수 개조:charge_speed_pct", blockers
            )
            self.assertIn("control:에이다", blockers)
            self.assertIn(
                "normal_delivery:에이다:특수 개조 2:charge_dmg_pct",
                blockers,
            )
            self.assertIn(
                "skill_state_delivery:에이다:특수 개조 2:charge_dmg_pct",
                blockers,
            )

        jig = compile_moris_squad(
            spec.build_squad(list(snapshot.SQUADS["지그_리코리코"]["members"]))
        )
        jig_blockers = set(static_score_blockers(jig))
        self.assertNotIn(
            "cadence:에이다:특수 개조:charge_speed_pct", jig_blockers
        )
        self.assertFalse(
            any(
                "특수 개조 2:charge_dmg_pct" in blocker
                for blocker in jig_blockers
            )
        )


if __name__ == "__main__":
    unittest.main()
