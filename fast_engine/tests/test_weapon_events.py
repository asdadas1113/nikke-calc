from __future__ import annotations

import unittest

from fast_engine.engine.model import CompiledCharacter, CompiledEffect, CompiledSquad
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule
from fast_engine.engine.weapon_events import simulate_weapon_trigger_boundaries


def _effect(threshold: int) -> CompiledEffect:
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name=f"hit_count:{threshold}",
        effect_type="buff",
        stat="atk_pct",
        polarity="beneficial",
        target="self",
        target_spec=None,
        conditions=(),
        condition_rules=(),
        triggers=(
            TriggerRule(
                f"hit_count:{threshold}",
                "hit_count",
                TriggerMode.MODULO,
                threshold=float(threshold),
                trigger_count_reducible=True,
            ),
        ),
        value=1.0,
        duration=1.0,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=None,
    )


def _sg_squad(threshold: int = 5) -> CompiledSquad:
    effect = _effect(threshold)
    member = CompiledCharacter(
        name="synthetic-sg",
        base_atk=1000.0,
        base_def=100.0,
        base_hp=10000.0,
        element=None,
        character_class="화력형",
        squad_group=None,
        burst_stage="3",
        burst_cooldown=40.0,
        burst_regen_time=2.0,
        weapon_type="SG",
        weapon={
            "weapon_type": "SG",
            "fire_mode": "auto",
            "max_ammo": 9,
            "reload_time": 1.5,
            "fire_rate": 1.5,
            "pellets": 10,
            "muzzles": 1,
            "is_clip": True,
            "reload_start_delay": 0.0,
            "post_reload_delay": 0.0,
        },
        effects=(effect,),
        skill_levels={},
        favorite_stage=0,
    )
    return CompiledSquad(
        (member,),
        TriggerIndex.from_effects((effect,), actor_count=1),
    )


class StaticWeaponEventTests(unittest.TestCase):
    def test_sg_hit_count_advances_per_pellet_without_per_pellet_events(self):
        squad = _sg_squad(5)
        rows = simulate_weapon_trigger_boundaries(
            squad,
            duration=0.1,
            effect_filter=lambda _effect: True,
        )

        # One trigger pull produces 10 pellet hits. hit_count:5 therefore fires
        # twice at the same physical shot timestamp, but the cadence engine still
        # represented the whole shot as one aggregated block rather than ten
        # scheduler events.
        self.assertEqual(
            [(row.time, row.event_key, row.count_increment) for row in rows],
            [(0.0, "hit_count", 5), (0.0, "hit_count", 5)],
        )

    def test_non_sg_single_hit_semantics_are_unchanged(self):
        squad = _sg_squad(5)
        base = squad.members[0]
        weapon = dict(base.weapon)
        weapon.update({"weapon_type": "AR", "pellets": 1, "is_clip": False})
        member = CompiledCharacter(
            name="synthetic-ar",
            base_atk=base.base_atk,
            base_def=base.base_def,
            base_hp=base.base_hp,
            element=base.element,
            character_class=base.character_class,
            squad_group=base.squad_group,
            burst_stage=base.burst_stage,
            burst_cooldown=base.burst_cooldown,
            burst_regen_time=base.burst_regen_time,
            weapon_type="AR",
            weapon=weapon,
            effects=base.effects,
            skill_levels={},
            favorite_stage=0,
        )
        ar = CompiledSquad(
            (member,),
            TriggerIndex.from_effects(base.effects, actor_count=1),
        )
        rows = simulate_weapon_trigger_boundaries(
            ar,
            duration=0.1,
            effect_filter=lambda _effect: True,
        )
        self.assertEqual(rows, ())


if __name__ == "__main__":
    unittest.main()
