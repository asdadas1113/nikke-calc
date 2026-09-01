from __future__ import annotations

import unittest

from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import (
    CapabilityDisposition,
    EffectCapability,
    EffectCategory,
)
from fast_engine.engine.damage import DamageTerms
from fast_engine.engine.damage_events import expected_damage_event
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import (
    CompiledCharacter,
    CompiledEffect,
    CompiledSquad,
    EnemyStaticProfile,
)
from fast_engine.engine.targets import TargetMode, TargetSpec
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule


def _capability(effect_type: str, stat: str) -> EffectCapability:
    return EffectCapability(
        character="synthetic",
        index=0,
        source="synthetic",
        name=stat,
        effect_type=effect_type,
        stat=stat,
        category=(
            EffectCategory.DAMAGE_EVENT
            if effect_type == "damage"
            else EffectCategory.HIT_FORMULA
        ),
        timing_families=("burst",),
        condition_families=(),
        target_family="enemy" if effect_type == "damage" else "ally_static",
        advanced_fields=(),
        disposition=CapabilityDisposition.PLANNED,
        blockers=("synthetic",),
    )


def _weapon() -> dict:
    return {
        "weapon_type": "AR",
        "fire_mode": "auto",
        "max_ammo": 60,
        "reload_time": 1.0,
        "fire_rate": 10.0,
        "fire_rate_max": None,
        "warmup_bullets": 1.0,
        "warmup_cooldown_time": 1.0,
        "post_fire_delay": 0.0,
        "post_reload_delay": 0.0,
        "reload_start_delay": 0.0,
        "cover_during_delay": False,
        "charge_time": 0.0,
        "pellets": 1,
        "muzzles": 1,
        "is_clip": False,
        "damage_coeff": 60.0,
        "core_dmg_mult": 200.0,
        "full_charge_mult": 100.0,
        "normal_hit_coeff": 1.0,
    }


def _member(name: str, stage: str, effects=()) -> CompiledCharacter:
    return CompiledCharacter(
        name=name,
        base_atk=100000.0,
        base_def=10000.0,
        base_hp=1000000.0,
        element=None,
        character_class="화력형",
        squad_group=None,
        burst_stage=stage,
        burst_cooldown=20.0,
        burst_regen_time=2.0,
        weapon_type="AR",
        weapon=_weapon(),
        effects=tuple(effects),
        skill_levels={},
        favorite_stage=0,
    )


def _pending_damage(*, effect_id: int = 0, actor_effect_index: int = 0) -> CompiledEffect:
    return CompiledEffect(
        effect_id=effect_id,
        actor=2,
        actor_effect_index=actor_effect_index,
        source="skill3",
        source_tag="skill",
        name="synthetic B3 pending",
        effect_type="damage",
        stat="bonus_damage",
        polarity=None,
        target="enemy",
        target_spec=TargetSpec("enemy", TargetMode.ENEMY),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule("burst_cast", "burst_cast", TriggerMode.EVENT),),
        value=500.0,
        duration=None,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=_capability("damage", "bonus_damage"),
    )


def _atk_buff(
    *,
    effect_id: int = 1,
    actor_effect_index: int = 1,
    timing: str = "full_burst_start",
) -> CompiledEffect:
    return CompiledEffect(
        effect_id=effect_id,
        actor=2,
        actor_effect_index=actor_effect_index,
        source="skill3",
        source_tag="skill",
        name="synthetic ATK",
        effect_type="buff",
        stat="atk_pct",
        polarity="beneficial",
        target="self",
        target_spec=TargetSpec("self", TargetMode.SELF),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule(timing, timing, TriggerMode.EVENT),),
        value=100.0,
        duration=10.0,
        max_stack=1.0,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=_capability("buff", "atk_pct"),
    )


def _squad(*, later_buff_timing: str = "full_burst_start") -> CompiledSquad:
    damage = _pending_damage()
    buff = _atk_buff(timing=later_buff_timing)
    effects = (damage, buff)
    members = (
        _member("synthetic-b1", "1"),
        _member("synthetic-b2", "2"),
        _member("synthetic-b3", "3", effects),
    )
    return CompiledSquad(
        members,
        TriggerIndex.from_effects(effects, actor_count=3),
    )


class PendingB3DamageRuntimeTests(unittest.TestCase):
    def test_later_burst_cast_buff_keeps_pending_damage_fail_closed(self):
        squad = _squad(later_buff_timing="burst_cast")
        sink = SimpleDamageScoreSink(squad, EnemyStaticProfile(duration=1.0))
        self.assertNotIn(0, sink.pending_specs)
        self.assertIn(0, sink.unsupported_effect_ids)

    def test_pending_damage_waits_for_full_burst_then_sees_fb_start_buff(self):
        squad = _squad()
        enemy = EnemyStaticProfile(defense=31784.0, duration=1.0)
        policy = BurstPolicy(
            duration=1.0,
            first_burst_time=0.0,
            reaction=0.0,
            switch_delay=0.0,
            full_burst_entry_delay=0.05,
        )

        before_sink = SimpleDamageScoreSink(squad, enemy)
        self.assertIn(0, before_sink.pending_specs)
        before = BurstRuntime(squad, policy, enemy, damage_sink=before_sink)
        before.run(duration=0.04)
        self.assertEqual(before_sink.char_total[2], 0.0)

        sink = SimpleDamageScoreSink(squad, enemy)
        runtime = BurstRuntime(squad, policy, enemy, damage_sink=sink)
        result = runtime.run(duration=0.20)
        self.assertEqual(result.full_burst_starts, (0.05,))

        spec = sink.pending_specs[0]
        expected = expected_damage_event(
            spec,
            squad.members[2],
            enemy,
            DamageTerms(atk_pct=100.0),
            full_burst=True,
        )
        self.assertAlmostEqual(sink.char_total[2], expected, places=8)


if __name__ == "__main__":
    unittest.main()
