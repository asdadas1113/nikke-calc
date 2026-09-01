from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_state import DamageTermResolver
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import (
    CompiledCharacter,
    CompiledEffect,
    CompiledSquad,
    EnemyStaticProfile,
)
from fast_engine.engine.scheduler import EventScheduler
from fast_engine.engine.state import ENEMY, StateStore
from fast_engine.engine.triggers import TriggerIndex


class DamageStateCacheTests(unittest.TestCase):
    def setUp(self):
        self.squad = compile_moris_squad(
            build_squad(["리타", "크라운", "홍련", "앨리스", "나가"])
        )
        self.state = StateStore.from_compiled_squad(self.squad)
        self.effects = ActiveEffectStore(self.squad, self.state)
        self.scheduler = EventScheduler()
        self.enemy = EnemyStaticProfile(element="수냉")
        self.resolver = DamageTermResolver(
            self.squad, self.effects, self.state, self.enemy
        )
        self.atk_effect = next(
            effect
            for effect in self.squad.effects
            if effect.effect_type == "buff"
            and effect.stat == "atk_pct"
            and float(effect.value or 0.0) != 0.0
        )

    def test_repeated_resolve_reuses_same_snapshot_object(self):
        first = self.resolver.resolve(0, now=0.0)
        second = self.resolver.resolve(0, now=1.0)
        self.assertIs(first, second)

    def test_resource_change_does_not_invalidate_damage_terms(self):
        first = self.resolver.resolve(0, now=0.0)
        self.state.set_ammo(0, max(self.state.actors[0].ammo - 1.0, 0.0))
        second = self.resolver.resolve(0, now=0.1)
        self.assertIs(first, second)

    def test_unrelated_actor_effect_change_does_not_invalidate_actor_zero(self):
        first = self.resolver.resolve(0, now=0.0)
        self.effects.activate_group(
            self.atk_effect, (1,), 0.0, self.scheduler
        )
        second = self.resolver.resolve(0, now=0.1)
        self.assertIs(first, second)

    def test_target_actor_effect_change_invalidates_and_recomputes(self):
        first = self.resolver.resolve(0, now=0.0)
        self.effects.activate_group(
            self.atk_effect, (0,), 0.0, self.scheduler
        )
        second = self.resolver.resolve(0, now=0.1)
        self.assertIsNot(first, second)
        self.assertGreater(second.atk_pct, first.atk_pct)


def _effect(effect_id: int, stat: str, value: float) -> CompiledEffect:
    return CompiledEffect(
        effect_id=effect_id,
        actor=0,
        actor_effect_index=effect_id,
        source="synthetic",
        source_tag="skill",
        name=f"{stat}-{effect_id}",
        effect_type="buff",
        stat=stat,
        polarity="beneficial",
        target="self",
        target_spec=None,
        conditions=(),
        condition_rules=(),
        triggers=(),
        value=value,
        duration=-1.0,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=None,
    )


def _routing_squad() -> CompiledSquad:
    effects = (
        _effect(0, "def_pct", -20.0),
        _effect(1, "personal_enemy_def_down_pct", -7.0),
        _effect(2, "received_dmg_pct", 11.0),
        _effect(3, "personal_received_dmg_pct", 5.0),
        _effect(4, "element_bonus", 8.0),
        _effect(5, "element_bonus_pct", 3.0),
        _effect(6, "part_dmg", 4.0),
        _effect(7, "part_dmg_pct", 6.0),
        _effect(8, "projectile_explosion_dmg", 9.0),
        _effect(9, "projectile_explosion_dmg_pct", 2.0),
    )
    member = CompiledCharacter(
        name="synthetic",
        base_atk=1000.0,
        base_def=100.0,
        base_hp=10000.0,
        element="전격",
        character_class="화력형",
        squad_group=None,
        burst_stage="3",
        burst_cooldown=40.0,
        burst_regen_time=2.0,
        weapon_type="AR",
        weapon={"max_ammo": 60},
        effects=effects,
        skill_levels={},
        favorite_stage=0,
    )
    return CompiledSquad(
        (member,),
        TriggerIndex.from_effects(effects, actor_count=1),
    )


class DamageStateRoutingTests(unittest.TestCase):
    def test_enemy_and_personal_damage_routes_match_moris_contract(self):
        squad = _routing_squad()
        state = StateStore.from_compiled_squad(squad)
        effects = ActiveEffectStore(squad, state)
        scheduler = EventScheduler()

        # Moris routes enemy-target def_pct/received_dmg to the target lane,
        # while personal_* modifiers stay on the scored actor.
        effects.activate_group(squad.effects[0], (ENEMY,), 0.0, scheduler)
        effects.activate_group(squad.effects[1], (0,), 0.0, scheduler)
        effects.activate_group(squad.effects[2], (ENEMY,), 0.0, scheduler)
        effects.activate_group(squad.effects[3], (0,), 0.0, scheduler)
        for effect in squad.effects[4:]:
            effects.activate_group(effect, (0,), 0.0, scheduler)

        terms = DamageTermResolver(
            squad,
            effects,
            state,
            EnemyStaticProfile(element="수냉"),
        ).resolve(0, now=0.0)

        self.assertEqual(terms.enemy_def_down_pct, -27.0)
        self.assertEqual(terms.received_dmg_pct, 16.0)
        self.assertEqual(terms.element_bonus_pct, 11.0)
        self.assertTrue(terms.element_match)
        self.assertEqual(terms.part_dmg_pct, 10.0)
        self.assertEqual(terms.projectile_explosion_dmg_pct, 11.0)


if __name__ == "__main__":
    unittest.main()
