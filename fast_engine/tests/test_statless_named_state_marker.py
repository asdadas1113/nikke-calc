from __future__ import annotations

import unittest

from context import spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.scheduler import EventKind
from fast_engine.engine.score import static_score_blockers


_GRAVE_TEAM = [
    "미란다",
    "그레이브",
    "에이다",
    "미하라 : 본딩 체인",
    "D : 킬러 와이프",
]
_RHQ_TEAM = [
    "라피 : 레드 후드",
    "레드 후드",
    "프리카",
    "민트",
    "퀀시 : 이스케이프 퀸",
]
_CROWN_TEAM = [
    "리틀 머메이드",
    "델타 : 닌자 시프",
    "크라운",
    "아스카 : WILLE",
    "라피 : 레드 후드",
]


class StatlessNamedStateMarkerTests(unittest.TestCase):
    def test_real_grave_marker_matches_narrow_shape(self):
        squad = compile_moris_squad(spec.build_squad(_GRAVE_TEAM))
        marker = next(
            effect for effect in squad.effects
            if squad.members[effect.actor].name == "그레이브"
            and effect.name == "미래 예지"
        )
        self.assertTrue(
            TriggerDispatcher._timed_self_named_state_marker_shape_supported(marker)
        )
        self.assertTrue(TriggerDispatcher.is_executable_effect(marker))

    def test_broader_statless_markers_stay_fail_closed(self):
        squad = compile_moris_squad(spec.build_squad(_RHQ_TEAM))
        performance = next(
            effect for effect in squad.effects
            if squad.members[effect.actor].name == "프리카"
            and effect.name == "퍼포먼스"
            and not (effect.stat or "")
        )
        mint = next(
            effect for effect in squad.effects
            if squad.members[effect.actor].name == "민트"
            and effect.name == "무대 파트 : 댄스"
            and not (effect.stat or "")
        )
        self.assertFalse(
            TriggerDispatcher._timed_self_named_state_marker_shape_supported(performance)
        )
        self.assertFalse(
            TriggerDispatcher._timed_self_named_state_marker_shape_supported(mint)
        )

    def test_real_grave_marker_expires_and_emits_state_end(self):
        squad = compile_moris_squad(spec.build_squad(_GRAVE_TEAM))
        grave = _GRAVE_TEAM.index("그레이브")
        marker = next(
            effect for effect in squad.effects
            if effect.actor == grave and effect.name == "미래 예지"
        )
        cooling = next(
            effect for effect in squad.effects
            if effect.actor == grave and effect.name == "방열 2"
        )
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=20.0, first_burst_time=30.0),
            EnemyStaticProfile(defense=0.0, duration=20.0),
        )

        result = runtime.dispatcher.dispatch(
            BurstSignal(1.0, "burst_cast", grave, grave, "2")
        )
        self.assertIn(marker.effect_id, result.activated_effect_ids)
        self.assertTrue(
            runtime.dispatcher.effects.has_named_state(grave, "미래 예지", now=1.0)
        )
        self.assertTrue(
            runtime.dispatcher.effects.has_named_state(grave, "미래 예지", now=10.999)
        )
        self.assertFalse(
            runtime.dispatcher.effects.has_named_state(grave, "미래 예지", now=11.0)
        )

        state_end_activated = set()
        while runtime.scheduler and runtime.scheduler.peek_time() <= 11.0 + 1e-9:
            event = runtime.scheduler.pop()
            if event.kind is EventKind.STATE_EXPIRE:
                runtime.dispatcher.handle_expiry(event)
            elif event.kind is EventKind.STATE_END_NOTIFY:
                owner, name = event.payload
                dispatch = runtime.dispatcher.dispatch(
                    BurstSignal(
                        event.time,
                        f"event:state_end:{name}",
                        int(owner),
                        int(owner),
                    )
                )
                if name == "미래 예지":
                    state_end_activated.update(dispatch.activated_effect_ids)

        self.assertIn(cooling.effect_id, state_end_activated)
        self.assertFalse(
            runtime.dispatcher.effects.has_named_state(grave, "미래 예지", now=11.0)
        )

    def test_marker_support_removes_only_grave_delivery_dependency(self):
        squad = compile_moris_squad(spec.build_squad(_GRAVE_TEAM))
        blockers = static_score_blockers(squad)
        self.assertFalse(any("그레이브:과열 II" in row for row in blockers))
        self.assertFalse(any("그레이브:과열 III" in row for row in blockers))

        crown = compile_moris_squad(spec.build_squad(_CROWN_TEAM))
        crown_blockers = static_score_blockers(crown)
        self.assertIn(
            "normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",
            crown_blockers,
        )
        self.assertIn(
            "skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",
            crown_blockers,
        )


if __name__ == "__main__":
    unittest.main()
