from __future__ import annotations

import unittest
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from context.spec import build_squad
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

if __name__ == "__main__":
    unittest.main()
