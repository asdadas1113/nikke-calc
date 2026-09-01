from __future__ import annotations

import json
import unittest
from pathlib import Path

from calculator.timeline import _core_hit_prob
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.model import CompiledCharacter, CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import score_static_normal_squad
from fast_engine.engine.triggers import TriggerIndex


_ROOT = Path(__file__).resolve().parents[2]
_MECHANICS = json.loads((_ROOT / "data" / "weapon_mechanics.json").read_text(encoding="utf-8"))
_ACCURACY = _MECHANICS["accuracy"]


def _weapon(weapon_type: str) -> dict:
    spec = _ACCURACY[weapon_type]
    fire_mode = "charge" if weapon_type in {"SR", "RL"} else "auto"
    return {
        "weapon_type": weapon_type,
        "fire_mode": fire_mode,
        "max_ammo": 60,
        "reload_time": 2.0,
        "fire_rate": 2.0,
        "fire_rate_max": None,
        "warmup_bullets": 1.0,
        "warmup_cooldown_time": 1.0,
        "post_fire_delay": 0.0,
        "post_reload_delay": 0.0,
        "reload_start_delay": 0.0,
        "cover_during_delay": False,
        "charge_time": 0.5,
        "pellets": 1,
        "muzzles": 1,
        "is_clip": False,
        "damage_coeff": 100.0,
        "core_dmg_mult": 200.0,
        "full_charge_mult": 100.0,
        "normal_hit_coeff": 1.0,
        "core_base_diameter": float(spec["base_diameter"]),
        "core_acc_slope": float(spec["acc_slope"]),
        "core_model_n": float(_ACCURACY["_model_n"]),
    }


def _single_member_squad(weapon_type: str = "AR") -> CompiledSquad:
    member = CompiledCharacter(
        name=f"synthetic-{weapon_type}",
        base_atk=80000.0,
        base_def=100.0,
        base_hp=10000.0,
        element="전격",
        character_class="화력형",
        squad_group=None,
        burst_stage="3",
        burst_cooldown=40.0,
        burst_regen_time=2.0,
        weapon_type=weapon_type,
        weapon=_weapon(weapon_type),
        effects=(),
        skill_levels={},
        favorite_stage=0,
    )
    return CompiledSquad(
        (member,),
        TriggerIndex.from_effects((), actor_count=1),
    )


class CoreProbabilityParityTests(unittest.TestCase):
    def test_weapon_model_matches_moris_for_all_weapon_types_and_accuracy(self):
        core_px = 52.0
        uptime = 0.73
        enemy = EnemyStaticProfile(core_uptime=uptime, core_px=core_px)

        for weapon_type in ("AR", "SMG", "SG", "MG", "SR", "RL"):
            weapon = _weapon(weapon_type)
            for accuracy_pct in (0.0, 17.5, 50.0, 100.0):
                with self.subTest(weapon_type=weapon_type, accuracy_pct=accuracy_pct):
                    expected = uptime * _core_hit_prob(
                        weapon_type,
                        accuracy_pct,
                        core_px,
                    )
                    actual = enemy.core_rate_for_weapon(
                        weapon,
                        accuracy_pct=accuracy_pct,
                    )
                    self.assertAlmostEqual(actual, expected, places=12)

    def test_no_core_px_preserves_historical_aggregate_fallback(self):
        enemy = EnemyStaticProfile(
            core_uptime=0.6,
            core_hit_rate_when_open=0.75,
        )
        self.assertAlmostEqual(
            enemy.core_rate_for_weapon(_weapon("SG"), accuracy_pct=100.0),
            0.45,
        )

    def test_core_px_path_is_used_by_static_normal_score(self):
        squad = _single_member_squad("AR")
        policy = BurstPolicy(duration=1.0, no_burst_actors=frozenset({0}))
        no_core = score_static_normal_squad(
            squad,
            policy,
            EnemyStaticProfile(
                duration=1.0,
                core_uptime=1.0,
                core_hit_rate_when_open=0.0,
            ),
        )
        modeled_core = score_static_normal_squad(
            squad,
            policy,
            EnemyStaticProfile(
                duration=1.0,
                core_uptime=1.0,
                core_hit_rate_when_open=0.0,
                core_px=52.0,
            ),
        )
        self.assertGreater(modeled_core.squad_total, no_core.squad_total)


if __name__ == "__main__":
    unittest.main()
