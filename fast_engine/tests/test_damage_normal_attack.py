from __future__ import annotations

import unittest

from calculator.damage import calc_damage_avg, default_hit_type
from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage import DamageTerms
from fast_engine.engine.model import CompiledCharacter
from fast_engine.engine.normal_attack import (
    compile_normal_attack_spec,
    expected_normal_block_damage,
    expected_normal_shot_damage,
)


def _character(*, pellets: int = 10, muzzles: int = 1) -> CompiledCharacter:
    return CompiledCharacter(
        name="synthetic-sg",
        base_atk=80000.0,
        base_def=100.0,
        base_hp=10000.0,
        element="전격",
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
            "reload_time": 2.0,
            "fire_rate": 1.5,
            "pellets": pellets,
            "muzzles": muzzles,
            "damage_coeff": 100.0,
            "core_dmg_mult": 200.0,
            "full_charge_mult": 100.0,
            "normal_hit_coeff": 0.9,
        },
        effects=(),
        skill_levels={},
        favorite_stage=0,
    )


class NormalAttackScoringTests(unittest.TestCase):
    def test_compiled_weapon_carries_moris_normal_hit_coeff(self):
        squad = compile_moris_squad(
            build_squad(["나가", "리타", "크라운", "홍련", "앨리스"])
        )
        by_name = {member.name: member for member in squad.members}
        self.assertEqual(by_name["나가"].weapon_type, "SG")
        self.assertAlmostEqual(by_name["나가"].weapon["normal_hit_coeff"], 0.9)
        self.assertAlmostEqual(by_name["크라운"].weapon["normal_hit_coeff"], 1.0)

    def test_sg_expected_shot_matches_moris_per_pellet_linearity(self):
        char = _character()
        spec = compile_normal_attack_spec(char)
        terms = DamageTerms(
            atk_pct=35.0,
            crit_rate=0.42,
            crit_dmg=25.0,
            core_dmg_pct=40.0,
            atk_dmg_pct=18.0,
            received_dmg_pct=12.0,
            element_bonus_pct=15.0,
            element_match=True,
        )
        core_prob = 0.55
        fast = expected_normal_shot_damage(
            spec,
            base_atk=char.base_atk,
            enemy_def=31784.0,
            terms=terms,
            core_prob=core_prob,
            is_full_burst=True,
        )

        buffs = {
            "atk_pct": terms.atk_pct,
            "atk_flat": 0.0,
            "enemy_def_down_pct": 0.0,
            "def_ignore_pct": 0.0,
            "crit_rate": terms.crit_rate,
            "crit_dmg": terms.crit_dmg,
            "core_dmg_pct": terms.core_dmg_pct,
            "normal_atk_dmg_pct": 0.0,
            "atk_dmg_pct": terms.atk_dmg_pct,
            "received_dmg": terms.received_dmg_pct,
            "element_bonus_pct": terms.element_bonus_pct,
            "is_element_match": True,
        }
        moris_per_pellet = calc_damage_avg(
            char.base_atk,
            buffs,
            char.weapon,
            hit_type=default_hit_type(
                coeff=char.weapon["damage_coeff"] / 10.0,
                core_prob=core_prob,
                is_full_burst=True,
            ),
            enemy_def=31784.0,
        )
        moris_linear = moris_per_pellet * 10 * 0.9
        self.assertAlmostEqual(fast, moris_linear, places=9)

    def test_muzzles_multiply_hits_without_dividing_coefficient_again(self):
        one = compile_normal_attack_spec(_character(muzzles=1))
        two = compile_normal_attack_spec(_character(muzzles=2))
        self.assertEqual(one.coeff_per_hit, two.coeff_per_hit)
        self.assertEqual(two.hits_per_shot, one.hits_per_shot * 2)

        terms = DamageTerms(crit_rate=0.0)
        d1 = expected_normal_shot_damage(
            one,
            base_atk=80000.0,
            enemy_def=31784.0,
            terms=terms,
            core_prob=0.0,
        )
        d2 = expected_normal_shot_damage(
            two,
            base_atk=80000.0,
            enemy_def=31784.0,
            terms=terms,
            core_prob=0.0,
        )
        self.assertAlmostEqual(d2, d1 * 2.0, places=9)

    def test_identical_shot_block_is_one_shot_times_count(self):
        spec = compile_normal_attack_spec(_character())
        terms = DamageTerms(atk_pct=20.0, crit_rate=0.25)
        one = expected_normal_shot_damage(
            spec,
            base_atk=80000.0,
            enemy_def=31784.0,
            terms=terms,
            core_prob=0.3,
        )
        block = expected_normal_block_damage(
            spec,
            shot_count=300,
            base_atk=80000.0,
            enemy_def=31784.0,
            terms=terms,
            core_prob=0.3,
        )
        self.assertAlmostEqual(block, one * 300, places=9)


if __name__ == "__main__":
    unittest.main()
