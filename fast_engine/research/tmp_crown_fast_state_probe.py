from __future__ import annotations

from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile

from .public_ranking_probe import COMMON_CONFIG, COMMON_ENEMY, _source_corpus

CROWN = "크라운"


def _enemy(duration: float) -> EnemyStaticProfile:
    core_px = float(COMMON_ENEMY.get("core_px", 0.0) or 0.0)
    return EnemyStaticProfile(
        defense=float(COMMON_ENEMY.get("def", 31784.0)),
        element=COMMON_ENEMY.get("code"),
        core_uptime=1.0 if core_px > 0 else 0.0,
        core_px=core_px,
        duration=duration,
    )


def main() -> None:
    rows = tuple((members, name) for members, name in _source_corpus() if CROWN in members)
    for members, source_name in rows:
        moris_squad = spec.build_squad(list(members))
        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(moris_squad, compiled, dict(COMMON_CONFIG))
        runtime = BurstRuntime(compiled, policy, _enemy(policy.duration))
        crown = compiled.names.index(CROWN)
        print(f"=== {source_name} crown_actor={crown} ===")
        for effect in compiled.members[crown].effects:
            if "릴렉스" not in (effect.name or "") and "로얄 에타이어" not in (effect.name or ""):
                continue
            print({
                "id": effect.effect_id,
                "name": effect.name,
                "type": effect.effect_type,
                "stat": effect.stat,
                "value": effect.value,
                "duration": effect.duration,
                "max_stack": effect.max_stack,
                "target": effect.target,
                "triggers": [(r.raw, r.event_key, r.mode.value, r.threshold) for r in effect.triggers],
                "conditions": [(r.raw, r.mode.value) for r in effect.condition_rules],
                "capability": effect.capability.disposition.value,
                "blockers": effect.capability.blockers,
                "static_exec": TriggerDispatcher.is_executable_effect(effect),
                "runtime_exec": runtime.dispatcher.is_runtime_executable_effect(effect),
                "can_activate": runtime.dispatcher.can_activate_effect(effect),
            })
        runtime.run(duration=policy.duration)
        counts = {
            key: value
            for key, value in runtime.dispatcher._event_counts.items()
            if key[0] == crown and ("stack_reach" in key[1] or "heal_received" in key[1] or "릴렉스" in key[1])
        }
        activations = {
            effect.name: runtime.dispatcher._activation_counts.get(effect.effect_id, 0)
            for effect in compiled.members[crown].effects
            if "릴렉스" in (effect.name or "") or "로얄 에타이어" in (effect.name or "")
        }
        print("event_counts", counts)
        print("activations", activations)


if __name__ == "__main__":
    main()
