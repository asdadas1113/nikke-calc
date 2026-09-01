from __future__ import annotations

import json
import unittest

from context import spec
from fast_engine.engine.compiler import compile_moris_squad

NAMES = ["미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인"]

class MiharaNoControlProbe(unittest.TestCase):
    def test_miranda_bullet_bound_metadata(self):
        moris_squad = spec.build_squad(NAMES)
        for char in moris_squad:
            if char["name"] == "미하라 : 본딩 체인":
                char["control"] = {}
        compiled = compile_moris_squad(moris_squad)
        effect = next(e for e in compiled.effects if e.name == "웨이크업! 4" and e.stat == "crit_rate")
        report = {
            "actor": compiled.members[effect.actor].name,
            "effect_id": effect.effect_id,
            "type": effect.effect_type,
            "name": effect.name,
            "stat": effect.stat,
            "value": effect.value,
            "duration": effect.duration,
            "target": effect.target,
            "conditions": list(effect.conditions),
            "triggers": [r.raw for r in effect.triggers],
            "parameters": dict(effect.parameters),
        }
        self.fail("INTENTIONAL_MIRANDA_BULLET_METADATA=" + json.dumps(report, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    unittest.main()
