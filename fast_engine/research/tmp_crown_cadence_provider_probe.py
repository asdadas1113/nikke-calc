from __future__ import annotations

from context import spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.score import (
    _dynamic_ammo_charge_score_actors,
    _dynamic_max_ammo_score_actors,
    _dynamic_mg_warmup_score_actors,
    _dynamic_rapid_reload_score_actors,
    _dynamic_reload_score_actors,
)
from fast_engine.engine.target_scope import possible_ally_targets

from .public_ranking_probe import _source_corpus

CROWN = "크라운"
CADENCE_STATS = {
    "reload_speed_pct",
    "max_ammo_pct",
    "max_ammo_flat",
    "ammo_charge_pct",
    "ammo_charge_flat",
    "mg_warmup_speed_pct",
    "attack_speed_pct",
    "force_reload",
}


def main() -> None:
    members = next(tuple(m) for m, name in _source_corpus() if name == "레이드_델타")
    compiled = compile_moris_squad(spec.build_squad(list(members)))
    crown = compiled.names.index(CROWN)
    print("members", members)
    print("crown_actor", crown)
    print("dynamic_reload", _dynamic_reload_score_actors(compiled))
    print("dynamic_max_ammo", _dynamic_max_ammo_score_actors(compiled))
    print("dynamic_ammo_charge", _dynamic_ammo_charge_score_actors(compiled))
    print("dynamic_mg_warmup", _dynamic_mg_warmup_score_actors(compiled))
    print("dynamic_rapid", _dynamic_rapid_reload_score_actors(compiled))
    print("=== cadence providers that may target Crown ===")
    for effect in compiled.effects:
        stat = effect.stat or ""
        if effect.effect_type != "weapon_change" and stat not in CADENCE_STATS:
            continue
        targets = possible_ally_targets(compiled, effect)
        if crown not in targets:
            continue
        print({
            "owner": compiled.names[effect.actor],
            "name": effect.name,
            "type": effect.effect_type,
            "stat": stat,
            "value": effect.value,
            "duration": effect.duration,
            "max_stack": effect.max_stack,
            "target": effect.target,
            "target_mode": effect.target_spec.mode.value,
            "possible_targets": tuple(compiled.names[a] for a in targets),
            "triggers": tuple((r.raw, r.event_key, r.mode.value, r.threshold) for r in effect.triggers),
            "conditions": tuple((r.raw, r.mode.value) for r in effect.condition_rules),
            "parameters": dict(effect.parameters),
            "capability": effect.capability.disposition.value,
            "blockers": effect.capability.blockers,
            "static_exec": TriggerDispatcher.is_executable_effect(effect),
        })


if __name__ == "__main__":
    main()
