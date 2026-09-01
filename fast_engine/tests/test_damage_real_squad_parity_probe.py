from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import json
from time import perf_counter
import unittest

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers


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
MIHARA_DAMAGE_NAMES = ("바디 컨텍 3", "사슬 감기", "사슬 당기기")


def zero_damage_effect(compiled: CompiledSquad, *, actor: int, name: str) -> CompiledSquad:
    members = list(compiled.members)
    effects = tuple(
        replace(effect, value=0.0)
        if effect.actor == actor and effect.effect_type == "damage" and effect.name == name
        else effect
        for effect in members[actor].effects
    )
    members[actor] = replace(members[actor], effects=effects)
    return CompiledSquad(tuple(members), compiled.trigger_index)


class FirstCertifiedRealSquadParityProbe(unittest.TestCase):
    def test_print_standardized_fast_moris_parity(self):
        moris_squad = spec.build_squad(NAMES)
        moris_config = spec.build_config(moris_squad, dict(CONFIG))
        enemy = dict(DEFAULT_ENEMY)

        t0 = perf_counter()
        moris = simulate(
            moris_squad,
            config=moris_config,
            enemy=enemy,
            seed=42,
            verbose=True,
        )
        moris_seconds = perf_counter() - t0

        compiled = compile_moris_squad(moris_squad)
        self.assertEqual(static_score_blockers(compiled), ())
        policy = compile_burst_policy(moris_squad, compiled, dict(CONFIG))
        fast_enemy = EnemyStaticProfile(
            defense=float(enemy.get("def", 31784.0)),
            element=enemy.get("code"),
            core_uptime=0.0,
            core_px=float(enemy.get("core_px", 0.0) or 0.0),
            duration=policy.duration,
        )
        t1 = perf_counter()
        fast = score_static_squad(compiled, policy, fast_enemy)
        fast_seconds = perf_counter() - t1
        self.assertEqual(fast.unsupported, ())

        fast_by_char = {
            name: float(value)
            for name, value in zip(compiled.names, fast.char_total)
        }
        moris_by_char = {
            name: float(moris.char_total.get(name, 0.0))
            for name in compiled.names
        }
        char_rows = {}
        for name in compiled.names:
            m = moris_by_char[name]
            f = fast_by_char[name]
            char_rows[name] = {
                "moris": m,
                "fast": f,
                "relative_error": None if m == 0.0 else f / m - 1.0,
            }

        moris_mihara_skills = defaultdict(int)
        for hit in moris.hits:
            if hit.caster == "미하라 : 본딩 체인":
                moris_mihara_skills[hit.skill_name] += int(hit.damage)

        fast_mihara_marginals = {}
        mihara_actor = compiled.names.index("미하라 : 본딩 체인")
        for damage_name in MIHARA_DAMAGE_NAMES:
            variant = zero_damage_effect(
                compiled,
                actor=mihara_actor,
                name=damage_name,
            )
            variant_policy = compile_burst_policy(
                moris_squad, variant, dict(CONFIG)
            )
            variant_score = score_static_squad(
                variant, variant_policy, fast_enemy
            )
            self.assertEqual(variant_score.unsupported, ())
            fast_mihara_marginals[damage_name] = (
                float(fast.char_total[mihara_actor])
                - float(variant_score.char_total[mihara_actor])
            )

        # Burst timing is measured separately from damage totals so a cadence
        # mismatch cannot hide inside a skill-damage discrepancy.
        sink = SimpleDamageScoreSink(compiled, fast_enemy)
        runtime = BurstRuntime(compiled, policy, fast_enemy, damage_sink=sink)
        fast_runtime = runtime.run(duration=policy.duration)
        moris_burst_starts = [
            row.t for row in moris.log.burst_log if row.event == "full_burst 시작"
        ]

        report = {
            "members": list(compiled.names),
            "moris_total": float(moris.squad_total),
            "fast_total": float(fast.squad_total),
            "relative_error": float(fast.squad_total) / float(moris.squad_total) - 1.0,
            "moris_seconds": moris_seconds,
            "fast_seconds": fast_seconds,
            "speedup": moris_seconds / fast_seconds,
            "fast_events": fast.events_processed,
            "characters": char_rows,
            "moris_mihara_skills": dict(sorted(moris_mihara_skills.items())),
            "fast_mihara_damage_marginals": fast_mihara_marginals,
            "burst": {
                "moris_count": len(moris_burst_starts),
                "fast_count": len(fast_runtime.full_burst_starts),
                "moris_starts": moris_burst_starts,
                "fast_starts": list(fast_runtime.full_burst_starts),
            },
            "scenario": {
                "config": CONFIG,
                "enemy": enemy,
                "optimizer_candidate_generation_used": False,
                "snapshot_case_overrides_used": False,
            },
        }
        payload = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.fail("INTENTIONAL_PARITY_LOCALIZATION=" + payload)


if __name__ == "__main__":
    unittest.main()
