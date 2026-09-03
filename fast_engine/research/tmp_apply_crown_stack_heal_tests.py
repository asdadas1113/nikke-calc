from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_named_event_test() -> None:
    path = Path("fast_engine/tests/test_named_buff_event_runtime.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    def test_named_event_without_executable_named_buff_provider_stays_blocked(self):\n",
        "    def test_named_event_source_certification_stays_per_effect(self):\n",
        label="named-event test name",
    )
    text = replace_once(
        text,
        '        self.assertTrue(any("크라운:로얄 에타이어 4:atk_dmg_pct" in item for item in blockers))\n',
        '        self.assertFalse(any("크라운:로얄 에타이어 4:atk_dmg_pct" in item for item in blockers))\n',
        label="Crown self-only named-event expectation",
    )
    path.write_text(text, encoding="utf-8")


def patch_marker_test() -> None:
    path = Path("fast_engine/tests/test_statless_named_state_marker.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    def test_marker_support_removes_only_grave_delivery_dependency(self):\n",
        "    def test_marker_support_and_self_stack_heal_bridge_stay_narrow(self):\n",
        label="marker test name",
    )
    text = replace_once(
        text,
        '''        self.assertIn(\n            "normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",\n            crown_blockers,\n        )\n        self.assertIn(\n            "skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",\n            crown_blockers,\n        )\n''',
        '''        self.assertNotIn(\n            "normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",\n            crown_blockers,\n        )\n        self.assertNotIn(\n            "skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",\n            crown_blockers,\n        )\n''',
        label="Crown marker expectations",
    )
    path.write_text(text, encoding="utf-8")


def write_stack_heal_test() -> None:
    path = Path("fast_engine/tests/test_stack_heal_received_runtime.py")
    path.write_text('''from __future__ import annotations

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
''', encoding="utf-8")


def main() -> None:
    patch_named_event_test()
    patch_marker_test()
    write_stack_heal_test()
    print("applied Crown self-stack heal regression updates")


if __name__ == "__main__":
    main()
