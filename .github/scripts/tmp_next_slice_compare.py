from __future__ import annotations

from pathlib import Path

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine import damage_policy, score as score_mod

TARGETS = {
    "레이드_헬름아쿠아스노우": (
        "섬광 수류탄 투척 발동 시간 조건",
        "이지스 캐논 견제 사격 2",
    ),
    "레이드_네온벨벳": ("초화력",),
}


def enum_value(value):
    return getattr(value, "value", str(value)) if value is not None else None


def effect_dump(compiled, effect):
    target = effect.target_spec
    return {
        "actor": compiled.members[effect.actor].name,
        "id": effect.effect_id,
        "name": effect.name,
        "type": effect.effect_type,
        "stat": effect.stat,
        "value": effect.value,
        "duration": effect.duration,
        "duration_bullets": getattr(effect, "duration_bullets", None),
        "max_stack": effect.max_stack,
        "max_trigger": getattr(effect, "max_trigger", None),
        "tick_interval": getattr(effect, "tick_interval", None),
        "target_mode": enum_value(target.mode),
        "target_runtime": target.runtime_supported,
        "target_raw": getattr(effect, "target", None),
        "triggers": [
            {
                "mode": enum_value(getattr(rule, "mode", None)),
                "event": getattr(rule, "event_key", None),
                "threshold": getattr(rule, "threshold", None),
                "modulo": getattr(rule, "modulo", None),
                "reducible": getattr(rule, "reducible", None),
                "params": getattr(rule, "params", None),
            }
            for rule in effect.triggers
        ],
        "conditions": [
            {
                "mode": enum_value(getattr(rule, "mode", None)),
                "key": getattr(rule, "key", None),
                "value": getattr(rule, "value", None),
            }
            for rule in effect.condition_rules
        ],
        "parameters": effect.parameters,
        "cap_disposition": enum_value(effect.capability.disposition),
        "cap_blockers": tuple(effect.capability.blockers),
        "dispatcher_executable": TriggerDispatcher.is_executable_effect(effect),
        "direct_damage_runtime": getattr(damage_policy, "is_direct_damage_buff_runtime_supported")(effect)
        if effect.effect_type == "buff"
        else None,
    }


def print_team(name: str):
    case = snapshot.SQUADS[name]
    members = tuple(str(x) for x in case["members"])
    compiled = compile_moris_squad(spec.build_squad(list(members)))
    print("\n=== TEAM", name, members)
    print("BLOCKERS", static_score_blockers(compiled))
    names = TARGETS[name]
    for effect in compiled.effects:
        if effect.name in names:
            print("TARGET_EFFECT", effect_dump(compiled, effect))
            for helper_name in (
                "_direct_damage_buff_score_supported",
                "_is_dynamic_charge_score_supported",
                "_named_buff_event_dependency_score_safe",
                "_periodic_grid_score_safe",
            ):
                helper = getattr(score_mod, helper_name, None)
                if helper is None:
                    continue
                try:
                    print(" SCORE_HELPER", helper_name, helper(compiled, effect))
                except Exception as exc:
                    print(" SCORE_HELPER", helper_name, type(exc).__name__, str(exc))
    return compiled


def source_snippets():
    needles = (
        "effect_interval",
        "received_dmg_pct",
        "stat_applied:received_dmg_pct",
        "이지스 캐논 견제 사격",
        "초화력",
    )
    roots = (Path("calculator"), Path("fast_engine"))
    print("\n=== SOURCE SNIPPETS")
    shown = 0
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace").splitlines()
            hits = [i for i, line in enumerate(text) if any(n in line for n in needles)]
            if not hits:
                continue
            for i in hits:
                lo = max(0, i - 6)
                hi = min(len(text), i + 12)
                print(f"--- {path}:{i+1}")
                for j in range(lo, hi):
                    print(f"{j+1:5d}: {text[j]}")
                shown += 1
                if shown >= 36:
                    return


def periodic_invalidator_dump():
    print("\n=== PERIODIC INVALIDATORS")
    for name in dir(score_mod):
        if "PERIODIC" in name.upper() and "INVALID" in name.upper():
            print(name, getattr(score_mod, name))


if __name__ == "__main__":
    print_team("레이드_헬름아쿠아스노우")
    print_team("레이드_네온벨벳")
    periodic_invalidator_dump()
    source_snippets()
