from __future__ import annotations

import json
import unittest

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import (
    _SAFE_CONDITIONS,
    _one_shot_lifetime_supported,
    _target_supported,
    _timing_supported,
    is_direct_damage_buff_runtime_supported,
)
from fast_engine.engine.score import static_score_blockers


class LittleMermaidDeliveryProbe(unittest.TestCase):
    def test_surface_bubble_received_damage_gate(self):
        names = ["리틀 머메이드", "크라운", "라피 : 레드 후드", "미하라 : 본딩 체인", "헬름"]
        compiled = compile_moris_squad(build_squad(names))
        effects = [
            e for e in compiled.effects
            if compiled.names[e.actor] == "리틀 머메이드"
            and e.name == "거품"
            and e.stat == "received_dmg_pct"
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
                        "threshold": r.threshold,
                        "reducible": r.trigger_count_reducible,
                        "timing_supported": _timing_supported(r),
                    }
                    for r in e.triggers
                ],
                "lifetime_supported": _one_shot_lifetime_supported(e),
                "target_supported": _target_supported(e.target_spec),
                "conditions_supported": all(r.mode in _SAFE_CONDITIONS for r in e.condition_rules),
                "runtime_supported": is_direct_damage_buff_runtime_supported(e),
            })
        report = {
            "effects": rows,
            "blockers": [b for b in static_score_blockers(compiled) if ":리틀 머메이드:거품:" in b],
        }
        self.fail("INTENTIONAL_LITTLE_MERMAID_DELIVERY=" + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
