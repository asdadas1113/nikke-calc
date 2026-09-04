from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.scheduler import EventKind
from fast_engine.engine.score import static_score_blockers


NAMES = ["라피 : 레드 후드", "레드 후드", "프리카", "민트", "퀀시 : 이스케이프 퀸"]


class NamedBuffEventRuntimeTests(unittest.TestCase):
    @staticmethod
    def _runtime():
        squad = compile_moris_squad(build_squad(NAMES))
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=80.0, first_burst_time=70.0),
            EnemyStaticProfile(defense=0.0, duration=80.0),
        )
        return squad, runtime

    @staticmethod
    def _expire_through(runtime, time: float) -> None:
        while runtime.scheduler and (runtime.scheduler.peek_time() or 0.0) <= time + 1e-9:
            event = runtime.scheduler.pop()
            if event.kind is EventKind.STATE_EXPIRE:
                runtime.dispatcher.handle_expiry(event)

    def test_public_frika_encore_damage_delivery_is_source_certified(self):
        squad, _runtime = self._runtime()
        blockers = static_score_blockers(squad)
        self.assertFalse(any("프리카:앵콜 2:atk_dmg_pct" in item for item in blockers))

    def test_mint_named_buff_broadcast_runs_complete_frika_encore_chain(self):
        squad, runtime = self._runtime()
        frika = NAMES.index("프리카")
        mint = NAMES.index("민트")
        runtime.machine.ready_at[frika] = 40.0

        runtime.dispatcher.dispatch(BurstSignal(0.0, "burst_cast", frika, frika))
        self.assertTrue(
            runtime.dispatcher.effects.has_named_state(frika, "퍼포먼스", now=0.01)
        )

        runtime.dispatcher.dispatch(BurstSignal(1.0, "burst_cast", mint, mint))

        encore = next(e for e in squad.members[frika].effects if e.name == "앵콜")
        encore2 = next(e for e in squad.members[frika].effects if e.name == "앵콜 2")
        encore3 = next(e for e in squad.members[frika].effects if e.name == "앵콜 3")
        vocal = next(e for e in squad.members[frika].effects if e.name == "무대 파트 : 보컬")

        self.assertEqual(runtime.dispatcher._activation_counts.get(encore.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(encore2.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(encore3.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(vocal.effect_id, 0), 1)
        self.assertAlmostEqual(runtime.machine.ready_at[frika], 61.0, places=9)
        self.assertTrue(
            runtime.dispatcher.effects.has_named_state(mint, "무대 파트 : 보컬", now=1.01)
        )

        for actor in range(len(NAMES)):
            self.assertGreaterEqual(
                runtime.dispatcher.effects.sum_stat(actor, "atk_dmg_pct", now=1.01),
                float(encore2.value or 0.0),
            )

    def test_duration_extension_invalidates_original_expiry(self):
        _squad, runtime = self._runtime()
        frika = NAMES.index("프리카")
        mint = NAMES.index("민트")
        runtime.dispatcher.dispatch(BurstSignal(0.0, "burst_cast", frika, frika))
        runtime.dispatcher.dispatch(BurstSignal(1.0, "burst_cast", mint, mint))

        self._expire_through(runtime, 25.0)
        self.assertTrue(
            runtime.dispatcher.effects.has_named_state(frika, "퍼포먼스", now=25.01)
        )
        self._expire_through(runtime, 46.0)
        self.assertFalse(
            runtime.dispatcher.effects.has_named_state(frika, "퍼포먼스", now=46.01)
        )

    def test_moris_nop_named_marker_can_drive_supported_consumer(self):
        squad, runtime = self._runtime()
        red = NAMES.index("레드 후드")
        blockers = static_score_blockers(squad)
        self.assertFalse(any("레드 후드:와일드 투스 4:atk_pct" in item for item in blockers))
        self.assertFalse(any("레드 후드:글레링 아이즈:charge_speed_pct" in item for item in blockers))

        marker = next(e for e in squad.members[red].effects if e.name == "레드 울프")
        consumer = next(e for e in squad.members[red].effects if e.name == "와일드 투스 4")
        self.assertTrue(runtime.dispatcher._named_event_marker_nop_shape_supported(marker))
        self.assertFalse(runtime.dispatcher.is_executable_effect(marker))

        runtime.dispatcher.dispatch(BurstSignal(1.0, "squad_burst_cast:3", red, red))
        self.assertEqual(runtime.dispatcher._activation_counts.get(marker.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(consumer.effect_id, 0), 1)
        self.assertAlmostEqual(
            runtime.dispatcher.effects.sum_stat(red, "atk_pct", now=1.01),
            float(consumer.value or 0.0),
            places=9,
        )

    def test_named_event_source_certification_stays_per_effect(self):
        names = ["리틀 머메이드", "토브", "크라운", "아스카 : WILLE", "루드밀라 : 윈터 오너"]
        squad = compile_moris_squad(build_squad(names))
        blockers = static_score_blockers(squad)
        self.assertFalse(any("토브:임시 개조 2:crit_dmg" in item for item in blockers))
        self.assertFalse(any("크라운:로얄 에타이어 4:atk_dmg_pct" in item for item in blockers))


if __name__ == "__main__":
    unittest.main()
