from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_state import DamageTermResolver
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.scheduler import EventKind
from fast_engine.engine.score import static_score_blockers


NAMES = ["리틀 머메이드", "나가", "크라운", "아스카 : WILLE", "루드밀라 : 윈터 오너"]


class TimedShieldRuntimeTests(unittest.TestCase):
    @staticmethod
    def _runtime():
        squad = compile_moris_squad(build_squad(NAMES))
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=40.0, first_burst_time=30.0),
            EnemyStaticProfile(defense=0.0, duration=40.0),
        )
        return squad, runtime

    @staticmethod
    def _expire_through(runtime, time: float) -> None:
        while runtime.scheduler and (runtime.scheduler.peek_time() or 0.0) <= time + 1e-9:
            event = runtime.scheduler.pop()
            if event.kind is EventKind.STATE_EXPIRE:
                runtime.dispatcher.handle_expiry(event)

    def test_public_naga_shield_and_unreachable_crown_heal_blockers_are_removed(self):
        squad, _runtime = self._runtime()
        blockers = static_score_blockers(squad)
        self.assertFalse(any("나가:우정의 가드 2:core_dmg_pct" in item for item in blockers))
        self.assertFalse(any("나가:친구들과 함께라면! 3:atk_caster_based_pct" in item for item in blockers))
        self.assertNotIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)
        self.assertNotIn("skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)

    def test_shield_state_precedes_same_time_shield_applied_consumer(self):
        squad, runtime = self._runtime()
        naga = NAMES.index("나가")
        crown = NAMES.index("크라운")
        runtime.dispatcher.dispatch(BurstSignal(0.0, "burst_cast", crown, crown))
        self.assertGreater(runtime.state.actors[naga].shield, 0.0)
        guard = next(e for e in squad.members[naga].effects if e.name == "우정의 가드 2")
        self.assertGreater(runtime.dispatcher._activation_counts.get(guard.effect_id, 0), 0)
        for actor in range(len(NAMES)):
            self.assertAlmostEqual(
                runtime.dispatcher.effects.sum_stat(actor, "core_dmg_pct", now=0.01),
                float(guard.value or 0.0),
                places=9,
            )

    def test_during_shield_damage_state_rechecks_after_shield_expiry(self):
        squad, runtime = self._runtime()
        naga = NAMES.index("나가")
        crown = NAMES.index("크라운")
        target = NAMES.index("리틀 머메이드")
        runtime.dispatcher.dispatch(BurstSignal(0.0, "burst_cast", crown, crown))
        runtime.dispatcher.dispatch(BurstSignal(14.0, "burst_cast", naga, naga))
        resolver = DamageTermResolver(squad, runtime.dispatcher.effects, runtime.state, runtime.enemy)
        before = resolver.resolve(target, now=14.1).atk_flat
        conditional = next(e for e in squad.members[naga].effects if e.name == "친구들과 함께라면! 3")
        expected_drop = squad.members[naga].base_atk * float(conditional.value or 0.0) / 100.0
        self._expire_through(runtime, 15.0)
        self.assertEqual(runtime.state.actors[naga].shield, 0.0)
        after = resolver.resolve(target, now=15.01).atk_flat
        self.assertAlmostEqual(before - after, expected_drop, places=6)

    def test_shield_refresh_invalidates_old_expiry(self):
        _squad, runtime = self._runtime()
        naga = NAMES.index("나가")
        crown = NAMES.index("크라운")
        runtime.dispatcher.dispatch(BurstSignal(0.0, "burst_cast", crown, crown))
        runtime.dispatcher.dispatch(BurstSignal(10.0, "burst_cast", crown, crown))
        self._expire_through(runtime, 15.0)
        self.assertGreater(runtime.state.actors[naga].shield, 0.0)
        self._expire_through(runtime, 25.0)
        self.assertEqual(runtime.state.actors[naga].shield, 0.0)


if __name__ == "__main__":
    unittest.main()
