from __future__ import annotations

import unittest
from dataclasses import replace

from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import (
    CapabilityDisposition,
    EffectCapability,
    EffectCategory,
)
from fast_engine.engine.model import (
    CompiledCharacter,
    CompiledEffect,
    CompiledSquad,
    EnemyStaticProfile,
)
from fast_engine.engine.normal_attack import expected_normal_block_damage
from fast_engine.engine.score import StaticNormalAttackObserver, static_normal_score_blockers
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule


def _ready_capability() -> EffectCapability:
    return EffectCapability(
        character="synthetic-charge",
        index=0,
        source="synthetic",
        name="live charge speed",
        effect_type="buff",
        stat="charge_speed_pct",
        category=EffectCategory.CADENCE_TIMELINE,
        timing_families=("burst",),
        condition_families=(),
        target_family="ally_static",
        advanced_fields=(),
        disposition=CapabilityDisposition.READY,
        blockers=(),
    )


def _charge_speed_effect() -> CompiledEffect:
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name="live charge speed",
        effect_type="buff",
        stat="charge_speed_pct",
        polarity="beneficial",
        target="self",
        target_spec=compile_target(
            "self",
            actor_by_name={"synthetic-charge": 0},
        ),
        conditions=(),
        condition_rules=(),
        triggers=(
            TriggerRule(
                "full_burst_start",
                "full_burst_start",
                TriggerMode.EVENT,
            ),
        ),
        value=50.0,
        duration=1.5,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=_ready_capability(),
    )


def _squad(effect: CompiledEffect) -> CompiledSquad:
    member = CompiledCharacter(
        name="synthetic-charge",
        base_atk=1000.0,
        base_def=100.0,
        base_hp=10000.0,
        element=None,
        character_class="화력형",
        squad_group=None,
        burst_stage="3",
        burst_cooldown=40.0,
        burst_regen_time=2.0,
        weapon_type="SR",
        weapon={
            "weapon_type": "SR",
            "fire_mode": "charge",
            "damage_coeff": 100.0,
            "max_ammo": 20,
            "reload_time": 2.0,
            "charge_time": 1.0,
            "full_charge_mult": 100.0,
            "core_dmg_mult": 200.0,
            "post_fire_delay": 0.0,
            "reload_start_delay": 0.0,
            "post_reload_delay": 0.0,
            "is_clip": False,
            "pellets": 1,
            "muzzles": 1,
        },
        effects=(effect,),
        skill_levels={},
        favorite_stage=0,
    )
    return CompiledSquad(
        (member,),
        TriggerIndex.from_effects((effect,), actor_count=1),
    )


class DynamicChargeScoringTests(unittest.TestCase):
    def test_live_charge_speed_uses_runtime_shots_without_static_double_count(self):
        effect = _charge_speed_effect()
        squad = _squad(effect)
        self.assertNotIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_pct",
            static_normal_score_blockers(squad),
        )

        enemy = EnemyStaticProfile(
            defense=0.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=4.0,
        )
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=4.0, first_burst_time=10.0),
            enemy,
        )
        # Activate the finite state directly so this test isolates cadence
        # replanning rather than burst-machine reachability. The effect expires
        # at 1.5 s: 50% speed produces shots at 0.5/1.0, then the in-progress
        # third charge is replanned to 2.0 and normal shots continue at 3.0.
        runtime.dispatcher.effects.activate(
            effect,
            0,
            0.0,
            runtime.scheduler,
        )
        observer = StaticNormalAttackObserver(runtime, duration=4.0)
        self.assertEqual(observer.dynamic_charge_actors, (0,))

        result = runtime.run(duration=4.0, score_observer=observer)
        score = observer.finish(events_processed=result.events_processed)

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
        self.assertAlmostEqual(score.char_total[0], per_shot * 4.0, places=6)

    def test_uncertified_charge_speed_delivery_remains_fail_closed(self):
        effect = _charge_speed_effect()
        planned = replace(
            effect.capability,
            disposition=CapabilityDisposition.PLANNED,
            blockers=("timing:weapon_hit",),
        )
        unsafe = replace(
            effect,
            triggers=(
                TriggerRule("full_charge", "full_charge", TriggerMode.EVENT),
            ),
            capability=planned,
        )
        blockers = static_normal_score_blockers(_squad(unsafe))
        self.assertIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_pct",
            blockers,
        )


if __name__ == "__main__":
    unittest.main()
