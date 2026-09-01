from __future__ import annotations

from collections import defaultdict
import json
from time import perf_counter
import unittest

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import StaticNormalAttackObserver, score_static_squad, static_score_blockers


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


class RealSquadParityProbe(unittest.TestCase):
    def test_surface_parity_after_helm_bullet_lifetime(self):
        moris_squad = spec.build_squad(NAMES)
        # Fixed comparison scenario: remove the same manual-control policy before
        # both Moris simulation and Fast compilation. This isolates engine parity
        # from an independently unsupported control mechanic.
        next(c for c in moris_squad if c["name"] == "미하라 : 본딩 체인")["control"] = {}
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
        blockers = static_score_blockers(compiled)
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

        # Independent Fast decomposition: normal vs supported skill damage.
        sink = SimpleDamageScoreSink(compiled, fast_enemy)
        runtime = BurstRuntime(compiled, policy, fast_enemy, damage_sink=sink)
        observer = StaticNormalAttackObserver(runtime, duration=policy.duration)
        runtime_result = runtime.run(duration=policy.duration, score_observer=observer)
        normal = observer.finish(events_processed=runtime_result.events_processed)

        moris_by_actor = defaultdict(float)
        for hit in moris.hits:
            moris_by_actor[hit.caster] += float(hit.damage)

        by_actor = {}
        for actor, name in enumerate(compiled.names):
            moris_total = float(moris_by_actor.get(name, 0.0))
            fast_total = float(fast.char_total[actor])
            by_actor[name] = {
                "moris": moris_total,
                "fast": fast_total,
                "relative_error": None if moris_total == 0.0 else fast_total / moris_total - 1.0,
                "fast_normal": float(normal.char_total[actor]),
                "fast_skill": float(sink.char_total[actor]),
            }

        helm_effect = next(
            e for e in compiled.effects
            if e.actor == compiled.names.index("헬름")
            and e.name == "이지스 캐논 3"
            and e.stat == "charge_dmg_mag_pct"
        )

        moris_skill = {}
        for name in ("헬름", "미하라 : 본딩 체인"):
            rows = defaultdict(lambda: {"hits": 0, "total": 0.0})
            for hit in moris.hits:
                if hit.caster != name:
                    continue
                row = rows[hit.skill_name]
                row["hits"] += 1
                row["total"] += float(hit.damage)
            moris_skill[name] = dict(rows)

        report = {
            "scenario": {
                "optimizer_candidate_generation_used": False,
                "snapshot_case_overrides_used": False,
                "mihara_control_removed_from_both_engines": True,
            },
            "blockers": list(blockers),
            "unsupported": list(fast.unsupported),
            "helm_charge_effect": {
                "value": helm_effect.value,
                "duration_bullets": helm_effect.parameters.get("duration_bullets"),
                "runtime_supported": is_direct_damage_buff_runtime_supported(helm_effect),
            },
            "moris_total": float(moris.squad_total),
            "fast_total": float(fast.squad_total),
            "relative_error": float(fast.squad_total) / float(moris.squad_total) - 1.0,
            "by_actor": by_actor,
            "moris_skill": moris_skill,
            "burst": {
                "fast_count": len(runtime_result.full_burst_starts),
                "fast_starts": [float(v) for v in runtime_result.full_burst_starts],
                "moris_count": len([
                    row for row in moris.log.burst_log if row.event == "full_burst 시작"
                ]),
                "moris_starts": [
                    float(row.t)
                    for row in moris.log.burst_log
                    if row.event == "full_burst 시작"
                ],
            },
            "timing": {
                "moris_seconds": moris_seconds,
                "fast_seconds": fast_seconds,
                "speedup": moris_seconds / fast_seconds,
                "fast_events": fast.events_processed,
            },
        }
        self.fail(
            "INTENTIONAL_REAL_SQUAD_PARITY_AFTER_HELM="
            + json.dumps(report, ensure_ascii=False, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
