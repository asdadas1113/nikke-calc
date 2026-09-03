from __future__ import annotations

import unittest

from context import spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers


_SELF_ONLY = [
    "리틀 머메이드",
    "델타 : 닌자 시프",
    "크라운",
    "아스카 : WILLE",
    "라피 : 레드 후드",
]
_EXTERNAL_HEAL = [
    "리틀 머메이드",
    "나가",
    "크라운",
    "아스카 : WILLE",
    "루드밀라 : 윈터 오너",
]


class StackHealReceivedRuntimeTests(unittest.TestCase):
    @staticmethod
    def _royal_blockers(names: list[str]) -> tuple[str, ...]:
        squad = compile_moris_squad(spec.build_squad(names))
        return tuple(
            row for row in static_score_blockers(squad)
            if "크라운:로얄 에타이어 4:atk_dmg_pct" in row
        )

    def test_self_stack_heal_opens_but_external_heal_stays_fail_closed(self):
        self.assertEqual(self._royal_blockers(_SELF_ONLY), ())
        external = self._royal_blockers(_EXTERNAL_HEAL)
        self.assertIn(
            "normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",
            external,
        )
        self.assertIn(
            "skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",
            external,
        )

    def test_stack_reach_reset_self_heal_and_received_consumer_are_one_chain(self):
        squad = compile_moris_squad(spec.build_squad(_SELF_ONLY))
        crown = squad.names.index("크라운")
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=20.0, first_burst_time=30.0),
            EnemyStaticProfile(defense=0.0, duration=20.0),
        )
        marker = next(e for e in squad.members[crown].effects if e.name == "릴렉스")
        reset = next(e for e in squad.members[crown].effects if e.name == "로얄 에타이어")
        heal = next(e for e in squad.members[crown].effects if e.name == "로얄 에타이어 3")
        consumer = next(e for e in squad.members[crown].effects if e.name == "로얄 에타이어 4")

        for index in range(43 * 20):
            now = (index + 1) / 1000.0
            runtime.dispatcher.dispatch(BurstSignal(now, "hit_count", crown, crown))

        self.assertEqual(runtime.dispatcher._activation_counts.get(marker.effect_id, 0), 20)
        self.assertEqual(runtime.dispatcher._activation_counts.get(reset.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(heal.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(consumer.effect_id, 0), 1)
        self.assertEqual(
            runtime.dispatcher.effects.named_stack(crown, "릴렉스", now=1.0),
            0.0,
        )
        for actor in range(len(squad.members)):
            self.assertAlmostEqual(
                runtime.dispatcher.effects.sum_stat(actor, "atk_dmg_pct", now=1.0),
                float(consumer.value or 0.0),
                places=9,
            )


if __name__ == "__main__":
    unittest.main()
