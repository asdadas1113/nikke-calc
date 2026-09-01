from __future__ import annotations

import json
import unittest

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.normal_attack import compile_normal_attack_spec
from fast_engine.engine.score import score_static_normal_squad
from fast_engine.engine.shot_blocks import compile_static_shot_blocks


NAMES = [
    "미란다",
    "브리드 : 사일런트 트랙",
    "헬름",
    "루주",
    "미하라 : 본딩 체인",
]
CONFIG = {
    "duration": 180.0,
    "first_burst_time": 3.0,
    "rng_mode": "expected",
}


class MiharaNormalAttackProbe(unittest.TestCase):
    def test_print_mihara_normal_attack_decomposition(self):
        moris_squad = spec.build_squad(NAMES)
        moris_config = spec.build_config(moris_squad, dict(CONFIG))
        enemy = dict(DEFAULT_ENEMY)
        moris = simulate(
            moris_squad,
            config=moris_config,
            enemy=enemy,
            seed=42,
            verbose=True,
        )

        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(moris_squad, compiled, dict(CONFIG))
        fast_enemy = EnemyStaticProfile(
            defense=float(enemy.get("def", 31784.0)),
            element=enemy.get("code"),
            core_uptime=0.0,
            core_px=float(enemy.get("core_px", 0.0) or 0.0),
            duration=policy.duration,
        )
        fast = score_static_normal_squad(compiled, policy, fast_enemy)

        actor = compiled.names.index("미하라 : 본딩 체인")
        member = compiled.members[actor]
        normal_spec = compile_normal_attack_spec(member)
        blocks = compile_static_shot_blocks(compiled, duration=policy.duration)[actor]
        fast_shots = sum(block.count for block in blocks if block.first_time < policy.duration)

        moris_hits = [
            hit
            for hit in moris.hits
            if hit.caster == "미하라 : 본딩 체인"
            and hit.skill_name == "기본 공격"
        ]
        moris_total = sum(int(hit.damage) for hit in moris_hits)
        fast_total = float(fast.char_total[actor])

        weapon_keys = (
            "fire_mode", "damage_coeff", "rate", "ammo", "reload_time",
            "warmup_bullets", "warmup_cooldown_time", "warmup_min_rate",
            "warmup_max_rate", "pellets", "muzzles", "normal_hit_coeff",
        )
        weapon = {key: member.weapon.get(key) for key in weapon_keys if key in member.weapon}

        report = {
            "moris": {
                "physical_hits": len(moris_hits),
                "total": moris_total,
                "mean_per_hit": None if not moris_hits else moris_total / len(moris_hits),
                "first_20": [
                    {"t": float(hit.t), "damage": int(hit.damage)}
                    for hit in moris_hits[:20]
                ],
            },
            "fast": {
                "shot_count": fast_shots,
                "total": fast_total,
                "mean_per_shot": None if fast_shots == 0 else fast_total / fast_shots,
                "block_count": len(blocks),
                "first_blocks": [
                    {
                        "first": block.first_time,
                        "count": block.count,
                        "interval": block.interval,
                        "last": block.last_time,
                    }
                    for block in blocks[:12]
                ],
            },
            "ratios": {
                "count_fast_over_moris": None if not moris_hits else fast_shots / len(moris_hits),
                "mean_fast_over_moris": None if not moris_hits or fast_shots == 0 else (fast_total / fast_shots) / (moris_total / len(moris_hits)),
                "total_fast_over_moris": None if moris_total == 0 else fast_total / moris_total,
            },
            "normal_spec": {
                "coeff_per_hit": normal_spec.coeff_per_hit,
                "hits_per_shot": normal_spec.hits_per_shot,
                "normal_hit_coeff": normal_spec.normal_hit_coeff,
            },
            "weapon": weapon,
            "base_atk": member.base_atk,
        }
        self.fail(
            "INTENTIONAL_MIHARA_NORMAL_PROBE="
            + json.dumps(report, ensure_ascii=False, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
