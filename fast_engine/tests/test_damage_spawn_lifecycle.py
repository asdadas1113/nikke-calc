from __future__ import annotations

import unittest
from unittest.mock import patch

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.state import ENEMY


NAMES = ["리틀 머메이드", "크라운", "라피 : 레드 후드", "미하라 : 본딩 체인", "헬름"]
CONFIG = {"duration": 1.0, "first_burst_time": 3.0, "rng_mode": "expected"}


class StaticSpawnLifecycleTests(unittest.TestCase):
    def test_little_mermaid_bubble_activates_once_on_enemy_spawn(self):
        moris = build_squad(NAMES)
        compiled = compile_moris_squad(moris)
        bubble = next(
            effect
            for effect in compiled.effects
            if compiled.names[effect.actor] == "리틀 머메이드"
            and effect.name == "거품"
            and effect.stat == "received_dmg_pct"
        )

        self.assertEqual([rule.event_key for rule in bubble.triggers], ["event:enemy_spawn"])
        self.assertTrue(is_direct_damage_buff_runtime_supported(bubble))
        blockers = static_score_blockers(compiled)
        self.assertNotIn(
            "normal_delivery:리틀 머메이드:거품:received_dmg_pct",
            blockers,
        )
        self.assertNotIn(
            "skill_state_delivery:리틀 머메이드:거품:received_dmg_pct",
            blockers,
        )

        policy = compile_burst_policy(moris, compiled, CONFIG)
        enemy = EnemyStaticProfile(
            defense=31784.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=1.0,
        )
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)

        # Isolate the t=0 lifecycle contract from unrelated later weapon/cadence
        # scheduling in this deliberately mechanic-heavy public squad.
        with (
            patch.object(runtime.machine.__class__, "start"),
            patch.object(runtime.weapons.__class__, "start"),
            patch.object(BurstRuntime, "_schedule_static_core_hits"),
            patch.object(BurstRuntime, "_schedule_static_last_bullets"),
            patch.object(BurstRuntime, "_schedule_initial_periodics"),
            patch(
                "fast_engine.engine.burst_runtime.simulate_weapon_trigger_boundaries",
                return_value=(),
            ),
        ):
            runtime.start(duration=0.01)

        self.assertEqual(runtime.dispatcher._activation_counts[bubble.effect_id], 1)
        self.assertAlmostEqual(
            runtime.dispatcher.effects.sum_stat(
                ENEMY, "received_dmg_pct", now=0.0
            ),
            5.05,
            places=9,
        )


if __name__ == "__main__":
    unittest.main()
