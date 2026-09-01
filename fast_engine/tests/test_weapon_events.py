from __future__ import annotations

import unittest

from fast_engine.engine.model import CompiledCharacter, CompiledEffect, CompiledSquad
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule
from fast_engine.engine.weapon_events import simulate_weapon_trigger_boundaries


def _effect(threshold: int, *, event_key: str = "hit_count", effect_id: int = 0) -> CompiledEffect:
    raw = f"{event_key}:{threshold}"
    return CompiledEffect(
        effect_id=effect_id,
        actor=0,
        actor_effect_index=effect_id,
        source="synthetic",
        source_tag="skill",
        name=raw,
        effect_type="buff",
        stat="atk_pct",
        polarity="beneficial",
        target="self",
        target_spec=None,
        conditions=(),
        condition_rules=(),
        triggers=(
            TriggerRule(
                raw,
                event_key,
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


def _sg_squad(*effects: CompiledEffect) -> CompiledSquad:
    if not effects:
        effects = (_effect(5),)
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
        effects=tuple(effects),
        skill_levels={},
        favorite_stage=0,
    )
    return CompiledSquad(
        (member,),
        TriggerIndex.from_effects(tuple(effects), actor_count=1),
    )


class StaticWeaponEventTests(unittest.TestCase):
    def test_sg_hit_count_advances_once_per_trigger_pull(self):
        squad = _sg_squad(_effect(5))
        rows = simulate_weapon_trigger_boundaries(
            squad,
            duration=3.0,
            effect_filter=lambda _effect: True,
        )

        # Moris hit_count is one event per SG trigger pull, independent of the
        # pellet count. At 1.5 shots/s the fifth shot is t=4/1.5.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].event_key, "hit_count")
        self.assertEqual(rows[0].count_increment, 5)
        self.assertAlmostEqual(rows[0].time, 4.0 / 1.5, places=8)

    def test_sg_pellet_hit_advances_per_pellet_without_global_pellet_events(self):
        squad = _sg_squad(_effect(5, event_key="pellet_hit"))
        rows = simulate_weapon_trigger_boundaries(
            squad,
            duration=0.1,
            effect_filter=lambda _effect: True,
        )

        # The same physical SG shot has ten pellet_hit notifications, so a
        # pellet_hit:5 threshold crosses twice at t=0. The cadence engine still
        # materializes only the two meaningful threshold crossings, not ten hits.
        self.assertEqual(
            [(row.time, row.event_key, row.count_increment) for row in rows],
            [(0.0, "pellet_hit", 5), (0.0, "pellet_hit", 5)],
        )

    def test_non_sg_single_hit_semantics_are_unchanged(self):
        squad = _sg_squad(_effect(5))
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
