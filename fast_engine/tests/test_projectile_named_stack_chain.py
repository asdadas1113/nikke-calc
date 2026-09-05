from __future__ import annotations

import unittest

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers


class ProjectileNamedStackChainTest(unittest.TestCase):
    def test_public_rapi_redhood_chain_remains_locally_supported(self):
        members = list(snapshot.SQUADS["레이드_레드후드퀀시"]["members"])
        squad = spec.build_squad(members)
        compiled = compile_moris_squad(squad)
        blockers = static_score_blockers(compiled)
        self.assertFalse(any("라피 : 레드 후드" in b for b in blockers), blockers)
        self.assertIn(
            "normal_state:프리카:무대, 시작할게. 3:same_timestamp_actor_order", blockers
        )

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
