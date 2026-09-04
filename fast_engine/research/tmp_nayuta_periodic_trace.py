from __future__ import annotations

from unittest.mock import patch

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.state import ENEMY
from fast_engine.engine.targets import TargetMode
from fast_engine.engine.triggers import TriggerMode
import fast_engine.engine.score as score_mod

from .public_ranking_probe import _fast_enemy, _source_corpus

TARGET_SOURCE = "레이드_델타"
ACTOR_NAME = "아스카 : WILLE"
STACK_NAME = "안티 AT 필드"
LM_BLOCKER = "skill_damage:리틀 머메이드:거품 난사:sequential_damage:10"


def _state_end_source_safe(squad, effect) -> bool:
    keys = tuple(
        rule.event_key or ""
        for rule in effect.triggers
        if (rule.event_key or "").startswith("event:state_end:")
    )
    if not keys or len(keys) != len(effect.triggers):
        return False
    if any(rule.mode is not TriggerMode.EVENT for rule in effect.triggers):
        return False
    for key in keys:
        name = key[len("event:state_end:"):]
        providers = tuple(
            provider
            for provider in squad.effects
            if provider.effect_id != effect.effect_id
            and provider.actor == effect.actor
            and provider.name == name
        )
        if len(providers) != 1:
            return False
        provider = providers[0]
        if not (
            provider.effect_type == "buff"
            and provider.target_spec.mode is TargetMode.SELF
            and provider.duration is not None
            and float(provider.duration) > 0.0
            and provider.parameters.get("duration_bullets") is None
            and TriggerDispatcher.is_executable_effect(provider)
        ):
            return False
    return True


def _regular_enemy_stack_provider(sink, actor: int, name: str):
    providers = tuple(
        provider
        for provider in sink.squad.effects
        if provider.actor == actor
        and provider.name == name
        and provider.effect_type == "buff"
        and provider.target_spec.mode is TargetMode.ENEMY
        and provider.max_stack is not None
        and float(provider.max_stack) > 1.0
        and provider.parameters.get("duration_bullets") is None
        and not provider.parameters
        and bool(provider.triggers)
        and all(rule.is_runtime_supported for rule in provider.condition_rules)
        and TriggerDispatcher.is_executable_effect(provider)
    )
    return providers[0] if len(providers) == 1 else None


def main() -> None:
    rows = [(members, source) for members, source in _source_corpus() if source == TARGET_SOURCE]
    assert len(rows) == 1, rows
    members, source = rows[0]
    raw = spec.build_squad(list(members))
    compiled = compile_moris_squad(raw)
    actor = members.index(ACTOR_NAME)
    config_dict = {
        "duration": 25.0,
        "first_burst_time": 3.0,
        "rng_mode": "expected",
    }
    config = spec.build_config(raw, dict(config_dict))
    policy = compile_burst_policy(raw, compiled, dict(config_dict))

    baseline = score_mod.static_score_blockers(compiled)
    print("BASELINE_BLOCKERS=" + repr(baseline))
    assert LM_BLOCKER in baseline
    assert "skill_damage:아스카 : WILLE:섬멸:bonus_damage" in baseline

    moris = simulate(
        raw,
        config=config,
        enemy=dict(DEFAULT_ENEMY),
        seed=42,
        verbose=True,
    )
    moris_annihilation = sum(
        float(hit.damage)
        for hit in moris.hits
        if hit.caster == ACTOR_NAME and hit.skill_name == "섬멸"
    )
    print("MORIS_ANNIHILATION=" + repr(moris_annihilation))

    original_delivery = SimpleDamageScoreSink._delivery_supported
    original_stack_shape = SimpleDamageScoreSink._stack_count_shape_supported
    original_stack_runtime = SimpleDamageScoreSink._stack_count_runtime_supported
    original_state_support = SimpleDamageScoreSink.supports_state_operation
    original_activate = SimpleDamageScoreSink.activate
    original_state_activate = SimpleDamageScoreSink.activate_state_operation
    original_static_blockers = score_mod.static_score_blockers

    trace: list[tuple] = []

    def delivery_supported(sink, effect):
        if original_delivery(sink, effect):
            return True
        return (
            effect.effect_type == "damage"
            and effect.target_spec.mode is TargetMode.ENEMY
            and effect.parameters.get("scaling") == "stack_count"
            and isinstance(effect.parameters.get("scaling_ref"), str)
            and bool(effect.parameters.get("scaling_ref"))
            and not effect.condition_rules
            and _state_end_source_safe(sink.squad, effect)
        )

    def stack_shape_supported(sink, effect, stack_spec):
        if original_stack_shape(sink, effect, stack_spec):
            return True
        return (
            _state_end_source_safe(sink.squad, effect)
            and _regular_enemy_stack_provider(sink, effect.actor, stack_spec.ref) is not None
        )

    def stack_runtime_supported(sink, effect):
        if original_stack_runtime(sink, effect):
            return True
        stack_spec = sink.stack_specs.get(effect.effect_id)
        if stack_spec is None or not _state_end_source_safe(sink.squad, effect):
            return False
        provider = _regular_enemy_stack_provider(sink, effect.actor, stack_spec.ref)
        if provider is None:
            return False
        return sink.runtime is None or sink.runtime.dispatcher.can_activate_effect(provider)

    def state_operation_supported(sink, effect):
        if original_state_support(sink, effect):
            return True
        if not (
            effect.effect_type == "instant"
            and (effect.stat or "") == "remove_named_buff"
            and effect.target_spec.mode is TargetMode.ENEMY
            and set(effect.parameters) == {"target_effect"}
            and isinstance(effect.parameters.get("target_effect"), str)
            and not effect.condition_rules
            and _state_end_source_safe(sink.squad, effect)
        ):
            return False
        provider = _regular_enemy_stack_provider(
            sink, effect.actor, str(effect.parameters["target_effect"])
        )
        if provider is None:
            return False
        return sink.runtime is None or sink.runtime.dispatcher.can_activate_effect(provider)

    def activate(sink, effect, *, now, targets, context):
        if effect.actor == actor and effect.name == "섬멸":
            assert sink.runtime is not None
            stack = sink.runtime.dispatcher.effects.named_stack(
                ENEMY, STACK_NAME, now=now
            )
            before = sink.char_total[actor]
            out = original_activate(
                sink, effect, now=now, targets=targets, context=context
            )
            trace.append(("damage", float(now), float(stack), sink.char_total[actor] - before))
            return out
        return original_activate(
            sink, effect, now=now, targets=targets, context=context
        )

    def activate_state_operation(sink, effect, *, now, targets):
        if effect.actor == actor and effect.name == "섬멸 2":
            assert sink.runtime is not None
            before = sink.runtime.dispatcher.effects.named_stack(ENEMY, STACK_NAME, now=now)
            out = original_state_activate(sink, effect, now=now, targets=targets)
            after = sink.runtime.dispatcher.effects.named_stack(ENEMY, STACK_NAME, now=now)
            trace.append(("remove", float(now), float(before), float(after), bool(out)))
            return out
        return original_state_activate(sink, effect, now=now, targets=targets)

    def diagnostic_blockers(squad):
        return tuple(
            blocker for blocker in original_static_blockers(squad)
            if blocker != LM_BLOCKER
        )

    with (
        patch.object(SimpleDamageScoreSink, "_delivery_supported", new=delivery_supported),
        patch.object(SimpleDamageScoreSink, "_stack_count_shape_supported", new=stack_shape_supported),
        patch.object(SimpleDamageScoreSink, "_stack_count_runtime_supported", new=stack_runtime_supported),
        patch.object(SimpleDamageScoreSink, "supports_state_operation", new=state_operation_supported),
        patch.object(SimpleDamageScoreSink, "activate", new=activate),
        patch.object(SimpleDamageScoreSink, "activate_state_operation", new=activate_state_operation),
        patch.object(score_mod, "static_score_blockers", new=diagnostic_blockers),
    ):
        widened = original_static_blockers(compiled)
        print("WIDENED_BLOCKERS=" + repr(widened))
        assert "skill_damage:아스카 : WILLE:섬멸:bonus_damage" not in widened, widened
        assert widened == (LM_BLOCKER,), widened

        fast = score_mod.score_static_squad(
            compiled,
            policy,
            _fast_enemy(duration=25.0),
            duration=25.0,
        )

    print("FAST_TRACE=" + repr(trace))
    print("FAST_UNSUPPORTED=" + repr(fast.unsupported))
    damage_rows = [row for row in trace if row[0] == "damage"]
    remove_rows = [row for row in trace if row[0] == "remove"]
    assert damage_rows and remove_rows, trace
    first_damage = damage_rows[0]
    first_remove = remove_rows[0]
    assert first_damage[2] == 30.0, first_damage
    assert first_remove[2:] == (30.0, 0.0, True), first_remove
    assert abs(first_damage[1] - first_remove[1]) < 1e-9, trace
    fast_annihilation = sum(float(row[3]) for row in damage_rows)
    print("FAST_ANNIHILATION=" + repr(fast_annihilation))
    print("ANNIHILATION_REL_ERR=" + repr(fast_annihilation / moris_annihilation - 1.0))
    assert abs(fast_annihilation / moris_annihilation - 1.0) < 0.01


if __name__ == "__main__":
    main()
