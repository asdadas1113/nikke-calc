from __future__ import annotations

from collections import defaultdict

from calculator import timeline
from calculator.buff_manager import BuffManager
from context import spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

from .public_ranking_probe import COMMON_CONFIG, COMMON_ENEMY, _source_corpus

CROWN = "크라운"
ROYAL = "로얄 에타이어 4"
HEAL_STATS = {"heal_hp_pct", "lifesteal_pct"}


def _trigger_shape(effect):
    return tuple(
        (rule.raw, rule.event_key, rule.mode.value, rule.threshold)
        for rule in effect.triggers
    )


def _possible_crown_target(compiled, effect, crown_actor: int) -> bool:
    # Reuse the exact target resolver helper used by score certification when possible.
    from fast_engine.engine.target_scope import possible_ally_targets

    try:
        return crown_actor in possible_ally_targets(compiled, effect)
    except Exception:
        return False


def main() -> None:
    crown_rows = tuple(
        (members, source_name)
        for members, source_name in _source_corpus()
        if CROWN in members
    )
    if len(crown_rows) != 7:
        raise AssertionError(f"expected 7 Crown source cases, got {len(crown_rows)}")

    print("=== CROWN HEAL PROVIDER SHAPES ===")
    for members, source_name in crown_rows:
        moris_squad = spec.build_squad(list(members))
        compiled = compile_moris_squad(moris_squad)
        crown_actor = compiled.names.index(CROWN)
        blockers = tuple(
            b for b in static_score_blockers(compiled)
            if f"{CROWN}:{ROYAL}:atk_dmg_pct" in b
        )
        print(f"TEAM {source_name} members={members}")
        print(f"  royal_blockers={blockers}")
        providers = []
        for effect in compiled.effects:
            stat = effect.stat or ""
            if stat not in HEAL_STATS:
                continue
            owner = compiled.members[effect.actor].name
            providers.append(
                {
                    "owner": owner,
                    "name": effect.name,
                    "stat": stat,
                    "type": effect.effect_type,
                    "target": effect.target,
                    "possible_crown": _possible_crown_target(compiled, effect, crown_actor),
                    "triggers": _trigger_shape(effect),
                    "conditions": tuple(rule.raw for rule in effect.condition_rules),
                    "duration": effect.duration,
                    "value": effect.value,
                    "params": dict(effect.parameters),
                }
            )
        print(f"  heal_providers={providers}")

    # Moris is the semantic oracle. Intercept only Crown's received-heal event;
    # do not alter dispatch, activation or HP behavior.
    traces: dict[str, list[float]] = defaultdict(list)
    current_source = {"name": ""}
    original_notify = BuffManager.notify

    def traced_notify(self, event: str, t: float, caster: str, **ctx):
        if event == "event:heal_received" and caster == CROWN:
            traces[current_source["name"]].append(float(t))
        return original_notify(self, event, t, caster, **ctx)

    BuffManager.notify = traced_notify
    try:
        print("=== MORIS CROWN HEAL_RECEIVED TRACE ===")
        for members, source_name in crown_rows:
            current_source["name"] = source_name
            moris_squad = spec.build_squad(list(members))
            config = spec.build_config(moris_squad, dict(COMMON_CONFIG))
            timeline.simulate(
                moris_squad,
                config=config,
                enemy=dict(COMMON_ENEMY),
                seed=42,
                verbose=False,
            )
            times = traces[source_name]
            print(
                f"TRACE {source_name} count={len(times)} "
                f"first={times[:12]} last={times[-5:] if times else []}"
            )
    finally:
        BuffManager.notify = original_notify

    active = sorted(name for name, times in traces.items() if times)
    silent = sorted(name for _members, name in crown_rows if not traces[name])
    print(f"ACTIVE_TEAMS={active}")
    print(f"SILENT_TEAMS={silent}")


if __name__ == "__main__":
    main()
