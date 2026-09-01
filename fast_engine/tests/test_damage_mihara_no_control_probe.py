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

NAMES = ["미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인"]
CONFIG = {"duration": 180.0, "first_burst_time": 3.0, "rng_mode": "expected"}

class MiharaNoControlProbe(unittest.TestCase):
    def test_lingering_crit_source(self):
        moris_squad = spec.build_squad(NAMES)
        for char in moris_squad:
            if char["name"] == "미하라 : 본딩 체인":
                char["control"] = {}
        enemy = dict(DEFAULT_ENEMY)
        moris = simulate(moris_squad, config=spec.build_config(moris_squad, dict(CONFIG)), enemy=enemy, seed=42, verbose=True)
        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(moris_squad, compiled, dict(CONFIG))
        fast_enemy = EnemyStaticProfile(defense=float(enemy.get("def", 31784.0)), element=enemy.get("code"), core_uptime=0.0, core_px=0.0, duration=180.0)
        actor = compiled.names.index("미하라 : 본딩 체인")
        member = compiled.members[actor]
        normal_spec = compile_normal_attack_spec(member)
        moris_hits = [h for h in moris.hits if h.caster == "미하라 : 본딩 체인" and h.skill_name == "기본 공격"]

        target = 14.4
        hit = min(moris_hits, key=lambda h: abs(float(h.t) - target))
        t = float(hit.t)
        runtime = BurstRuntime(compiled, policy, fast_enemy)
        runtime.run(duration=t + 1e-6)
        resolver = DamageTermResolver(compiled, runtime.dispatcher.effects, runtime.state, fast_enemy)
        terms = resolver.resolve(actor, now=t)
        fast_damage = expected_normal_shot_damage(normal_spec, base_atk=member.base_atk, enemy_def=fast_enemy.defense, terms=terms, core_prob=0.0, is_full_burst=(runtime.machine.phase == "full_burst"), is_optimal_range=False)

        active_crit = []
        for stat in ("crit_rate", "normal_atk_crit_rate", "crit_dmg", "normal_atk_crit_dmg"):
            for effect, active in runtime.dispatcher.effects.iter_stat(stat, now=t):
                if active.target != actor:
                    continue
                active_crit.append({
                    "stat": stat,
                    "name": effect.name,
                    "value": effect.value,
                    "source": compiled.members[active.source_actor].name,
                    "duration": effect.duration,
                    "expires_at": active.expires_at,
                    "activated_generation": active.generation,
                    "effect_id": effect.effect_id,
                })
        report = {"t": t, "moris": int(hit.damage), "fast": fast_damage, "crit_rate": terms.crit_rate, "crit_dmg": terms.crit_dmg, "active_crit": active_crit}
        self.fail("INTENTIONAL_MIHARA_CRIT_SOURCE=" + json.dumps(report, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    unittest.main()
