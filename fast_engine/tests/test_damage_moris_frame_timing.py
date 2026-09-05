from __future__ import annotations

import unittest

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.effects import ActiveEffect
from fast_engine.engine.frame_lattice import moris_observed_tick
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers


class MorisFrameTimingTest(unittest.TestCase):
    def test_charge_and_burst_deadlines_use_distinct_outer_tick_rules(self):
        self.assertAlmostEqual(
            moris_observed_tick(3.0, horizon=180.0, epsilon=1e-9),
            3.0,
            places=12,
        )
        self.assertAlmostEqual(
            moris_observed_tick(3.65, horizon=180.0),
            3.6666666666666585,
            places=12,
        )
        self.assertAlmostEqual(
            moris_observed_tick(15.57, horizon=180.0, epsilon=1e-9),
            15.583333333333687,
            places=12,
        )

    def test_timed_effect_lives_until_true_expiry(self):
        effect = ActiveEffect(
            effect_id=0,
            target=0,
            source_actor=0,
            cohort=(0,),
            stacks=1.0,
            expires_at=26.40000000000035,
            generation=1,
        )
        self.assertTrue(effect.active(26.4))
        self.assertFalse(effect.active(effect.expires_at))

    def test_def55_near_tie_both_sides_now_fail_closed(self):
        mm = (
            "미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인",
        )
        rhq = (
            "라피 : 레드 후드", "레드 후드", "프리카", "민트", "퀀시 : 이스케이프 퀸",
        )
        duration = 180.0
        cfg = {"duration": duration, "first_burst_time": 3.0, "rng_mode": "expected"}
        profile = EnemyStaticProfile(
            defense=55000.0, element="작열", core_uptime=1.0, core_px=10.0, duration=duration,
        )
        mm_squad = spec.build_squad(list(mm))
        mm_compiled = compile_moris_squad(mm_squad)
        mm_blockers = static_score_blockers(mm_compiled)
        self.assertIn("normal_state:미란다:파워 업!:rank_target_timing", mm_blockers)
        mm_policy = compile_burst_policy(mm_squad, mm_compiled, dict(cfg))
        with self.assertRaises(NotImplementedError):
            score_static_squad(mm_compiled, mm_policy, profile, duration=duration)
        rhq_squad = spec.build_squad(list(rhq))
        rhq_compiled = compile_moris_squad(rhq_squad)
        rhq_blockers = static_score_blockers(rhq_compiled)
        self.assertIn(
            "normal_state:프리카:무대, 시작할게. 3:same_timestamp_actor_order", rhq_blockers
        )
        rhq_policy = compile_burst_policy(rhq_squad, rhq_compiled, dict(cfg))
        with self.assertRaises(NotImplementedError):
            score_static_squad(rhq_compiled, rhq_policy, profile, duration=duration)



if __name__ == "__main__":
    unittest.main()
