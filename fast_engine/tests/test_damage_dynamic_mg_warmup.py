from __future__ import annotations

import unittest
from dataclasses import replace

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.capabilities import CapabilityDisposition, EffectCapability, EffectCategory
from fast_engine.engine.model import CompiledEffect, CompiledSquad, EnemyStaticProfile
from fast_engine.engine.normal_attack import expected_normal_block_damage
from fast_engine.engine.score import StaticNormalAttackObserver, static_normal_score_blockers, static_score_blockers
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule
from fast_engine.tests.test_damage_dynamic_reload_scoring import _member


def _effect(value: float = 100.0, duration: float = 10.0) -> CompiledEffect:
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name="live MG warmup",
        effect_type="buff",
        stat="mg_warmup_speed_pct",
        polarity="beneficial",
        target="self",
        target_spec=compile_target("self", actor_by_name={"synthetic-reload": 0}),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule("burst_cast", "burst_cast", TriggerMode.EVENT),),
        value=value,
        duration=duration,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=EffectCapability(
            character="synthetic-reload",
            index=0,
            source="synthetic",
            name="live MG warmup",
            effect_type="buff",
            stat="mg_warmup_speed_pct",
            category=EffectCategory.CADENCE_TIMELINE,
            timing_families=("burst",),
            condition_families=(),
            target_family="ally_static",
            advanced_fields=(),
            disposition=CapabilityDisposition.READY,
            blockers=(),
        ),
    )


def _squad(effect: CompiledEffect) -> CompiledSquad:
    member = _member((effect,), fire_mode="auto_warmup", weapon_type="MG")
    weapon = dict(member.weapon)
    weapon.update(
        fire_rate=1.0,
        fire_rate_max=3.0,
        warmup_bullets=4,
        warmup_cooldown_time=10.0,
        max_ammo=20,
        reload_time=10.0,
    )
    member = replace(member, weapon=weapon)
    return CompiledSquad((member,), TriggerIndex.from_effects((effect,), actor_count=1))


class DynamicMgWarmupScoringTests(unittest.TestCase):
    def test_live_warmup_speed_changes_compressed_mg_cadence(self):
        effect = _effect()
        squad = _squad(effect)
        self.assertNotIn(
            "cadence:synthetic-reload:live MG warmup:mg_warmup_speed_pct",
            static_normal_score_blockers(squad),
        )

        duration = 2.1
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
        runtime.dispatcher.effects.activate(effect, 0, 0.0, runtime.scheduler)
        observer = StaticNormalAttackObserver(runtime, duration=duration)
        result = runtime.run(duration=duration, score_observer=observer)
        score = observer.finish(events_processed=result.events_processed)

        self.assertEqual(observer.dynamic_reload_actors, (0,))
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
        # +100% warmup makes the MG warmup path 0 -> 2 -> 4.  Shots inside
        # [0, 2.1) are therefore 0.0, 1.0, 1.5, 1.833..., four total.
        # The old static-only warmup increment produced only three shots here.
        self.assertAlmostEqual(score.char_total[0], per_shot * 4.0, places=6)

    def test_asuka_public_blocker_is_removed_without_character_whitelist(self):
        names = [
            "리틀 머메이드",
            "델타 : 닌자 시프",
            "크라운",
            "아스카 : WILLE",
            "라피 : 레드 후드",
        ]
        blockers = static_score_blockers(compile_moris_squad(build_squad(names)))
        self.assertNotIn(
            "cadence:아스카 : WILLE:긴급 수복 2:mg_warmup_speed_pct",
            blockers,
        )


if __name__ == "__main__":
    unittest.main()
