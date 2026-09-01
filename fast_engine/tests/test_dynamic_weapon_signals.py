from __future__ import annotations

import unittest
from dataclasses import replace

from fast_engine.engine.dynamic_weapon import MultiSignalChargeCadenceRuntime
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import CompiledCharacter, CompiledEffect, CompiledSquad
from fast_engine.engine.scheduler import EventKind, EventScheduler
from fast_engine.engine.state import StateStore
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule


def _effect(effect_id: int, timing: str, event_key: str, threshold: int) -> CompiledEffect:
    return CompiledEffect(
        effect_id=effect_id,
        actor=0,
        actor_effect_index=effect_id,
        source="synthetic",
        source_tag="skill",
        name=timing,
        effect_type="buff",
        stat="atk_pct",
        polarity="beneficial",
        target="self",
        target_spec=None,
        conditions=(),
        condition_rules=(),
        triggers=(
            TriggerRule(
                timing,
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


def _raw_full_charge_effect(effect_id: int = 0) -> CompiledEffect:
    base = _effect(effect_id, "full_charge_hit", "full_charge_hit", 1)
    rule = TriggerRule(
        "full_charge_hit",
        "full_charge_hit",
        TriggerMode.EVENT,
    )
    return replace(base, triggers=(rule,))


def _squad() -> CompiledSquad:
    effects = (
        _effect(0, "hit_count:3", "hit_count", 3),
        _effect(1, "full_charge_count:4", "full_charge_hit", 4),
    )
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
            "max_ammo": 6,
            "reload_time": 2.0,
            "charge_time": 1.0,
            "post_fire_delay": 0.0,
            "reload_start_delay": 0.0,
            "post_reload_delay": 0.0,
            "is_clip": False,
            "pellets": 1,
            "muzzles": 1,
        },
        effects=effects,
        skill_levels={},
        favorite_stage=0,
    )
    return CompiledSquad(
        (member,),
        TriggerIndex.from_effects(effects, actor_count=1),
    )


class DynamicMultiSignalTests(unittest.TestCase):
    def test_union_of_count_thresholds_uses_one_physical_boundary(self):
        squad = _squad()
        scheduler = EventScheduler()
        state = StateStore.from_compiled_squad(squad)
        effects = ActiveEffectStore(squad, state)
        runtime = MultiSignalChargeCadenceRuntime(
            squad,
            effects,
            state,
            scheduler,
            duration=10.0,
            effect_filter=lambda _effect: True,
        )
        runtime.start(0.0)

        # hit_count:3 is the first observable threshold. Shots 1 and 2 are
        # fast-forwarded inside the cadence runtime and never enter the scheduler.
        self.assertAlmostEqual(scheduler.peek_time(), 3.0)
        first_event = scheduler.pop()
        self.assertEqual(first_event.kind, EventKind.WEAPON_BOUNDARY)
        first = runtime.handle_boundary(first_event)
        self.assertIsNotNone(first)
        self.assertEqual(
            {(row.event_key, row.count_increment) for row in first.signals},
            {("hit_count", 3), ("full_charge_hit", 3)},
        )

        runtime.sync(first_event.time)
        self.assertAlmostEqual(scheduler.peek_time(), 4.0)
        second_event = scheduler.pop()
        second = runtime.handle_boundary(second_event)
        self.assertIsNotNone(second)
        self.assertEqual(
            {(row.event_key, row.count_increment) for row in second.signals},
            {("hit_count", 1), ("full_charge_hit", 1)},
        )

    def test_raw_full_charge_consumer_promotes_each_charge_shot(self):
        raw = _raw_full_charge_effect()
        base = _squad().members[0]
        member = replace(base, effects=(raw,))
        squad = CompiledSquad(
            (member,),
            TriggerIndex.from_effects((raw,), actor_count=1),
        )
        scheduler = EventScheduler()
        state = StateStore.from_compiled_squad(squad)
        runtime = MultiSignalChargeCadenceRuntime(
            squad,
            ActiveEffectStore(squad, state),
            state,
            scheduler,
            duration=10.0,
            effect_filter=lambda _effect: True,
        )
        self.assertEqual(runtime.actors, (0,))
        runtime.start(0.0)

        self.assertAlmostEqual(scheduler.peek_time(), 1.0)
        first = runtime.handle_boundary(scheduler.pop())
        self.assertEqual(
            [(row.event_key, row.count_increment) for row in first.signals],
            [("full_charge_hit", 1)],
        )
        runtime.sync(1.0)
        self.assertAlmostEqual(scheduler.peek_time(), 2.0)

    def test_hit_count_only_charge_actor_enters_dynamic_runtime(self):
        hit_only = _effect(0, "hit_count:3", "hit_count", 3)
        base = _squad().members[0]
        member = CompiledCharacter(
            name=base.name,
            base_atk=base.base_atk,
            base_def=base.base_def,
            base_hp=base.base_hp,
            element=base.element,
            character_class=base.character_class,
            squad_group=base.squad_group,
            burst_stage=base.burst_stage,
            burst_cooldown=base.burst_cooldown,
            burst_regen_time=base.burst_regen_time,
            weapon_type=base.weapon_type,
            weapon=base.weapon,
            effects=(hit_only,),
            skill_levels={},
            favorite_stage=0,
        )
        squad = CompiledSquad(
            (member,),
            TriggerIndex.from_effects((hit_only,), actor_count=1),
        )
        scheduler = EventScheduler()
        state = StateStore.from_compiled_squad(squad)
        runtime = MultiSignalChargeCadenceRuntime(
            squad,
            ActiveEffectStore(squad, state),
            state,
            scheduler,
            duration=10.0,
            effect_filter=lambda _effect: True,
        )
        self.assertEqual(runtime.actors, (0,))
        runtime.start(0.0)
        self.assertAlmostEqual(scheduler.peek_time(), 3.0)
        event = scheduler.pop()
        boundary = runtime.handle_boundary(event)
        self.assertEqual(
            [(row.event_key, row.count_increment) for row in boundary.signals],
            [("hit_count", 3)],
        )

    def test_multi_hit_charge_hit_count_fails_closed(self):
        base = _squad()
        hit_only = _effect(0, "hit_count:3", "hit_count", 3)
        weapon = dict(base.members[0].weapon)
        weapon["muzzles"] = 2
        member = replace(base.members[0], weapon=weapon, effects=(hit_only,))
        squad = CompiledSquad(
            (member,),
            TriggerIndex.from_effects((hit_only,), actor_count=1),
        )
        scheduler = EventScheduler()
        state = StateStore.from_compiled_squad(squad)
        with self.assertRaisesRegex(NotImplementedError, "multiple hits per shot"):
            MultiSignalChargeCadenceRuntime(
                squad,
                ActiveEffectStore(squad, state),
                state,
                scheduler,
                duration=10.0,
                effect_filter=lambda _effect: True,
            )


if __name__ == "__main__":
    unittest.main()
