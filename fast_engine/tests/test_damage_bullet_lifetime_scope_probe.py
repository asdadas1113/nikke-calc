from __future__ import annotations

import json
import unittest

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.shot_blocks import static_bullet_lifetime_cadence_safe


CADENCE = {
    "reload_speed_pct",
    "max_ammo_pct",
    "max_ammo_flat",
    "max_ammo_infinite",
    "ammo_charge_flat",
    "ammo_charge_pct",
    "charge_speed_pct",
    "charge_speed_caster_based_pct",
    "charge_time_flat",
    "charge_time_fixed",
    "attack_speed_pct",
    "mg_warmup_speed_pct",
}


class BulletLifetimeScopeProbe(unittest.TestCase):
    def test_surface_public_helm_team_scope(self):
        names = ["리틀 머메이드", "크라운", "라피 : 레드 후드", "미하라 : 본딩 체인", "헬름"]
        compiled = compile_moris_squad(build_squad(names))
        helm_actor = compiled.names.index("헬름")
        rows = []
        for effect in compiled.effects:
            if effect.effect_type == "weapon_change" or (effect.stat or "") in CADENCE:
                rows.append({
                    "owner": compiled.names[effect.actor],
                    "name": effect.name,
                    "type": effect.effect_type,
                    "stat": effect.stat,
                    "target": effect.target,
                    "target_mode": effect.target_spec.mode.value,
                    "target_actor": effect.target_spec.count,
                    "duration": effect.duration,
                    "triggers": [r.raw for r in effect.triggers],
                })
        report = {
            "helm_actor": helm_actor,
            "helm_static_cadence_safe": static_bullet_lifetime_cadence_safe(compiled, helm_actor),
            "helm_blockers": [b for b in static_score_blockers(compiled) if ":헬름:" in b],
            "cadence_mutations": rows,
        }
        self.fail("INTENTIONAL_BULLET_SCOPE=" + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
