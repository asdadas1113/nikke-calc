from __future__ import annotations

import json
from time import perf_counter
import unittest

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
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


class FirstCertifiedRealSquadParityProbe(unittest.TestCase):
    def test_print_standardized_fast_moris_parity(self):
        # Membership is fixed explicitly. No optimizer candidate generator or
        # snapshot case-specific build/config/enemy data participates here.
        moris_squad = spec.build_squad(NAMES)
        moris_config = spec.build_config(moris_squad, dict(CONFIG))
        enemy = dict(DEFAULT_ENEMY)

        t0 = perf_counter()
        moris = simulate(
            moris_squad,
            config=moris_config,
            enemy=enemy,
            seed=42,
            verbose=False,
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

        report = {
            "members": list(compiled.names),
            "scenario": {
                "config": CONFIG,
                "enemy": enemy,
                "optimizer_candidate_generation_used": False,
                "snapshot_case_overrides_used": False,
            },
            "moris_total": float(moris.squad_total),
            "fast_total": float(fast.squad_total),
            "relative_error": (
                None
                if moris.squad_total == 0
                else float(fast.squad_total) / float(moris.squad_total) - 1.0
            ),
            "moris_seconds": moris_seconds,
            "fast_seconds": fast_seconds,
            "speedup": None if fast_seconds == 0.0 else moris_seconds / fast_seconds,
            "fast_events": fast.events_processed,
            "characters": char_rows,
        }
        print("FIRST_CERTIFIED_REAL_SQUAD_PARITY=" + json.dumps(
            report, ensure_ascii=False, sort_keys=True
        ))


if __name__ == "__main__":
    unittest.main()
