from __future__ import annotations

import json
import unittest

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_normal_squad
from fast_engine.engine.shot_blocks import compile_static_shot_blocks

NAMES = ["미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인"]
CONFIG = {"duration": 180.0, "first_burst_time": 3.0, "rng_mode": "expected"}

class MiharaNoControlProbe(unittest.TestCase):
    def test_compare_normal_attack_without_control(self):
        moris_squad = spec.build_squad(NAMES)
        for char in moris_squad:
            if char["name"] == "미하라 : 본딩 체인":
                char["control"] = {}

        moris_config = spec.build_config(moris_squad, dict(CONFIG))
        enemy = dict(DEFAULT_ENEMY)
        moris = simulate(moris_squad, config=moris_config, enemy=enemy, seed=42, verbose=True)

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
        blocks = compile_static_shot_blocks(compiled, duration=policy.duration)[actor]
        fast_shots = sum(block.count for block in blocks if block.first_time < policy.duration)
        moris_hits = [h for h in moris.hits if h.caster == "미하라 : 본딩 체인" and h.skill_name == "기본 공격"]
        moris_total = sum(int(h.damage) for h in moris_hits)
        fast_total = float(fast.char_total[actor])
        report = {
            "control": next(c["control"] for c in moris_squad if c["name"] == "미하라 : 본딩 체인"),
            "moris": {"hits": len(moris_hits), "total": moris_total, "mean": moris_total / len(moris_hits)},
            "fast": {"shots": fast_shots, "total": fast_total, "mean": fast_total / fast_shots},
            "ratios": {"shots": fast_shots / len(moris_hits), "mean": (fast_total / fast_shots) / (moris_total / len(moris_hits)), "total": fast_total / moris_total},
            "moris_samples": [{"t": float(h.t), "damage": int(h.damage)} for h in moris_hits[:20]],
        }
        self.fail("INTENTIONAL_MIHARA_NO_CONTROL=" + json.dumps(report, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    unittest.main()
