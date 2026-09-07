from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import (
    static_score_blockers,
    _temporary_self_rapid_weapon_change_score_supported,
    _rapid_actor_score_safe,
)
from fast_engine.engine.dispatcher import TriggerDispatcher

TEAMS = ("스쿼드2", "레이드_네온벨벳", "레이드_소다")

for team in TEAMS:
    case = snapshot.SQUADS[team]
    compiled = compile_moris_squad(spec.build_squad(list(case["members"])))
    print("\n===", team, tuple(case["members"]), flush=True)
    nayuta = next(i for i,m in enumerate(compiled.members) if m.name == "나유타")
    member = compiled.members[nayuta]
    print("NAYUTA_ACTOR", nayuta, flush=True)
    print("BASE_WEAPON", member.weapon, flush=True)
    print("RAPID_SAFE", _rapid_actor_score_safe(compiled, nayuta), flush=True)
    for effect in member.effects:
        print("EFFECT", effect.effect_id, {
            "name": effect.name,
            "type": effect.effect_type,
            "stat": effect.stat,
            "target": effect.target,
            "target_mode": effect.target_spec.mode.value,
            "value": effect.value,
            "duration": effect.duration,
            "max_stack": effect.max_stack,
            "max_trigger": effect.max_trigger,
            "tick_interval": effect.tick_interval,
            "parameters": effect.parameters,
            "conditions": [(r.mode.value, r.key, r.value) for r in effect.condition_rules],
            "triggers": [(r.mode.value, r.event_key, r.threshold, r.interval, r.trigger_count_reducible) for r in effect.triggers],
            "cap_disp": effect.capability.disposition.value,
            "cap_blockers": effect.capability.blockers,
        }, flush=True)
        if effect.effect_type == "weapon_change":
            print("WC_SHAPE", TriggerDispatcher._temporary_self_rapid_weapon_change_shape_supported(effect), flush=True)
            print("WC_SCORE", _temporary_self_rapid_weapon_change_score_supported(compiled, effect), flush=True)
    print("REFERENCES_MEMORY_BURN", flush=True)
    for effect in compiled.effects:
        refs = []
        for r in effect.condition_rules:
            if r.key == "기억 연소": refs.append(("condition", r.mode.value, r.key))
        for r in effect.triggers:
            if (r.event_key or "") == "event:state_end:기억 연소": refs.append(("trigger", r.mode.value, r.event_key))
        if effect.parameters.get("target_effect") == "기억 연소": refs.append(("target_effect", effect.parameters.get("target_effect")))
        if refs:
            print("REF", effect.effect_id, compiled.members[effect.actor].name, effect.name, effect.effect_type, effect.stat, refs, {
                "target": effect.target,
                "value": effect.value,
                "duration": effect.duration,
                "max_stack": effect.max_stack,
                "parameters": effect.parameters,
                "triggers": [(r.mode.value, r.event_key, r.threshold, r.interval, r.trigger_count_reducible) for r in effect.triggers],
                "conditions": [(r.mode.value, r.key, r.value) for r in effect.condition_rules],
            }, flush=True)
    print("NAYUTA_BLOCKERS", tuple(b for b in static_score_blockers(compiled) if ":나유타:" in b or b == "control:나유타"), flush=True)
