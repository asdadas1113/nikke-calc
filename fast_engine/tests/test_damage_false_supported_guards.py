from __future__ import annotations

import unittest
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

_NAMES = ["라피", "폴리", "프로덕트 12", "미란다", "아니스"]

def _effect(name: str, stat: str, *, target: str, duration: float, timing: str):
    return {
        "source": "skill1", "type": "buff", "name": name, "stat": stat,
        "fixed_value": 100.0, "polarity": "beneficial", "target": target,
        "duration": duration, "trigger": {"timing": [timing], "condition": []},
        "scaling": "stack_count", "scaling_ref": "AUDIT reference",
    }


def _conditional_passive(name: str, stat: str, condition: str):
    return {
        "source": "skill1", "type": "buff", "name": name, "stat": stat,
        "fixed_value": 100.0, "polarity": "beneficial", "target": "self",
        "duration": -1.0,
        "trigger": {"timing": ["passive"], "condition": [condition]},
    }

def _compiled(raw_effects):
    mapping = {_NAMES[0]: raw_effects}
    def fake_char_effects(self, name):
        return mapping.get(name, [])
    with patch.object(BuffManager, "char_effects", new=fake_char_effects):
        return compile_moris_squad(build_squad(_NAMES))

class FalseSupportedScalingGuardTests(unittest.TestCase):
    def test_reference_scaled_direct_buff_fails_closed(self):
        squad = _compiled([_effect("AUDIT scaled atk", "atk_pct", target="all_allies", duration=10.0, timing="burst_cast")])
        blockers = static_score_blockers(squad)
        self.assertIn("normal_delivery:라피:AUDIT scaled atk:atk_pct", blockers)
        self.assertIn("skill_state_delivery:라피:AUDIT scaled atk:atk_pct", blockers)

    def test_reference_scaled_permanent_cadence_buff_is_not_static_folded(self):
        squad = _compiled([_effect("AUDIT scaled reload", "reload_speed_pct", target="self", duration=-1.0, timing="battle_start")])
        self.assertIn("cadence:라피:AUDIT scaled reload:reload_speed_pct", static_score_blockers(squad))

    def test_unowned_full_burst_conditional_passive_fails_closed(self):
        squad = _compiled([_conditional_passive(
            "AUDIT conditional", "atk_pct", "during_full_burst"
        )])
        blockers = static_score_blockers(squad)
        self.assertIn("normal_delivery:라피:AUDIT conditional:atk_pct", blockers)
        self.assertIn("skill_state_delivery:라피:AUDIT conditional:atk_pct", blockers)

    def test_unowned_remove_of_scored_buff_fails_closed(self):
        provider = {
            "source": "skill1", "type": "buff", "name": "AUDIT state",
            "stat": "atk_pct", "fixed_value": 100.0,
            "polarity": "beneficial", "target": "self", "duration": -1.0,
            "trigger": {"timing": ["battle_start"], "condition": []},
        }
        remover = {
            "source": "skill1", "type": "instant", "name": "AUDIT remove",
            "stat": "remove_named_buff", "target": "self",
            "target_effect": "AUDIT state",
            "trigger": {"timing": ["full_burst_start"], "condition": []},
        }
        blockers = static_score_blockers(_compiled([provider, remover]))
        self.assertIn(
            "normal_state:라피:AUDIT remove:remove_named_buff", blockers
        )

    def test_rank_target_resolves_after_same_event_atk_mutation(self):
        rank = {
            "source": "skill1", "type": "buff", "name": "AUDIT rank",
            "stat": "crit_rate", "fixed_value": 50.0,
            "polarity": "beneficial", "target": "allies_top_atk:1",
            "duration": 10.0,
            "trigger": {"timing": ["full_burst_start"], "condition": []},
        }
        sibling = {
            "source": "skill1", "type": "buff", "name": "AUDIT rank sibling",
            "stat": "crit_dmg", "fixed_value": 20.0,
            "polarity": "beneficial", "target": "allies_top_atk:1",
            "duration": 10.0,
            "trigger": {"timing": ["full_burst_start"], "condition": []},
        }
        atk = {
            "source": "skill1", "type": "buff", "name": "AUDIT atk",
            "stat": "atk_pct", "fixed_value": 10000.0,
            "polarity": "beneficial", "target": "폴리",
            "duration": 10.0,
            "trigger": {"timing": ["full_burst_start"], "condition": []},
        }
        compiled = _compiled([rank, sibling, atk])
        blockers = static_score_blockers(compiled)
        self.assertNotIn(
            "normal_state:라피:AUDIT rank:rank_target_timing", blockers
        )
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(duration=2.0, first_burst_time=2.0, max_burst_count=0),
        )
        runtime.dispatcher.dispatch(BurstSignal(1.0, "full_burst_start", 0, 0))
        poli = _NAMES.index("폴리")
        # Query the sibling first: both same caster/time/raw effects must share
        # the post-mutation cohort even when their stats are read in reverse order.
        self.assertEqual(
            runtime.dispatcher.effects.sum_stat(poli, "crit_dmg", now=1.0),
            20.0,
        )
        self.assertEqual(
            runtime.dispatcher.effects.sum_stat(poli, "crit_rate", now=1.0),
            50.0,
        )
        for actor in range(len(_NAMES)):
            if actor == poli:
                continue
            self.assertEqual(
                runtime.dispatcher.effects.sum_stat(actor, "crit_rate", now=1.0),
                0.0,
            )

if __name__ == "__main__":
    unittest.main()
