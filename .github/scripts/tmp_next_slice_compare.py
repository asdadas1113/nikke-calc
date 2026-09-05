from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch marker: {label}")
    return text.replace(old, new, 1)


def apply_candidate() -> None:
    path = Path("fast_engine/engine/dispatcher.py")
    text = path.read_text(encoding="utf-8")
    marker = '''    @staticmethod
    def _periodic_timing_is_only_blocker(effect: "CompiledEffect") -> bool:
'''
    helper = '''    @staticmethod
    def _periodic_finite_enemy_received_damage_shape_supported(
        effect: "CompiledEffect",
    ) -> bool:
        """Certify a fixed-grid finite enemy received-damage stack."""
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(effect.capability.blockers) == {
                "category:hit_formula",
                "stat:received_dmg_pct",
                "timing:periodic",
                "condition:enemy",
                "target:enemy_singleton",
            }
            and effect.effect_type == "buff"
            and bool(effect.name)
            and (effect.stat or "") == "received_dmg_pct"
            and effect.target_spec.mode is TargetMode.ENEMY
            and effect.target_spec.runtime_supported
            and effect.value is not None
            and float(effect.value) >= 0.0
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack is not None
            and float(effect.max_stack) >= 1.0
            and float(effect.max_stack).is_integer()
            and effect.max_trigger is None
            and effect.tick_interval is None
            and not effect.parameters
            and len(effect.condition_rules) == 1
            and effect.condition_rules[0].mode is ConditionMode.TARGET_CODE
            and bool(effect.condition_rules[0].key)
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.PERIODIC
            and effect.triggers[0].interval is not None
            and float(effect.triggers[0].interval) > 0.0
        )

'''
    text = replace_once(text, marker, helper + marker, "dispatcher helper insert")
    old = '''            TriggerDispatcher._periodic_permanent_self_direct_stack_shape_supported(effect)
            or TriggerDispatcher._periodic_finite_self_crit_shape_supported(effect)
            or TriggerDispatcher._self_stack_reach_marker_shape_supported(effect)
'''
    new = '''            TriggerDispatcher._periodic_permanent_self_direct_stack_shape_supported(effect)
            or TriggerDispatcher._periodic_finite_self_crit_shape_supported(effect)
            or TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(effect)
            or TriggerDispatcher._self_stack_reach_marker_shape_supported(effect)
'''
    text = replace_once(text, old, new, "dispatcher executable")
    path.write_text(text, encoding="utf-8")

    path = Path("fast_engine/engine/score.py")
    text = path.read_text(encoding="utf-8")
    old = '''        TriggerDispatcher._periodic_permanent_self_direct_stack_shape_supported(effect)
        or TriggerDispatcher._periodic_finite_self_crit_shape_supported(effect)
    ):
'''
    new = '''        TriggerDispatcher._periodic_permanent_self_direct_stack_shape_supported(effect)
        or TriggerDispatcher._periodic_finite_self_crit_shape_supported(effect)
        or TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(effect)
    ):
'''
    text = replace_once(text, old, new, "score fixed periodic")
    path.write_text(text, encoding="utf-8")


def run_probe() -> None:
    # Import Fast only after the runner-only source patch so Python does not cache
    # the pre-patch dispatcher/score modules.
    from fast_engine.engine.burst import compile_burst_policy
    from fast_engine.engine.burst_runtime import BurstRuntime
    from fast_engine.engine.compiler import compile_moris_squad
    from fast_engine.engine.dispatcher import TriggerDispatcher
    from fast_engine.engine.model import EnemyStaticProfile
    from fast_engine.engine.score import static_score_blockers
    from fast_engine.engine.state import ENEMY

    team = "레이드_헬름아쿠아스노우"
    moris_squad = spec.build_squad(list(snapshot.SQUADS[team]["members"]))
    compiled = compile_moris_squad(moris_squad)
    helm = next(i for i, m in enumerate(compiled.members) if m.name == "헬름 : 아쿠아마린")
    effect = next(e for e in compiled.members[helm].effects if e.name == "이지스 캐논 견제 사격 2")
    rule = effect.triggers[0]
    print("HELM_EFFECT", {
        "interval": rule.interval,
        "value": effect.value,
        "duration": effect.duration,
        "max_stack": effect.max_stack,
        "condition": [(r.mode.value, r.key, r.value) for r in effect.condition_rules],
        "polarity": effect.polarity,
        "cap": tuple(effect.capability.blockers),
    })
    assert TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(effect)
    assert TriggerDispatcher.is_executable_effect(effect)

    blockers = set(static_score_blockers(compiled))
    normal = "normal_delivery:헬름 : 아쿠아마린:이지스 캐논 견제 사격 2:received_dmg_pct"
    skill = "skill_state_delivery:헬름 : 아쿠아마린:이지스 캐논 견제 사격 2:received_dmg_pct"
    assert normal not in blockers, blockers
    assert skill not in blockers, blockers
    assert "periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval" in blockers
    assert "weapon_change:스노우 화이트:세븐스 드워프 : I" in blockers
    print("PATCHED_BLOCKERS", tuple(sorted(blockers)))

    duration = 25.0
    config = {"duration": duration, "rng_mode": "expected"}
    enemy = dict(DEFAULT_ENEMY)
    enemy["code"] = "전격"
    policy = compile_burst_policy(moris_squad, compiled, config)
    fast_enemy = EnemyStaticProfile(
        defense=float(enemy.get("def", 31784.0)),
        element="전격",
        core_px=float(enemy.get("core_px", 0.0) or 0.0),
        core_uptime=1.0 if float(enemy.get("core_px", 0.0) or 0.0) > 0 else 0.0,
        duration=duration,
    )

    fast_trace = []
    original = TriggerDispatcher.dispatch_periodic

    def traced(dispatcher, effect_id, rule_index, *, time, context):
        result = original(dispatcher, effect_id, rule_index, time=time, context=context)
        if effect_id == effect.effect_id and effect_id in result.activated_effect_ids:
            fast_trace.append((
                time,
                dispatcher.effects.named_stack(ENEMY, effect.name, now=time),
                dispatcher.effects.sum_stat(ENEMY, "received_dmg_pct", now=time),
            ))
        return result

    with patch.object(TriggerDispatcher, "dispatch_periodic", new=traced):
        BurstRuntime(compiled, policy, enemy=fast_enemy).run(duration=duration)

    moris = simulate(
        moris_squad,
        config=config,
        enemy=enemy,
        verbose=True,
    )
    moris_events = [
        row for row in moris.log.buff_events
        if row.kind == "activate" and row.name == effect.name
    ]
    moris_times = [row.t for row in moris_events]
    print("FAST_TRACE", fast_trace)
    print("MORIS_TIMES", moris_times)
    print("MORIS_ROWS", [vars(row) if hasattr(row, "__dict__") else repr(row) for row in moris_events[:12]])
    assert len(fast_trace) == len(moris_times), (fast_trace, moris_times)
    for (actual, _stack, _value), expected in zip(fast_trace, moris_times):
        assert abs(actual - expected) <= 1e-9, (actual, expected)

    mismatch_enemy = dict(enemy)
    mismatch_enemy["code"] = "작열"
    mismatch_fast = EnemyStaticProfile(
        defense=float(mismatch_enemy.get("def", 31784.0)),
        element="작열",
        core_px=float(mismatch_enemy.get("core_px", 0.0) or 0.0),
        core_uptime=1.0 if float(mismatch_enemy.get("core_px", 0.0) or 0.0) > 0 else 0.0,
        duration=duration,
    )
    mismatch_trace = []

    def traced_mismatch(dispatcher, effect_id, rule_index, *, time, context):
        result = original(dispatcher, effect_id, rule_index, time=time, context=context)
        if effect_id == effect.effect_id and effect_id in result.activated_effect_ids:
            mismatch_trace.append(time)
        return result

    with patch.object(TriggerDispatcher, "dispatch_periodic", new=traced_mismatch):
        BurstRuntime(compiled, policy, enemy=mismatch_fast).run(duration=duration)
    moris_mismatch = simulate(moris_squad, config=config, enemy=mismatch_enemy, verbose=True)
    moris_mismatch_times = [
        row.t for row in moris_mismatch.log.buff_events
        if row.kind == "activate" and row.name == effect.name
    ]
    print("MISMATCH", mismatch_trace, moris_mismatch_times)
    assert mismatch_trace == []
    assert moris_mismatch_times == []


if __name__ == "__main__":
    apply_candidate()
    run_probe()
