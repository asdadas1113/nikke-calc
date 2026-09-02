from __future__ import annotations

import unittest
from dataclasses import replace

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import CapabilityDisposition, EffectCapability, EffectCategory
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import CompiledEffect, EnemyStaticProfile
from fast_engine.engine.score import StaticNormalAttackObserver, static_normal_score_blockers, static_score_blockers
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerMode, TriggerRule
from fast_engine.tests.test_damage_dynamic_reload_scoring import _reload_effect, _squad_many


def _last_bullet_effect() -> CompiledEffect:
    return CompiledEffect(
        effect_id=1,
        actor=0,
        actor_effect_index=1,
        source="synthetic",
        source_tag="skill",
        name="last bullet atk",
        effect_type="buff",
        stat="atk_pct",
        polarity="beneficial",
        target="self",
        target_spec=compile_target("self", actor_by_name={"synthetic-reload": 0}),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule("last_bullet", "last_bullet", TriggerMode.EVENT),),
        value=25.0,
        duration=10.0,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=EffectCapability(
            character="synthetic-reload",
            index=1,
            source="synthetic",
            name="last bullet atk",
            effect_type="buff",
            stat="atk_pct",
            category=EffectCategory.HIT_FORMULA,
            timing_families=("weapon_hit",),
            condition_families=(),
            target_family="ally_static",
            advanced_fields=(),
            disposition=CapabilityDisposition.READY,
            blockers=(),
        ),
    )


class DynamicLastBulletBoundaryTests(unittest.TestCase):
    def test_last_bullet_consumer_no_longer_blocks_dynamic_reload_owner(self):
        reload_effect = _reload_effect(duration=1.5)
        last = _last_bullet_effect()
        blockers = static_normal_score_blockers(_squad_many((reload_effect, last)))
        self.assertNotIn(
            "cadence:synthetic-reload:live reload:reload_speed_pct",
            blockers,
        )

    def test_last_bullet_fire_remains_fail_closed(self):
        reload_effect = _reload_effect(duration=1.5)
        pre = replace(
            _last_bullet_effect(),
            triggers=(TriggerRule("last_bullet_fire", "last_bullet_fire", TriggerMode.EVENT),),
        )
        blockers = static_normal_score_blockers(_squad_many((reload_effect, pre)))
        self.assertIn(
            "cadence:synthetic-reload:live reload:reload_speed_pct",
            blockers,
        )

    def test_magazine_final_shot_dispatches_last_bullet_once(self):
        reload_effect = _reload_effect(duration=1.5)
        last = _last_bullet_effect()
        squad = _squad_many((reload_effect, last))
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=1.2, first_burst_time=30.0),
            EnemyStaticProfile(defense=0.0, duration=1.2),
        )
        runtime.dispatcher.effects.activate(reload_effect, 0, 0.0, runtime.scheduler)
        observer = StaticNormalAttackObserver(runtime, duration=1.2)
        result = runtime.run(duration=1.2, score_observer=observer)
        observer.finish(events_processed=result.events_processed)
        self.assertEqual(runtime.dispatcher._activation_counts.get(1, 0), 1)
        self.assertEqual(runtime.weapons._rapid_reload._states[0].hit_count, 2)

    def test_public_privaty_reload_stays_closed_for_other_recipient_constraints(self):
        names = [
            "\ub9ac\ud2c0 \uba38\uba54\uc774\ub4dc",
            "\ud06c\ub77c\uc6b4",
            "\ub77c\ud53c : \ub808\ub4dc \ud6c4\ub4dc",
            "\uc568\ub9ac\uc2a4",
            "\ud504\ub9ac\ubc14\ud2f0",
        ]
        compiled = compile_moris_squad(build_squad(names))
        blockers = static_score_blockers(compiled)
        self.assertIn("control:\uc568\ub9ac\uc2a4", blockers)
        self.assertIn("cadence:\ud504\ub9ac\ubc14\ud2f0:EX \ub9e4\uac70\uc9c4 2:reload_speed_pct", blockers)
        self.assertIn("cadence:\ud504\ub9ac\ubc14\ud2f0:EX \ub9e4\uac70\uc9c4 3:max_ammo_pct", blockers)


if __name__ == "__main__":
    unittest.main()
