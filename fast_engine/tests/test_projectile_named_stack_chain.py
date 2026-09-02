from __future__ import annotations

import unittest

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers


class ProjectileNamedStackChainTest(unittest.TestCase):
    def test_public_rapi_redhood_chain_is_certified(self):
        members = list(snapshot.SQUADS["레이드_레드후드퀀시"]["members"])
        squad = spec.build_squad(members)
        compiled = compile_moris_squad(squad)
        blockers = static_score_blockers(compiled)
        self.assertFalse(any("라피 : 레드 후드" in b for b in blockers), blockers)
        self.assertEqual(blockers, ())

        cfg = spec.build_config(squad, {
            "duration": 30.0, "first_burst_time": 3.0, "rng_mode": "expected",
        })
        policy = compile_burst_policy(squad, compiled, cfg)
        fast = score_static_squad(
            compiled, policy, EnemyStaticProfile(defense=31784.0, duration=30.0)
        )
        self.assertEqual(fast.unsupported, ())
        self.assertGreater(fast.squad_total, 0.0)

        moris = simulate(
            squad, config=cfg, enemy=dict(DEFAULT_ENEMY), seed=42, verbose=False
        )
        rel = fast.squad_total / float(moris.squad_total) - 1.0
        print("RAPI_CHAIN_30S", float(moris.squad_total), fast.squad_total, rel)
        self.assertLess(abs(rel), 0.35)

    def test_cross_actor_weapon_hit_is_not_opened(self):
        members = list(snapshot.SQUADS["레이드_레드후드퀀시"]["members"])
        squad = spec.build_squad(members)
        compiled = compile_moris_squad(squad)
        from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
        sink = SimpleDamageScoreSink(compiled, EnemyStaticProfile(defense=0.0, duration=1.0))
        self.assertTrue(sink.supports_weapon_hit_source(0, "부착형 유탄 4"))
        self.assertFalse(sink.supports_weapon_hit_source(1, "부착형 유탄 4"))


if __name__ == "__main__":
    unittest.main()
