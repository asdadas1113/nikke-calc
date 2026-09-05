from __future__ import annotations

import unittest
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers


NAMES = ["라피", "폴리", "프로덕트 12", "미란다", "아니스"]


def compiled(raw_effects):
    mapping = {NAMES[0]: raw_effects}

    def fake_char_effects(self, name):
        return mapping.get(name, [])

    with patch.object(BuffManager, "char_effects", new=fake_char_effects):
        return compile_moris_squad(build_squad(NAMES))


class FiniteReferenceStackCaptureTests(unittest.TestCase):
    def test_owned_finite_ref_freezes_then_refresh_recaptures(self):
        provider = {
            "source": "skill1", "type": "buff", "name": "AUDIT reference",
            "stat": "accuracy_pct", "fixed_value": 1.0,
            "polarity": "beneficial", "target": "self", "duration": -1.0,
            "max_stack": 3,
            "trigger": {"timing": ["burst_enter:1"], "condition": []},
        }
        consumer = {
            "source": "skill2", "type": "buff", "name": "AUDIT captured",
            "stat": "crit_dmg", "fixed_value": 10.0,
            "polarity": "beneficial", "target": "all_allies", "duration": 10.0,
            "trigger": {"timing": ["burst_cast"], "condition": []},
            "scaling": "stack_count", "scaling_ref": "AUDIT reference",
        }
        squad = compiled([provider, consumer])
        blockers = static_score_blockers(squad)
        self.assertNotIn("normal_delivery:라피:AUDIT captured:crit_dmg", blockers)
        self.assertNotIn("skill_state_delivery:라피:AUDIT captured:crit_dmg", blockers)

        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=20.0, first_burst_time=20.0, max_burst_count=0),
        )
        dispatch = runtime.dispatcher.dispatch
        for t in (1.0, 2.0, 3.0):
            dispatch(BurstSignal(t, "burst_enter:1", 0, 0))
        dispatch(BurstSignal(4.0, "burst_cast", 0, 0))
        self.assertEqual(runtime.dispatcher.effects.sum_stat(0, "crit_dmg", now=4.0), 30.0)

        runtime.dispatcher.effects.adjust_named_stack(
            0, "AUDIT reference", -2.0, now=5.0
        )
        # Existing finite consumer stays at the activation-time 3-stack value.
        self.assertEqual(runtime.dispatcher.effects.sum_stat(0, "crit_dmg", now=5.0), 30.0)

        # Refresh captures the now-current one stack.
        dispatch(BurstSignal(6.0, "burst_cast", 0, 0))
        self.assertEqual(runtime.dispatcher.effects.sum_stat(0, "crit_dmg", now=6.0), 10.0)

    def test_missing_provider_stays_fail_closed(self):
        consumer = {
            "source": "skill2", "type": "buff", "name": "AUDIT missing",
            "stat": "atk_pct", "fixed_value": 10.0,
            "polarity": "beneficial", "target": "all_allies", "duration": 10.0,
            "trigger": {"timing": ["burst_cast"], "condition": []},
            "scaling": "stack_count", "scaling_ref": "NO provider",
        }
        blockers = static_score_blockers(compiled([consumer]))
        self.assertIn("normal_delivery:라피:AUDIT missing:atk_pct", blockers)
        self.assertIn("skill_state_delivery:라피:AUDIT missing:atk_pct", blockers)

    def test_permanent_reference_remains_live_unowned(self):
        provider = {
            "source": "skill1", "type": "buff", "name": "AUDIT reference",
            "stat": "accuracy_pct", "fixed_value": 1.0,
            "polarity": "beneficial", "target": "self", "duration": -1.0,
            "max_stack": 3,
            "trigger": {"timing": ["battle_start"], "condition": []},
        }
        consumer = {
            "source": "skill2", "type": "buff", "name": "AUDIT permanent",
            "stat": "reload_speed_pct", "fixed_value": 10.0,
            "polarity": "beneficial", "target": "self", "duration": -1.0,
            "trigger": {"timing": ["battle_start"], "condition": []},
            "scaling": "stack_count", "scaling_ref": "AUDIT reference",
        }
        blockers = static_score_blockers(compiled([provider, consumer]))
        self.assertIn("cadence:라피:AUDIT permanent:reload_speed_pct", blockers)

    def test_public_maidden_mast_ref_blockers_are_owned_but_other_gaps_remain(self):
        squad = compile_moris_squad(build_squad([
            "목단", "마스트 : 로망틱 메이드", "홍련 : 흑영", "리버렐리오", "앵커 : 이노센트 메이드"
        ]))
        blockers = static_score_blockers(squad)
        # Reference capture is owned, and Anchor's third-full-burst generic
        # harmful-stack decrement now proves the stack-3 remover unreachable in
        # this roster. Independent cadence and rank-target gaps remain.
        self.assertIn(
            "cadence:마스트 : 로망틱 메이드:파이레츠 스피릿 2:reload_speed_pct", blockers
        )
        self.assertNotIn(
            "normal_delivery:마스트 : 로망틱 메이드:파이레츠 로망 3:atk_caster_based_pct", blockers
        )
        self.assertNotIn(
            "skill_state_delivery:마스트 : 로망틱 메이드:파이레츠 스피릿:split_dmg_pct", blockers
        )
        self.assertNotIn(
            "skill_state_delivery:마스트 : 로망틱 메이드:파이레츠 로망 3:atk_caster_based_pct", blockers
        )
        self.assertNotIn(
            "normal_state:마스트 : 로망틱 메이드:파이레츠 스피릿 3:remove_named_buff", blockers
        )

    def test_arcana_owned_self_provider_opens_but_tove_provider_does_not(self):
        squad = compile_moris_squad(build_squad([
            "토브", "아르카나 : 포츈 메이트", "도로시 : 세렌디피티", "드레이크", "솔린 : 프로스트 티켓"
        ]))
        blockers = static_score_blockers(squad)
        self.assertNotIn(
            "normal_delivery:아르카나 : 포츈 메이트:쌓여가는 사진첩:atk_caster_based_pct", blockers
        )
        self.assertNotIn(
            "skill_state_delivery:아르카나 : 포츈 메이트:쌓여가는 사진첩:atk_caster_based_pct", blockers
        )
        self.assertIn(
            "normal_delivery:토브:급조품의 기적:atk_caster_based_pct", blockers
        )
        self.assertIn(
            "normal_delivery:토브:급조품의 기적 2:atk_caster_based_pct", blockers
        )


if __name__ == "__main__":
    unittest.main()