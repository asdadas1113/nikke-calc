from __future__ import annotations

import unittest

from calculator.damage import calc_damage_avg, default_hit_type
from fast_engine.engine.damage import DamageTerms, HitSpec, expected_damage


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


def _moris_hit(hit: HitSpec) -> dict:
    return default_hit_type(
        coeff=hit.coeff,
        is_normal_atk=hit.is_normal_atk,
        core_prob=hit.core_prob,
        is_core_damage=hit.is_core_damage,
        is_weapon_mode_skill=hit.is_weapon_mode_skill,
        is_full_burst=hit.is_full_burst,
        is_optimal_range=hit.is_optimal_range,
        is_full_charge=hit.is_full_charge,
        is_burst_damage=hit.is_burst_damage,
        is_aoe_burst=hit.is_aoe_burst,
        is_pierce_damage=hit.is_pierce_damage,
        is_armor_break_damage=hit.is_armor_break_damage,
        is_dot=hit.is_dot,
        is_projectile_explosion=hit.is_projectile_explosion,
        is_projectile_attachment=hit.is_projectile_attachment,
        is_sequential=hit.is_sequential,
        is_split=hit.is_split,
        is_part=hit.is_part,
    )


class FastDamageKernelParityTests(unittest.TestCase):
    BASE_ATK = 80000.0
    ENEMY_DEF = 31784.0
    WEAPON = {
        "damage_coeff": 69.04,
        "core_dmg_mult": 200.0,
        "full_charge_mult": 250.0,
    }

    def assertMorisParity(self, terms: DamageTerms, hit: HitSpec) -> None:
        fast = expected_damage(
            base_atk=self.BASE_ATK,
            enemy_def=self.ENEMY_DEF,
            core_dmg_mult=self.WEAPON["core_dmg_mult"],
            full_charge_mult=self.WEAPON["full_charge_mult"],
            terms=terms,
            hit=hit,
        )
        moris = calc_damage_avg(
            self.BASE_ATK,
            _moris_buffs(terms),
            self.WEAPON,
            hit_type=_moris_hit(hit),
            enemy_def=self.ENEMY_DEF,
        )
        # Both paths intentionally use slightly different arithmetic grouping.
        # Treat sub-1e-8 drift as floating-point noise rather than formula drift.
        self.assertAlmostEqual(fast, moris, delta=1e-8, msg=(fast, moris, terms, hit))

    def test_plain_normal_attack(self):
        self.assertMorisParity(DamageTerms(), HitSpec(coeff=69.04))

    def test_expected_crit_core_fullburst_element_normal_attack(self):
        self.assertMorisParity(
            DamageTerms(
                atk_pct=47.5,
                atk_flat=4321.0,
                enemy_def_down_pct=-12.0,
                def_ignore_pct=18.0,
                crit_rate=0.43,
                crit_dmg=31.0,
                core_dmg_pct=56.0,
                normal_atk_dmg_pct=22.0,
                atk_dmg_pct=17.0,
                received_dmg_pct=11.0,
                element_bonus_pct=23.0,
                element_match=True,
            ),
            HitSpec(
                coeff=69.04,
                core_prob=0.65,
                is_full_burst=True,
                is_optimal_range=True,
            ),
        )

    def test_full_charge_layers(self):
        self.assertMorisParity(
            DamageTerms(
                atk_pct=20.0,
                crit_rate=0.27,
                charge_dmg_pct=11.11,
                charge_dmg_mag_pct=167.87,
            ),
            HitSpec(coeff=69.04, is_full_charge=True),
        )

    def test_skill_type_layers_and_skill_crit_lane(self):
        self.assertMorisParity(
            DamageTerms(
                atk_pct=30.0,
                crit_rate=0.90,
                crit_dmg=100.0,
                crit_rate_skill=0.25,
                crit_dmg_skill=35.0,
                atk_dmg_pct=20.0,
                burst_dmg_pct=50.0,
                burst_dmg_aoe_pct=120.0,
                received_dmg_pct=16.0,
                element_bonus_pct=10.0,
                element_match=True,
            ),
            HitSpec(
                coeff=833.79,
                is_normal_atk=False,
                is_burst_damage=True,
                is_aoe_burst=True,
                is_full_burst=True,
            ),
        )

    def test_armor_break_part_split_and_projectile_layers(self):
        self.assertMorisParity(
            DamageTerms(
                atk_pct=15.0,
                crit_rate=0.0,
                atk_dmg_pct=8.0,
                armor_break_dmg_pct=25.0,
                projectile_explosion_dmg_pct=40.0,
                part_dmg_pct=30.0,
                received_dmg_pct=12.0,
                split_dmg_pct=22.0,
            ),
            HitSpec(
                coeff=315.0,
                is_normal_atk=False,
                is_armor_break_damage=True,
                is_projectile_explosion=True,
                is_part=True,
                is_split=True,
            ),
        )


if __name__ == "__main__":
    unittest.main()
