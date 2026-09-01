from __future__ import annotations

import json
import unittest

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import (
    DIRECT_DAMAGE_STATE_STATS,
    _SAFE_CONDITIONS,
    _one_shot_lifetime_supported,
    _target_supported,
    _timing_supported,
    is_direct_damage_buff_runtime_supported,
)
from fast_engine.engine.score import static_score_blockers

NAMES = ["미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인"]


class HelmDeliveryProbe(unittest.TestCase):
    def test_surface_gate_inputs(self):
        squad = build_squad(NAMES)
        next(c for c in squad if c["name"] == "미하라 : 본딩 체인")["control"] = {}
        compiled = compile_moris_squad(squad)
        effects = [
            e for e in compiled.effects
            if e.actor == 2 and e.name == "이지스 캐논 3" and e.stat == "charge_dmg_mag_pct"
        ]
        rows = []
        for e in effects:
            rows.append({
                "effect_id": e.effect_id,
                "source": e.source,
                "source_tag": e.source_tag,
                "effect_type": e.effect_type,
                "stat": e.stat,
                "value": e.value,
                "duration": e.duration,
                "max_stack": e.max_stack,
                "target": e.target,
                "target_mode": e.target_spec.mode.value,
                "conditions": list(e.conditions),
                "condition_modes": [r.mode.value for r in e.condition_rules],
                "parameters": dict(e.parameters),
                "triggers": [
                    {
                        "raw": r.raw,
                        "event_key": r.event_key,
                        "mode": r.mode.value,
                        "timing_supported": _timing_supported(r),
                    }
                    for r in e.triggers
                ],
                "stat_known": (e.stat or "") in DIRECT_DAMAGE_STATE_STATS,
                "one_shot_supported": _one_shot_lifetime_supported(e),
                "target_supported": _target_supported(e.target_spec),
                "conditions_supported": all(r.mode in _SAFE_CONDITIONS for r in e.condition_rules),
                "runtime_supported": is_direct_damage_buff_runtime_supported(e),
            })
        report = {
            "favorite_stage": compiled.members[2].favorite_stage,
            "effect_count": len(effects),
            "effects": rows,
            "blockers": list(static_score_blockers(compiled)),
        }
        self.fail("INTENTIONAL_HELM_DELIVERY_GATE=" + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
