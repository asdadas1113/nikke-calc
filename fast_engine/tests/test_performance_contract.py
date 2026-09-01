from __future__ import annotations

import unittest

from fast_engine.engine.model import CompiledCharacter, CompiledEffect, CompiledSquad
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule
from fast_engine.engine.weapon import simulate_static_weapon_cadence
from fast_engine.engine.weapon_events import simulate_weapon_trigger_boundaries


def _effect() -> CompiledEffect:
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name="hit_count:120",
        effect_type="buff",
        stat="atk_pct",
        polarity="beneficial",
        target="self",
        target_spec=None,
        conditions=(),
        condition_rules=(),
        triggers=(
            TriggerRule(
                "hit_count:120",
                "hit_count",
                TriggerMode.MODULO,
                threshold=120.0,
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


def _mg_squad() -> CompiledSquad:
    effect = _effect()
    member = CompiledCharacter(
        name="synthetic-mg",
        base_atk=1000.0,
        base_def=100.0,
        base_hp=10000.0,
        element=None,
        character_class="화력형",
        squad_group=None,
        burst_stage="3",
        burst_cooldown=40.0,
        burst_regen_time=2.0,
        weapon_type="MG",
        weapon={
            "weapon_type": "MG",
            "fire_mode": "auto_warmup",
            "max_ammo": 300,
            "reload_time": 2.0,
            "fire_rate": 1.0,
            "fire_rate_max": 70.0,
            "warmup_bullets": 41.4,
            "warmup_cooldown_time": 1.0,
            "pellets": 1,
            "muzzles": 1,
            "is_clip": False,
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


class FastBoundaryCompressionContractTests(unittest.TestCase):
    def test_thousands_of_mg_hits_materialize_only_threshold_crossings(self):
        squad = _mg_squad()
        cadence = simulate_static_weapon_cadence(squad, duration=180.0)[0]
        rows = simulate_weapon_trigger_boundaries(
            squad,
            duration=180.0,
            effect_filter=lambda _effect: True,
        )

        self.assertGreater(cadence.hit_events, 1000)
        self.assertEqual(len(rows), cadence.hit_events // 120)
        # Structural throughput contract: global events scale with meaningful
        # trigger crossings, not raw shots/hits.
        self.assertLess(len(rows), cadence.hit_events / 50)


if __name__ == "__main__":
    unittest.main()
