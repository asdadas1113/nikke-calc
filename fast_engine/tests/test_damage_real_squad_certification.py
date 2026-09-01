from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers


class RealSquadCertificationTests(unittest.TestCase):
    def test_control_miranda_mihara_is_fully_certified(self):
        names = [
            "미란다",
            "브리드 : 사일런트 트랙",
            "헬름",
            "루주",
            "미하라 : 본딩 체인",
        ]
        moris_squad = build_squad(names)
        compiled = compile_moris_squad(moris_squad)

        blockers = static_score_blockers(compiled)
        self.assertEqual(blockers, (), msg=f"state-delivery blockers remain: {blockers}")

        config = {
            "duration": 180.0,
            "first_burst_time": 3.0,
            "rng_mode": "expected",
        }
        policy = compile_burst_policy(moris_squad, compiled, config)
        enemy = EnemyStaticProfile(
            defense=31784.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=180.0,
        )
        score = score_static_squad(compiled, policy, enemy)
        print(
            "REAL_SQUAD_FAST_SCORE",
            score.squad_total,
            "events",
            score.events_processed,
            "unsupported",
            score.unsupported,
        )

        self.assertGreater(score.squad_total, 0.0)
        self.assertEqual(
            score.unsupported,
            (),
            msg=f"Fast returned only a partial subtotal: {score.unsupported}",
        )


if __name__ == "__main__":
    unittest.main()
