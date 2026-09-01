from __future__ import annotations

import json
import unittest

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_state import DamageTermResolver
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.normal_attack import compile_normal_attack_spec, expected_normal_shot_damage
from fast_engine.engine.score import score_static_normal_squad
from fast_engine.engine.shot_blocks import compile_static_shot_blocks

NAMES = ["미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인"]
CONFIG = {"duration": 180.0, "first_burst_time": 3.0, "rng_mode": "expected"}
TERM_KEYS = (
    "atk_pct", "atk_flat", "enemy_def_down_pct", "def_ignore_pct",
    "crit_rate", "crit_dmg", "normal_atk_dmg_pct", "atk_dmg_pct",
    "received_dmg_pct", "element_bonus_pct",
)

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
        member = compiled.members[actor]
        normal_spec = compile_normal_attack_spec(member)
        blocks = compile_static_shot_blocks(compiled, duration=policy.duration)[actor]
        fast_shots = sum(block.count for block in blocks if block.first_time < policy.duration)
        moris_hits = [h for h in moris.hits if h.caster == "미하라 : 본딩 체인" and h.skill_name == "기본 공격"]
        moris_total = sum(int(h.damage) for h in moris_hits)
        fast_total = float(fast.char_total[actor])

        full_runtime = BurstRuntime(compiled, policy, fast_enemy)
        rr = full_runtime.run(duration=policy.duration)
        targets = [0.0]
        for start, end in list(zip(rr.full_burst_starts, rr.full_burst_ends))[:3]:
            targets.extend([start + 1.0, end + 1.0])
        if rr.full_burst_starts:
            targets.append(rr.full_burst_starts[-1] + 1.0)

        samples = []
        for target in targets:
            hit = min(moris_hits, key=lambda h: abs(float(h.t) - target))
            t = float(hit.t)
            runtime = BurstRuntime(compiled, policy, fast_enemy)
            runtime.run(duration=min(policy.duration, t + 1e-6))
            resolver = DamageTermResolver(compiled, runtime.dispatcher.effects, runtime.state, fast_enemy)
            terms = resolver.resolve(actor, now=t)
            fast_damage = expected_normal_shot_damage(
                normal_spec,
                base_atk=member.base_atk,
                enemy_def=fast_enemy.defense,
                terms=terms,
                core_prob=0.0,
                is_full_burst=(runtime.machine.phase == "full_burst"),
                is_optimal_range=False,
            )
            samples.append({
                "target": target,
                "t": t,
                "moris": int(hit.damage),
                "fast": fast_damage,
                "ratio": fast_damage / int(hit.damage),
                "phase": runtime.machine.phase,
                "terms": {key: getattr(terms, key) for key in TERM_KEYS},
            })

        report = {
            "moris": {"hits": len(moris_hits), "total": moris_total, "mean": moris_total / len(moris_hits)},
            "fast": {"shots": fast_shots, "total": fast_total, "mean": fast_total / fast_shots},
            "ratios": {"shots": fast_shots / len(moris_hits), "mean": (fast_total / fast_shots) / (moris_total / len(moris_hits)), "total": fast_total / moris_total},
            "fb_starts": list(rr.full_burst_starts),
            "fb_ends": list(rr.full_burst_ends),
            "samples": samples,
        }
        self.fail("INTENTIONAL_MIHARA_PHASE_PROBE=" + json.dumps(report, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    unittest.main()
