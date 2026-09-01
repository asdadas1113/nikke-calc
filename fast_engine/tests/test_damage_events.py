from __future__ import annotations

import unittest

from calculator.damage import calc_damage_avg, default_hit_type
from fast_engine.engine.damage import DamageTerms
from fast_engine.engine.damage_events import (
    compile_fixed_dot_damage_event,
    compile_pending_b3_bonus_damage_event,
    compile_simple_damage_event,
    expected_damage_event,
)
from fast_engine.engine.model import CompiledCharacter, CompiledEffect, EnemyStaticProfile
from fast_engine.engine.triggers import TriggerMode, TriggerRule


def _character(*, burst_stage: str = "2", weapon_type: str = "AR") -> CompiledCharacter:
    return CompiledCharacter(
        name="synthetic-damage",
        base_atk=80000.0,
        base_def=10000.0,
        base_hp=1000000.0,
        element="전격",
        character_class="화력형",
        squad_group=None,
        burst_stage=burst_stage,
        burst_cooldown=20.0,
        burst_regen_time=2.0,
        weapon_type=weapon_type,
        weapon={
            "weapon_type": weapon_type,
            "damage_coeff": 69.04,
            "core_dmg_mult": 200.0,
            "full_charge_mult": 250.0,
        },
        effects=(),
        skill_levels={},
        favorite_stage=0,
    )


def _effect(
    *,
    stat: str,
    value: float = 300.0,
    target="enemy",
    burst_cast: bool = False,
    tick_interval: float | None = None,
    duration: float | None = None,
    max_stack: float | None = None,
    parameters: dict | None = None,
) -> CompiledEffect:
    triggers = (
        TriggerRule("burst_cast", "burst_cast", TriggerMode.EVENT),
    ) if burst_cast else (
        TriggerRule("battle_start", "battle_start", TriggerMode.EVENT),
    )
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name="synthetic damage",
        effect_type="damage",
        stat=stat,
        polarity=None,
        target=target,
        target_spec=None,
        conditions=(),
        condition_rules=(),
        triggers=triggers,
        value=value,
        duration=duration,
        max_stack=max_stack,
        max_trigger=None,
        tick_interval=tick_interval,
        parameters=parameters or {},
        capability=None,
    )


def _moris_buffs(terms: DamageTerms) -> dict:
    return {
        "atk_pct": terms.atk_pct,
        "atk_flat": terms.atk_flat,
        "enemy_def_down_pct": terms.enemy_def_down_pct,
        "def_ignore_pct": terms.def_ignore_pct,
        "crit_rate": terms.crit_rate,
        "crit_dmg": terms.crit_dmg,
        "crit_rate_skill": terms.crit_rate if terms.crit_rate_skill is None else terms.crit_rate_skill,
        "crit_dmg_skill": terms.crit_dmg if terms.crit_dmg_skill is None else terms.crit_dmg_skill,
        "core_dmg_pct": terms.core_dmg_pct,
        "normal_atk_dmg_pct": terms.normal_atk_dmg_pct,
        "atk_dmg_pct": terms.atk_dmg_pct,
        "burst_dmg_pct": terms.burst_dmg_pct,
        "burst_dmg_aoe_pct": terms.burst_dmg_aoe_pct,
        "pierce_dmg_pct": terms.pierce_dmg_pct,
        "armor_break_dmg_pct": terms.armor_break_dmg_pct,
        "dot_dmg_pct": terms.dot_dmg_pct,
        "projectile_explosion_dmg": terms.projectile_explosion_dmg_pct,
        "projectile_attachment_dmg": terms.projectile_attachment_dmg_pct,
        "sequential_dmg_pct": terms.sequential_dmg_pct,
        "part_dmg_pct": terms.part_dmg_pct,
        "charge_dmg_pct": terms.charge_dmg_pct,
        "charge_dmg_mag_pct": terms.charge_dmg_mag_pct,
        "received_dmg": terms.received_dmg_pct,
        "split_dmg_pct": terms.split_dmg_pct,
        "element_bonus_pct": terms.element_bonus_pct,
        "is_element_match": terms.element_match,
    }


class SimpleDamageEventTests(unittest.TestCase):
    def test_numeric_multi_hit_burst_damage_is_one_dealform_times_hit_count(self):
        char = _character()
        effect = _effect(stat="burst_damage:4", value=833.79, target="all_enemies")
        spec = compile_simple_damage_event(effect, char)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.hit_count, 4)
        self.assertTrue(spec.hit.is_burst_damage)
        self.assertTrue(spec.hit.is_aoe_burst)

        terms = DamageTerms(
            atk_pct=30.0,
            crit_rate=0.75,
            crit_dmg=80.0,
            crit_rate_skill=0.25,
            crit_dmg_skill=35.0,
            atk_dmg_pct=20.0,
            burst_dmg_pct=50.0,
            burst_dmg_aoe_pct=120.0,
            received_dmg_pct=16.0,
            element_bonus_pct=10.0,
            element_match=True,
        )
        enemy = EnemyStaticProfile(defense=31784.0)
        fast = expected_damage_event(spec, char, enemy, terms, full_burst=True)
        moris = calc_damage_avg(
            char.base_atk,
            _moris_buffs(terms),
            dict(char.weapon),
            hit_type=default_hit_type(
                coeff=833.79,
                is_normal_atk=False,
                is_full_burst=True,
                is_burst_damage=True,
                is_aoe_burst=True,
            ),
            enemy_def=enemy.defense,
        ) * 4
        self.assertAlmostEqual(fast, moris, places=8)

    def test_normal_formula_rl_reuses_expected_core_and_projectile_layers(self):
        char = _character(weapon_type="RL")
        effect = _effect(
            stat="damage",
            value=250.0,
            parameters={"damage_formula": "normal_attack"},
        )
        spec = compile_simple_damage_event(effect, char)
        self.assertIsNotNone(spec)
        self.assertTrue(spec.hit.is_normal_atk)
        self.assertTrue(spec.hit.is_projectile_explosion)

        terms = DamageTerms(
            crit_rate=0.35,
            core_dmg_pct=40.0,
            normal_atk_dmg_pct=20.0,
            projectile_explosion_dmg_pct=30.0,
        )
        enemy = EnemyStaticProfile(
            defense=31784.0,
            core_uptime=0.5,
            core_hit_rate_when_open=0.8,
        )
        fast = expected_damage_event(spec, char, enemy, terms, full_burst=False)
        moris = calc_damage_avg(
            char.base_atk,
            _moris_buffs(terms),
            dict(char.weapon),
            hit_type=default_hit_type(
                coeff=250.0,
                is_normal_atk=True,
                core_prob=0.4,
                is_projectile_explosion=True,
            ),
            enemy_def=enemy.defense,
        )
        self.assertAlmostEqual(fast, moris, places=8)

    def test_b3_burst_cast_bonus_has_distinct_pending_compiler(self):
        char = _character(burst_stage="3")
        effect = _effect(stat="bonus_damage", value=500.0, burst_cast=True)
        self.assertIsNone(compile_simple_damage_event(effect, char))
        pending = compile_pending_b3_bonus_damage_event(effect, char)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.hit_count, 1)
        self.assertFalse(pending.hit.is_burst_damage)
        self.assertFalse(pending.hit.is_normal_atk)

        # Moris special-cases only the exact stat `bonus_damage`.
        multi = _effect(stat="bonus_damage:5", value=123.0, burst_cast=True)
        immediate = compile_simple_damage_event(multi, char)
        self.assertIsNotNone(immediate)
        self.assertEqual(immediate.hit_count, 5)
        self.assertIsNone(compile_pending_b3_bonus_damage_event(multi, char))

        self.assertIsNone(
            compile_pending_b3_bonus_damage_event(
                effect, _character(burst_stage="2")
            )
        )
        self.assertIsNone(
            compile_pending_b3_bonus_damage_event(
                _effect(stat="burst_damage", burst_cast=True), char
            )
        )

    def test_fixed_dot_compiler_keeps_only_finite_non_scaling_slice(self):
        char = _character()
        delayed = _effect(
            stat="dot_damage",
            value=150.0,
            tick_interval=1.0,
            duration=5.0,
            max_stack=1,
        )
        spec = compile_fixed_dot_damage_event(delayed, char)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.interval, 1.0)
        self.assertEqual(spec.duration, 5.0)
        self.assertFalse(spec.immediate)
        self.assertTrue(spec.damage.hit.is_dot)

        immediate = compile_fixed_dot_damage_event(
            _effect(
                stat="dot_damage",
                tick_interval=0.5,
                duration=2.0,
                max_stack=1,
                parameters={"tick_start": "immediate"},
            ),
            char,
        )
        self.assertIsNotNone(immediate)
        self.assertTrue(immediate.immediate)

        self.assertIsNone(
            compile_fixed_dot_damage_event(
                _effect(
                    stat="dot_damage",
                    tick_interval=1.0,
                    duration=5.0,
                    max_stack=2,
                ),
                char,
            )
        )
        self.assertIsNone(
            compile_fixed_dot_damage_event(
                _effect(
                    stat="dot_damage",
                    tick_interval=1.0,
                    duration=-1.0,
                    max_stack=1,
                ),
                char,
            )
        )
        self.assertIsNone(
            compile_fixed_dot_damage_event(
                _effect(
                    stat="dot_damage",
                    tick_interval=1.0,
                    duration=5.0,
                    max_stack=1,
                    parameters={"scaling": "stack_count", "scaling_ref": "x"},
                ),
                char,
            )
        )
        self.assertIsNone(
            compile_fixed_dot_damage_event(
                _effect(
                    stat="dot_damage",
                    target="same_target:paired",
                    tick_interval=1.0,
                    duration=5.0,
                    max_stack=1,
                ),
                char,
            )
        )

    def test_dynamic_or_delayed_damage_fails_closed(self):
        char = _character(burst_stage="3")
        self.assertIsNone(
            compile_simple_damage_event(
                _effect(stat="dot_damage", tick_interval=1.0), char
            )
        )
        self.assertIsNone(
            compile_simple_damage_event(
                _effect(stat="damage", parameters={"scaling": "stack_count", "scaling_ref": "x"}),
                char,
            )
        )
        self.assertIsNone(
            compile_simple_damage_event(
                _effect(stat="bonus_damage", burst_cast=True), char
            )
        )
        self.assertIsNone(
            compile_pending_b3_bonus_damage_event(
                _effect(
                    stat="bonus_damage",
                    burst_cast=True,
                    parameters={"scaling": "stack_count", "scaling_ref": "x"},
                ),
                char,
            )
        )
        self.assertIsNone(
            compile_pending_b3_bonus_damage_event(
                _effect(stat="bonus_damage", burst_cast=True, target="same_target:paired"),
                char,
            )
        )
        self.assertIsNone(
            compile_simple_damage_event(
                _effect(stat="damage", target="same_target:paired"), char
            )
        )


if __name__ == "__main__":
    unittest.main()
