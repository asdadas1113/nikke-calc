from __future__ import annotations

from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import BurstMachine, compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers
from fast_engine.engine.state import ENEMY as ENEMY_TARGET
from fast_engine.engine.targets import TargetMode
from fast_engine.engine.triggers import TriggerMode

NAMES = ["미란다", "아스카 : WILLE", "브리드 : 사일런트 트랙", "헬름", "루주"]
ASUKA = 1
DURATION = 180.0
CONFIG = {"duration": DURATION, "first_burst_time": 3.0, "rng_mode": "expected"}
ENEMY_CONFIG = dict(DEFAULT_ENEMY)
ENEMY_CONFIG.update({"def": 55000.0, "code": "작열", "core_px": 10.0})
PROFILE = EnemyStaticProfile(
    defense=55000.0,
    element="작열",
    core_uptime=1.0,
    core_px=10.0,
    duration=DURATION,
)


def build():
    raw = spec.build_squad(NAMES)
    return raw, compile_moris_squad(raw)


def state_end_safe(squad_obj, effect):
    keys = [rule.event_key or "" for rule in effect.triggers]
    if not keys or any(
        rule.mode is not TriggerMode.EVENT or not key.startswith("event:state_end:")
        for rule, key in zip(effect.triggers, keys)
    ):
        return False
    for key in keys:
        name = key[len("event:state_end:") :]
        providers = [
            item
            for item in squad_obj.effects
            if item.actor == effect.actor
            and item.effect_id != effect.effect_id
            and item.name == name
        ]
        if len(providers) != 1:
            return False
        provider = providers[0]
        if not (
            provider.effect_type == "buff"
            and provider.target_spec.mode is TargetMode.SELF
            and provider.duration is not None
            and float(provider.duration) >= 0.0
            and provider.parameters.get("duration_bullets") is None
            and TriggerDispatcher.is_executable_effect(provider)
        ):
            return False
    return True


def finite_provider(sink, effect, ref, runtime=False):
    providers = [
        item
        for item in sink.squad.effects
        if item.actor == effect.actor and item.name == ref
    ]
    if len(providers) != 1:
        return None
    provider = providers[0]
    ok = (
        provider.effect_type == "buff"
        and provider.target_spec.mode is TargetMode.ENEMY
        and provider.duration is not None
        and float(provider.duration) > 0.0
        and provider.max_stack is not None
        and float(provider.max_stack) > 1.0
        and not provider.parameters
        and TriggerDispatcher.is_executable_effect(provider)
    )
    if not ok:
        return None
    if runtime and sink.runtime is not None and not sink.runtime.dispatcher.can_activate_effect(provider):
        return None
    return provider


def main() -> None:
    raw, squad = build()
    annihilate = next(
        effect
        for effect in squad.effects
        if effect.actor == ASUKA and effect.name == "섬멸" and effect.effect_type == "damage"
    )

    old_delivery = SimpleDamageScoreSink._delivery_supported
    old_shape = SimpleDamageScoreSink._stack_count_shape_supported
    old_runtime = SimpleDamageScoreSink._stack_count_runtime_supported
    old_remove = TriggerDispatcher._enemy_remove_named_state_runtime_supported
    old_score = SimpleDamageScoreSink._score_spec
    old_cast_signals = BurstMachine._cast_signals

    def delivery(sink, effect):
        return old_delivery(sink, effect) or (
            effect.target_spec.mode is TargetMode.ENEMY
            and state_end_safe(sink.squad, effect)
        )

    def stack_shape(sink, effect, stack_spec):
        return old_shape(sink, effect, stack_spec) or finite_provider(
            sink, effect, stack_spec.ref
        ) is not None

    def stack_runtime(sink, effect):
        if old_runtime(sink, effect):
            return True
        stack_spec = sink.stack_specs.get(effect.effect_id)
        return stack_spec is not None and finite_provider(
            sink, effect, stack_spec.ref, True
        ) is not None

    def remove_runtime(dispatcher, effect):
        if old_remove(dispatcher, effect):
            return True
        if not (
            effect.effect_type == "instant"
            and (effect.stat or "") == "remove_named_buff"
            and effect.target_spec.mode is TargetMode.ENEMY
            and set(effect.parameters) == {"target_effect"}
            and not effect.condition_rules
            and state_end_safe(dispatcher.squad, effect)
        ):
            return False
        ref = str(effect.parameters["target_effect"])
        providers = [
            item
            for item in dispatcher.squad.effects
            if item.actor == effect.actor and item.name == ref
        ]
        return (
            len(providers) == 1
            and providers[0].target_spec.mode is TargetMode.ENEMY
            and TriggerDispatcher.is_executable_effect(providers[0])
            and dispatcher.can_activate_effect(providers[0])
        )

    fast_rows = []
    fast_casts = []

    def traced_score(sink, effect_id, *, now, full_burst):
        ref = (
            sink.runtime.dispatcher.effects.named_stack(
                ENEMY_TARGET, "안티 AT 필드", now=now
            )
            if effect_id == annihilate.effect_id and sink.runtime is not None
            else None
        )
        before = sink.char_total[ASUKA]
        out = old_score(sink, effect_id, now=now, full_burst=full_burst)
        if effect_id == annihilate.effect_id:
            fast_rows.append((float(now), ref, sink.char_total[ASUKA] - before))
        return out

    def traced_cast_signals(machine, actor, stage, now):
        if actor == ASUKA:
            fast_casts.append((float(now), str(stage), int(machine.cycle_count)))
        return old_cast_signals(machine, actor, stage, now)

    with (
        patch.object(SimpleDamageScoreSink, "_delivery_supported", new=delivery),
        patch.object(SimpleDamageScoreSink, "_stack_count_shape_supported", new=stack_shape),
        patch.object(SimpleDamageScoreSink, "_stack_count_runtime_supported", new=stack_runtime),
        patch.object(TriggerDispatcher, "_enemy_remove_named_state_runtime_supported", new=remove_runtime),
        patch.object(SimpleDamageScoreSink, "_score_spec", new=traced_score),
        patch.object(BurstMachine, "_cast_signals", new=traced_cast_signals),
    ):
        blockers = static_score_blockers(squad)
        assert blockers == (), blockers
        fast = score_static_squad(
            squad,
            compile_burst_policy(raw, squad, CONFIG),
            PROFILE,
            duration=DURATION,
        )

    fast_stacks = [int(stack) for _, stack, _ in fast_rows]
    assert fast_stacks, "no Fast annihilation rows"
    print(f"FAST_TOTAL={fast.squad_total:.9f}")
    print(f"FAST_ANNIHILATE_STACKS={fast_stacks}")
    print("FAST_ANNIHILATE_ROWS=" + repr(fast_rows))
    print("FAST_ASUKA_CASTS=" + repr(fast_casts))

    original_notify = BuffManager.notify
    rel_errors = []
    for seed in range(30):
        raw_m, _ = build()
        moris_state = []
        moris_casts = []

        def notify(manager, event, t, caster, **ctx):
            if caster == "아스카 : WILLE" and event == "burst_cast":
                moris_casts.append(float(t))
            if caster == "아스카 : WILLE" and event == "event:state_end:섬멸 태세":
                stack = max(
                    (
                        active.stack
                        for active in manager._active
                        if active.caster == caster
                        and active.effect.get("name") == "안티 AT 필드"
                    ),
                    default=0,
                )
                moris_state.append((float(t), int(stack)))
            return original_notify(manager, event, t, caster, **ctx)

        with patch.object(BuffManager, "notify", new=notify):
            moris = simulate(
                raw_m,
                config=spec.build_config(raw_m, CONFIG),
                enemy=dict(ENEMY_CONFIG),
                seed=seed,
                verbose=False,
            )

        moris_stacks = [stack for _, stack in moris_state]
        rel = float(fast.squad_total) / float(moris.squad_total) - 1.0
        rel_errors.append(rel)
        if seed == 0:
            print("MORIS_ASUKA_CASTS=" + repr(moris_casts))
            print("MORIS_STATE_END_ROWS=" + repr(moris_state))
        assert moris_stacks == fast_stacks, (
            f"seed={seed} stack mismatch: Moris={moris_stacks} Fast={fast_stacks}"
        )
        assert abs(rel) < 0.001, f"seed={seed} relative error {rel:.9%} exceeds 0.1%"
        print(
            f"SEED={seed:02d} MORIS_TOTAL={float(moris.squad_total):.9f} "
            f"REL={rel:.9%} STACKS={moris_stacks}"
        )

    print(
        "ASUKA_180S_30SEED_PASS "
        f"min_rel={min(rel_errors):.9%} max_rel={max(rel_errors):.9%} "
        f"max_abs={max(abs(value) for value in rel_errors):.9%}"
    )


if __name__ == "__main__":
    main()
