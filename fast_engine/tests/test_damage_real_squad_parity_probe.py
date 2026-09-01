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
MIHARA_DAMAGE_NAMES = ("바디 컨텍 3", "사슬 감기", "사슬 당기기")


class RecordingDamageSink(SimpleDamageScoreSink):
    __slots__ = ("effect_rows",)

    def __init__(self, squad, enemy):
        super().__init__(squad, enemy)
        self.effect_rows = defaultdict(list)

    def _score_spec(self, effect_id: int, *, now: float, full_burst: bool) -> bool:
        actor = self._effect_actor.get(effect_id)
        before = None if actor is None else self.char_total[actor]
        hit_count = None
        multiplier = 1.0
        if effect_id in self.stack_specs:
            hit_count = self._stack_count_hit_count(effect_id)
        if effect_id in self.stateful_dot_specs:
            multiplier = self._stateful_effect_stack(effect_id, now=now)
        fired = super()._score_spec(
            effect_id,
            now=now,
            full_burst=full_burst,
        )
        if fired and actor is not None and before is not None:
            damage = self.char_total[actor] - before
            spec = self._damage_spec(effect_id)
            self.effect_rows[effect_id].append({
                "t": float(now),
                "damage": float(damage),
                "physical_hits": (
                    int(hit_count)
                    if hit_count is not None
                    else (int(spec.hit_count) if spec is not None else None)
                ),
                "stack_multiplier": float(multiplier),
            })
        return fired


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

        # Re-run one Fast runtime with a recording sink. This does not use the
        # optimizer; it records score-kernel invocations only and leaves the
        # production score path untouched.
        recording = RecordingDamageSink(compiled, fast_enemy)
        runtime = BurstRuntime(
            compiled,
            policy,
            fast_enemy,
            damage_sink=recording,
        )
        observer = StaticNormalAttackObserver(runtime, duration=policy.duration)
        runtime_result = runtime.run(
            duration=policy.duration,
            score_observer=observer,
        )
        normal = observer.finish(events_processed=runtime_result.events_processed)

        mihara_actor = compiled.names.index("미하라 : 본딩 체인")
        fast_mihara = {
            "normal_total": float(normal.char_total[mihara_actor]),
            "skill_total": float(recording.char_total[mihara_actor]),
            "combined": float(normal.char_total[mihara_actor] + recording.char_total[mihara_actor]),
            "effects": {},
        }
        for effect in compiled.effects:
            if effect.actor != mihara_actor or effect.name not in MIHARA_DAMAGE_NAMES:
                continue
            rows = recording.effect_rows.get(effect.effect_id, [])
            total = sum(row["damage"] for row in rows)
            physical_hits = sum(int(row["physical_hits"] or 0) for row in rows)
            fast_mihara["effects"][effect.name] = {
                "score_calls": len(rows),
                "physical_hits": physical_hits,
                "total": total,
                "mean_per_call": None if not rows else total / len(rows),
                "mean_per_physical_hit": None if physical_hits == 0 else total / physical_hits,
                "first": rows[:12],
            }

        moris_skill_rows = {}
        for skill_name in ("기본 공격",) + MIHARA_DAMAGE_NAMES:
            rows = [
                hit
                for hit in moris.hits
                if hit.caster == "미하라 : 본딩 체인"
                and hit.skill_name == skill_name
            ]
            total = sum(int(hit.damage) for hit in rows)
            moris_skill_rows[skill_name] = {
                "physical_hits": len(rows),
                "total": total,
                "mean_per_physical_hit": None if not rows else total / len(rows),
                "first": [
                    {"t": float(hit.t), "damage": int(hit.damage), "tag": hit.hit_tag}
                    for hit in rows[:12]
                ],
            }

        report = {
            "moris_total": float(moris.squad_total),
            "fast_total": float(fast.squad_total),
            "relative_error": float(fast.squad_total) / float(moris.squad_total) - 1.0,
            "moris_seconds": moris_seconds,
            "fast_seconds": fast_seconds,
            "speedup": moris_seconds / fast_seconds,
            "fast_mihara": fast_mihara,
            "moris_mihara": moris_skill_rows,
            "burst": {
                "fast_count": len(runtime_result.full_burst_starts),
                "moris_count": len([
                    row for row in moris.log.burst_log if row.event == "full_burst 시작"
                ]),
            },
            "scenario": {
                "optimizer_candidate_generation_used": False,
                "snapshot_case_overrides_used": False,
            },
        }
        self.fail(
            "INTENTIONAL_MIHARA_COUNT_VALUE_PROBE="
            + json.dumps(report, ensure_ascii=False, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
