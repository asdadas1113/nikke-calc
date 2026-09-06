from __future__ import annotations

from dataclasses import dataclass

from .conditions import ConditionMode
from .model import CompiledSquad
from .reference_stack import finite_reference_stack_capture_shape
from .target_scope import possible_ally_targets
from .targets import TargetMode
from .triggers import TriggerMode

_EPS = 1e-9
_STACK_MUTATOR_STATS = frozenset({
    "remove_named_buff",
    "buff_stack_add",
    "buff_stack_remove",
    "buff_stack_init",
    "debuff_stack_add",
    "debuff_stack_remove",
})


@dataclass(frozen=True, slots=True)
class OwnedControlLifecycle:
    """Compile-time ownership proof for one exact self-control transaction."""

    actor: int
    stack_effect_id: int
    control_effect_id: int
    remover_effect_id: int
    passive_effect_ids: tuple[int, ...]


def _one_event(effect, key: str) -> bool:
    return (
        len(effect.triggers) == 1
        and effect.triggers[0].mode is TriggerMode.EVENT
        and effect.triggers[0].event_key == key
    )


def _stack3_condition(effect, name: str) -> bool:
    return (
        len(effect.condition_rules) == 1
        and effect.condition_rules[0].mode is ConditionMode.SELF_STACK_AT_LEAST
        and effect.condition_rules[0].key == name
        and abs(float(effect.condition_rules[0].value or 0.0) - 3.0) <= _EPS
    )


def _passive_shape(effect, *, actor: int, provider_name: str) -> bool:
    if effect.name not in {"파이레츠 하트", "파이레츠 하트 2"}:
        return False
    if not (
        effect.actor == actor
        and effect.effect_type == "buff"
        and effect.target_spec.mode is TargetMode.ALL_ALLIES
        and effect.target_spec.runtime_supported
        and effect.duration in (None, -1, -1.0)
        and effect.max_stack in (None, 1, 1.0)
        and effect.max_trigger is None
        and effect.tick_interval is None
        and not effect.parameters
        and len(effect.condition_rules) == 1
        and effect.condition_rules[0].mode is ConditionMode.SELF_STATE
        and effect.condition_rules[0].key == provider_name
        and len(effect.triggers) == 1
        and effect.triggers[0].mode is TriggerMode.EVENT
        and effect.triggers[0].event_key == "battle_start"
        and effect.triggers[0].raw == "passive"
    ):
        return False
    return (effect.stat or "") in {"crit_rate", "atk_caster_based_pct"}


def _weapon_shape_supported(squad: CompiledSquad, actor: int) -> bool:
    member = squad.members[actor]
    weapon = member.weapon
    return (
        str(member.weapon_type) == "MG"
        and str(weapon.get("fire_mode") or "") == "auto_warmup"
        and not weapon.get("is_clip")
        and not weapon.get("cover_during_delay")
        and not weapon.get("control")
    )


def certified_stack3_self_stun_remove_lifecycles(
    squad: CompiledSquad,
) -> tuple[OwnedControlLifecycle, ...]:
    """Own only the exact Maid-Mast stack-3 hangover/removal dependency graph.

    Character names never participate. The proof is deliberately shape- and
    state-name-specific so generic stun/remove families remain fail-closed.
    """

    out: list[OwnedControlLifecycle] = []
    effects = tuple(squad.effects)
    for provider in effects:
        if not (
            provider.name == "취기"
            and provider.effect_type == "buff"
            and (provider.stat or "") == "accuracy_pct"
            and provider.polarity == "harmful"
            and provider.target_spec.mode is TargetMode.SELF
            and provider.target_spec.runtime_supported
            and provider.value is not None
            and abs(float(provider.value) + 20.0) <= _EPS
            and provider.duration in (None, -1, -1.0)
            and abs(float(provider.max_stack or 0.0) - 3.0) <= _EPS
            and provider.max_trigger is None
            and provider.tick_interval is None
            and not provider.parameters
            and not provider.condition_rules
            and _one_event(provider, "burst_enter:1")
        ):
            continue
        actor = provider.actor
        if tuple(possible_ally_targets(squad, provider)) != (actor,):
            continue
        if sum(1 for row in effects if row.name == provider.name) != 1:
            continue
        if not _weapon_shape_supported(squad, actor):
            continue
        if any(
            row.effect_type == "weapon_change"
            and actor in possible_ally_targets(squad, row)
            for row in effects
        ):
            continue

        controls = tuple(
            row for row in squad.members[actor].effects
            if row.name == "숙취"
            and row.effect_type == "buff"
            and (row.stat or "") == "stun"
            and row.polarity == "harmful"
            and row.target_spec.mode is TargetMode.SELF
            and row.target_spec.runtime_supported
            and row.value is None
            and row.duration is not None
            and abs(float(row.duration) - 10.0) <= _EPS
            and row.max_stack in (None, 1, 1.0)
            and row.max_trigger is None
            and row.tick_interval is None
            and not row.parameters
            and _stack3_condition(row, provider.name)
            and _one_event(row, "full_burst_end")
        )
        removers = tuple(
            row for row in squad.members[actor].effects
            if row.name == "파이레츠 스피릿 3"
            and row.effect_type == "instant"
            and (row.stat or "") == "remove_named_buff"
            and row.target_spec.mode is TargetMode.SELF
            and row.target_spec.runtime_supported
            and row.value is None
            and row.duration is None
            and row.max_stack is None
            and row.max_trigger is None
            and row.tick_interval is None
            and set(row.parameters) == {"target_effect"}
            and row.parameters.get("target_effect") == provider.name
            and _stack3_condition(row, provider.name)
            and _one_event(row, "full_burst_end")
        )
        if len(controls) != 1 or len(removers) != 1:
            continue
        control, remover = controls[0], removers[0]
        actor_rows = squad.members[actor].effects
        control_pos = actor_rows.index(control)
        remover_pos = actor_rows.index(remover)
        if remover_pos != control_pos + 1:
            continue

        # No competing control/immunity may affect this actor.
        conflict = False
        for row in effects:
            targets = set(possible_ally_targets(squad, row))
            if row.effect_id != control.effect_id and (row.stat or "") == "stun" and actor in targets:
                conflict = True
                break
            if (row.stat or "") == "stun_immune" and actor in targets:
                conflict = True
                break
        if conflict:
            continue

        passives = tuple(
            row for row in squad.members[actor].effects
            if _passive_shape(row, actor=actor, provider_name=provider.name)
        )
        if len(passives) != 2:
            continue
        if {row.name for row in passives} != {"파이레츠 하트", "파이레츠 하트 2"}:
            continue

        allowed_condition_ids = {
            control.effect_id,
            remover.effect_id,
            *(row.effect_id for row in passives),
        }
        if any(
            row.effect_id not in allowed_condition_ids
            and not (
                row.actor == actor
                and row.parameters.get("scaling_ref") == provider.name
                and finite_reference_stack_capture_shape(row)
            )
            and any(rule.key == provider.name for rule in row.condition_rules)
            for row in effects
        ):
            continue

        # Captured finite scaling_ref consumers are already independently owned;
        # they are intentionally allowed to outlive removal of the source state.
        bad_reference = False
        for row in effects:
            if row.parameters.get("scaling_ref") != provider.name:
                continue
            if row.actor != actor or not finite_reference_stack_capture_shape(row):
                bad_reference = True
                break
        if bad_reference:
            continue

        # The paired remover is the only direct named mutator. Target-less stack
        # mutators are also rejected if their ally cohort could touch this actor.
        bad_mutator = False
        for row in effects:
            stat = row.stat or ""
            if row.effect_id == remover.effect_id:
                continue
            if row.parameters.get("target_effect") == provider.name:
                bad_mutator = True
                break
            if stat in _STACK_MUTATOR_STATS and not row.parameters.get("target_effect"):
                if actor in possible_ally_targets(squad, row):
                    bad_mutator = True
                    break
        if bad_mutator:
            continue

        state_end_key = f"event:state_end:{provider.name}"
        named_event_key = f"event:{provider.name}"
        if any(
            row.effect_id not in {control.effect_id, remover.effect_id}
            and any((rule.event_key or "") in {state_end_key, named_event_key} for rule in row.triggers)
            for row in effects
        ):
            continue

        out.append(
            OwnedControlLifecycle(
                actor=actor,
                stack_effect_id=provider.effect_id,
                control_effect_id=control.effect_id,
                remover_effect_id=remover.effect_id,
                passive_effect_ids=tuple(sorted(row.effect_id for row in passives)),
            )
        )
    return tuple(out)
