from __future__ import annotations

import unittest

from calculator.timeline import DEFAULT_ENEMY
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import EnemyStaticProfile


class ConditionalPassiveSelfStackTest(unittest.TestCase):
    def test_quency_route_completion_materializes_passive_damage_states(self) -> None:
        members = [
            "라피 : 레드 후드",
            "레드 후드",
            "프리카",
            "민트",
            "퀀시 : 이스케이프 퀸",
        ]
        squad = spec.build_squad(members)
        compiled = compile_moris_squad(squad)
        qi = members.index("퀀시 : 이스케이프 퀸")
        config = {"duration": 30.0, "first_burst_time": 3.0, "rng_mode": "expected"}
        enemy = EnemyStaticProfile(
            defense=float(DEFAULT_ENEMY.get("def", 31784.0)),
            element=DEFAULT_ENEMY.get("code"),
            core_uptime=0.0,
            core_px=0.0,
            duration=30.0,
        )
        policy = compile_burst_policy(squad, compiled, config)
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        runtime.run(duration=30.0)

        effects = runtime.dispatcher.effects
        now = 29.999
        self.assertAlmostEqual(effects.sum_stat(qi, "split_dmg_pct", now=now), 49.58, places=6)
        self.assertAlmostEqual(effects.sum_stat(qi, "core_dmg_pct", now=now), 25.25, places=6)
        self.assertTrue(effects.has_named_state(qi, "루트 확정 3", now=now))
        self.assertGreaterEqual(effects.sum_stat(qi, "crit_rate", now=now), 16.73)


if __name__ == "__main__":
    unittest.main()
