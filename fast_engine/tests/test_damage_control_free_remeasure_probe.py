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


class ControlFreeRealSquadRemeasureProbe(unittest.TestCase):
    def test_surface_standardized_measurement(self):
        squad = spec.build_squad(NAMES)
        next(c for c in squad if c["name"] == "미하라 : 본딩 체인")["control"] = {}
        config = spec.build_config(squad, dict(CONFIG))
        enemy = dict(DEFAULT_ENEMY)

        compiled = compile_moris_squad(squad)
        blockers = static_score_blockers(compiled)
        policy = compile_burst_policy(squad, compiled, dict(CONFIG))
        fast_enemy = EnemyStaticProfile(
            defense=float(enemy.get("def", 31784.0)),
            element=enemy.get("code"),
            core_uptime=0.0,
            core_px=float(enemy.get("core_px", 0.0) or 0.0),
            duration=policy.duration,
        )

        t0 = perf_counter()
        moris = simulate(
            squad,
            config=config,
            enemy=enemy,
            seed=42,
            verbose=False,
        )
        moris_seconds = perf_counter() - t0

        fast = None
        fast_seconds = None
        fast_error = None
        try:
            t1 = perf_counter()
            fast = score_static_squad(compiled, policy, fast_enemy)
            fast_seconds = perf_counter() - t1
        except Exception as exc:  # research probe: surface fail-closed reason
            fast_error = f"{type(exc).__name__}: {exc}"

        report = {
            "blockers": list(blockers),
            "fast_error": fast_error,
            "fast_unsupported": None if fast is None else list(fast.unsupported),
            "moris_total": float(moris.squad_total),
            "fast_total": None if fast is None else float(fast.squad_total),
            "relative_error": (
                None
                if fast is None or not moris.squad_total
                else float(fast.squad_total) / float(moris.squad_total) - 1.0
            ),
            "moris_by_char": {
                name: float(value)
                for name, value in zip(NAMES, moris.char_total)
            },
            "fast_by_char": (
                None
                if fast is None
                else {name: float(value) for name, value in zip(NAMES, fast.char_total)}
            ),
            "moris_seconds": moris_seconds,
            "fast_seconds": fast_seconds,
            "speedup": (
                None
                if fast_seconds is None or fast_seconds <= 0
                else moris_seconds / fast_seconds
            ),
            "scenario": {
                "mihara_control_removed_in_common_source_squad": True,
                "optimizer_candidate_generation_used": False,
                "snapshot_case_overrides_used": False,
            },
        }
        self.fail(
            "INTENTIONAL_CONTROL_FREE_REAL_SQUAD_REMEASURE="
            + json.dumps(report, ensure_ascii=False, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
