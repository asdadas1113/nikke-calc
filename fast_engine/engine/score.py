from __future__ import annotations

from math import inf, nextafter
from typing import TYPE_CHECKING

from .conditions import ConditionMode
from .core_events import is_static_expected_core_count_rule
from .damage_policy import (
    DIRECT_DAMAGE_STATE_STATS,
    is_direct_damage_buff_runtime_supported,
    is_static_element_override_score_supported,
)
from .damage_state import DamageTermResolver
from .dispatcher import TriggerDispatcher
from .dynamic_rapid import is_supported_rapid_cover_control
from .model import CompiledSquad, EnemyStaticProfile, FastScore
from .normal_attack import NormalAttackSpec, compile_normal_attack_spec, expected_normal_block_damage
from .shot_blocks import (
    ShotBlockCursor,
    compile_static_shot_blocks,
    static_bullet_lifetime_cadence_safe,
)
from .target_scope import possible_ally_targets, target_scope_is_static
from .triggers import TriggerMode
from .weapon import StaticCadenceModifiers

if TYPE_CHECKING:
    from .burst import BurstPolicy
    from .burst_runtime import BurstRuntime


_CADENCE_OR_SHAPE_STATS = frozenset({
    "reload_speed_pct",
    "reload_time_fixed",
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
    "force_reload",
    "pellet_count",
    "pellet_count_fixed",
})
_STATIC_FOLDABLE = frozenset(StaticCadenceModifiers.__dataclass_fields__)

_DYNAMIC_CHARGE_SCORE_STATS = frozenset({
    "charge_speed_pct",
    "charge_speed_caster_based_pct",
})
_DYNAMIC_RELOAD_SCORE_STATS = frozenset({"reload_speed_pct"})
_DYNAMIC_MAX_AMMO_SCORE_STATS = frozenset({"max_ammo_pct", "max_ammo_flat"})

_NORMAL_DIRECT_DAMAGE_STATS = frozenset({
    "atk_pct",
    "atk_flat",
    "atk_caster_based_pct",
    "def_ignore_pct",
    "crit_rate",
    "normal_atk_crit_rate",
    "crit_dmg",
    "normal_atk_crit_dmg",
    "core_dmg_pct",
    "accuracy_pct",
    "normal_atk_dmg_pct",
    "atk_dmg_pct",
    "charge_dmg_pct",
    "charge_dmg_mag_pct",
    "received_dmg_pct",
    "personal_received_dmg_pct",
    "element_bonus",
    "element_bonus_pct",
    "def_pct",
    "personal_enemy_def_down_pct",
    "pierce_enabled",
    "armor_break_enabled",
})

_UNRESOLVED_NORMAL_DAMAGE_STATS = frozenset({
    "atk_from_hp_pct",
    "atk_copy",
    "atk_buff_mag_pct",
    "charge_dmg_per_max_ammo_pct",
    "dmg_scale_mag_pct",
})

_PERIODIC_AUX_STATS = frozenset({"atk_pct", "atk_flat", "atk_caster_based_pct"})
_PERIODIC_GRID_INVALIDATORS = frozenset({
    "effect_interval",
    "skill_cooldown_pct",
    "skill_cooldown_reduce_pct",
    "force_skill_use",
})

_PATTERNLESS_UNREACHABLE_EVENT_KEYS = frozenset({
    "received_hit",
    "enemy_death",
    "event:part_destroy",
})


def _is_folded_static_self_modifier(effect) -> bool:
    return (
        (effect.stat or "") in _STATIC_FOLDABLE
        and effect.effect_type == "buff"
        and effect.target_spec.mode.value == "self"
        and effect.duration in (None, -1.0)
        and not effect.condition_rules
        and bool(effect.triggers)
        and all(rule.event_key == "battle_start" for rule in effect.triggers)
    )


def _charge_actor_indexes(squad: CompiledSquad) -> tuple[int, ...]:
    return tuple(
        actor
        for actor, member in enumerate(squad.members)
        if str(member.weapon.get("fire_mode") or "") == "charge"
    )


def _is_dynamic_charge_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") not in _DYNAMIC_CHARGE_SCORE_STATS:
        return False
    if not _charge_actor_indexes(squad):
        return True
    if effect.effect_type != "buff" or not _valid_dynamic_bullet_lifetime(effect):
        return False
    return TriggerDispatcher.is_executable_effect(effect)


def _possible_ally_targets(squad: CompiledSquad, effect) -> tuple[int, ...]:
    return possible_ally_targets(squad, effect)


def _actor_has_executable_event(
    squad: CompiledSquad,
    actor: int,
    event_keys: frozenset[str],
) -> bool:
    return any(
        TriggerDispatcher.is_executable_effect(effect)
        and any(rule.event_key in event_keys for rule in effect.triggers)
        for effect in squad.members[actor].effects
    )


def _actor_has_unhandled_count_event(
    squad: CompiledSquad,
    actor: int,
    event_keys: frozenset[str],
) -> bool:
    for effect in squad.members[actor].effects:
        if not TriggerDispatcher.is_executable_effect(effect):
            continue
        for rule in effect.triggers:
            if rule.event_key not in event_keys:
                continue
            threshold = int(rule.threshold or 0)
            if (
                rule.mode is not TriggerMode.MODULO
                or not rule.trigger_count_reducible
                or threshold <= 0
            ):
                return True
    return False


def _actor_has_executable_core_count(squad: CompiledSquad, actor: int) -> bool:
    return any(
        TriggerDispatcher.is_executable_effect(effect)
        and any(is_static_expected_core_count_rule(rule) for rule in effect.triggers)
        for effect in squad.members[actor].effects
    )


def _reload_speed_positive_upper_bound(squad: CompiledSquad, actor: int) -> float:
    """Conservative upper bound for beneficial reload speed on one actor.

    ``cover_during_delay`` only changes Moris behavior once reload speed reaches
    100%. Counting every possibly-targeting positive buff at maximum stack is an
    intentionally loose bound: if even this stays below 100, the special branch
    is provably unreachable for the squad.
    """

    total = 0.0
    for effect in squad.effects:
        if effect.effect_type != "buff" or (effect.stat or "") != "reload_speed_pct":
            continue
        if actor not in _possible_ally_targets(squad, effect):
            continue
        value = max(0.0, float(effect.value or 0.0))
        if value <= 0.0:
            continue
        max_stack = effect.max_stack
        if max_stack is not None and float(max_stack) < 0.0:
            return inf
        stacks = 1.0 if max_stack is None else max(1.0, float(max_stack))
        total += value * stacks
    return total


def _temporary_self_charge_weapon_change_score_supported(
    squad: CompiledSquad, effect
) -> bool:
    if not TriggerDispatcher._temporary_self_charge_weapon_change_shape_supported(effect):
        return False
    member = squad.members[effect.actor]
    params = effect.parameters
    charge = float(params.get("charge_seconds", params.get("charge_time", 1.0)))
    if not (
        str(member.weapon.get("fire_mode") or "") == "charge"
        and str(member.weapon.get("weapon_type") or member.weapon_type) == str(params.get("weapon_type"))
        and abs(float(member.weapon.get("charge_time") or 0.0) - charge) <= 1e-9
        and not member.weapon.get("control")
        and not member.weapon.get("is_clip")
    ):
        return False
    related = tuple(
        other
        for other in squad.effects
        if other.effect_type == "weapon_change"
        and effect.actor in _possible_ally_targets(squad, other)
    )
    return len(related) == 1 and related[0].effect_id == effect.effect_id


def _charge_actor_score_safe(squad: CompiledSquad, actor: int) -> bool:
    """Safety contract for per-shot dynamic SR/RL score ownership."""

    member = squad.members[actor]
    if str(member.weapon.get("fire_mode") or "") != "charge":
        return False
    if member.weapon.get("control") or member.weapon.get("is_clip"):
        return False
    if (
        member.weapon.get("cover_during_delay")
        and _reload_speed_positive_upper_bound(squad, actor) >= 100.0 - 1e-9
    ):
        return False

    weapon_changes = tuple(
        effect
        for effect in squad.effects
        if effect.effect_type == "weapon_change"
        and actor in _possible_ally_targets(squad, effect)
    )
    if weapon_changes and not (
        len(weapon_changes) == 1
        and _temporary_self_charge_weapon_change_score_supported(squad, weapon_changes[0])
    ):
        return False

    if _actor_has_executable_core_count(squad, actor):
        return False
    if _actor_has_executable_event(
        squad,
        actor,
        frozenset({"last_bullet_fire", "event:full_reload", "full_reload"}),
    ):
        return False
    for effect in squad.members[actor].effects:
        if not any(rule.event_key == "on_attack" for rule in effect.triggers):
            continue
        if not TriggerDispatcher.is_executable_effect(effect):
            continue
        if not TriggerDispatcher._on_attack_charge_speed_shape_supported(effect):
            return False
    if _actor_has_executable_event(squad, actor, frozenset({"pellet_hit"})):
        return False
    return not _actor_has_unhandled_count_event(
        squad, actor, frozenset({"hit_count"})
    )


def _rapid_actor_score_safe(
    squad: CompiledSquad,
    actor: int,
    *,
    require_cover_control: bool = False,
) -> bool:
    """Safety contract for compressed auto/MG physical-shot ownership."""

    member = squad.members[actor]
    mode = str(member.weapon.get("fire_mode") or "")
    if mode not in {"auto", "auto_warmup"}:
        return False
    if member.weapon.get("is_clip") or member.weapon.get("cover_during_delay"):
        return False

    control = member.weapon.get("control") or {}
    if require_cover_control:
        if not is_supported_rapid_cover_control(member):
            return False
    elif control and not is_supported_rapid_cover_control(member):
        return False

    for effect in squad.effects:
        if effect.effect_type != "weapon_change":
            continue
        if actor in _possible_ally_targets(squad, effect):
            return False

    if _actor_has_executable_core_count(squad, actor):
        return False
    if _actor_has_executable_event(
        squad,
        actor,
        frozenset({
            "last_bullet_fire",
            "on_attack",
            "event:full_reload",
            "full_reload",
            "event:cover",
        }),
    ):
        return False
    if _actor_has_unhandled_count_event(
        squad, actor, frozenset({"hit_count", "pellet_hit"})
    ):
        return False

    if any(
        TriggerDispatcher.is_executable_effect(effect)
        and any(rule.event_key == "squad_body_hit" for rule in effect.triggers)
        for effect in squad.effects
    ):
        return False
    return True


def _actor_has_live_max_ammo_mutation(squad: CompiledSquad, actor: int) -> bool:
    for effect in squad.effects:
        if (effect.stat or "") not in {"max_ammo_pct", "max_ammo_flat", "max_ammo_infinite"}:
            continue
        if _is_folded_static_self_modifier(effect):
            continue
        if actor in _possible_ally_targets(squad, effect):
            return True
    return False


def _timed_self_state_end_source_score_safe(squad: CompiledSquad, effect) -> bool:
    """Prove every state-end trigger comes from Fast's certified source bridge.

    Dispatcher may parse a narrow ``event:state_end:*`` consumer, but score
    certification must additionally prove that the named source state is one
    Fast actually emits: an executable finite-duration self buff owned by the
    same actor, with an ordinary time lifetime.  Any ambiguous/unsupported
    provider keeps the consumer fail-closed.
    """

    keys = tuple(
        rule.event_key
        for rule in effect.triggers
        if (rule.event_key or "").startswith("event:state_end:")
    )
    if not keys:
        return True
    if len(keys) != len(effect.triggers):
        return False

    for key in keys:
        name = key[len("event:state_end:"):]
        if not name:
            return False
        providers = tuple(
            provider
            for provider in squad.members[effect.actor].effects
            if provider.effect_id != effect.effect_id and provider.name == name
        )
        if not providers:
            return False
        for provider in providers:
            if (
                provider.effect_type != "buff"
                or provider.target_spec.mode.value != "self"
                or provider.duration is None
                or float(provider.duration) < 0.0
                or provider.parameters.get("duration_bullets") is not None
                or not TriggerDispatcher.is_executable_effect(provider)
            ):
                return False
    return True


def _ammo_charge_named_event_safe(squad: CompiledSquad, effect) -> bool:
    if not effect.name:
        return True
    event_key = f"event:{effect.name}"
    return not any(
        other.effect_id != effect.effect_id
        and any(rule.event_key == event_key for rule in other.triggers)
        for other in squad.effects
    )


def _ammo_charge_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:
    if _actor_has_live_max_ammo_mutation(squad, actor):
        return False
    mode = str(squad.members[actor].weapon.get("fire_mode") or "")
    if mode in {"auto", "auto_warmup"}:
        return _rapid_actor_score_safe(squad, actor)
    if mode == "charge":
        return _charge_actor_score_safe(squad, actor)
    return False


def _is_dynamic_ammo_charge_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") not in {"ammo_charge_pct", "ammo_charge_flat"}:
        return False
    if effect.effect_type != "instant" or effect.value is None or float(effect.value) < 0.0:
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    # Weapon state is initialized after battle_start in BurstRuntime. Keep that
    # lifecycle shape fail-closed in the first ammo-refill slice.
    if any(rule.event_key == "battle_start" for rule in effect.triggers):
        return False
    if not _ammo_charge_named_event_safe(squad, effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(
        _ammo_charge_recipient_score_safe(squad, actor) for actor in targets
    )


def _dynamic_ammo_charge_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if _is_dynamic_ammo_charge_score_supported(squad, effect):
            actors.update(_possible_ally_targets(squad, effect))
    return tuple(sorted(actors))


def _is_dynamic_mg_warmup_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") != "mg_warmup_speed_pct":
        return False
    if effect.effect_type != "buff":
        return False
    if effect.parameters.get("duration_bullets") is not None:
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    if not _timed_self_state_end_source_score_safe(squad, effect):
        return False
    mg_targets = tuple(
        actor
        for actor in _possible_ally_targets(squad, effect)
        if str(squad.members[actor].weapon.get("fire_mode") or "") == "auto_warmup"
    )
    return all(_rapid_actor_score_safe(squad, actor) for actor in mg_targets)


def _dynamic_mg_warmup_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if not _is_dynamic_mg_warmup_score_supported(squad, effect):
            continue
        actors.update(
            actor
            for actor in _possible_ally_targets(squad, effect)
            if str(squad.members[actor].weapon.get("fire_mode") or "") == "auto_warmup"
        )
    return tuple(sorted(actors))


def _reload_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:
    member = squad.members[actor]
    mode = str(member.weapon.get("fire_mode") or "")
    if mode in {"auto", "auto_warmup"}:
        return _rapid_actor_score_safe(squad, actor)
    if mode == "charge":
        return _charge_actor_score_safe(squad, actor)
    return False


def _max_ammo_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:
    mode = str(squad.members[actor].weapon.get("fire_mode") or "")
    if mode in {"auto", "auto_warmup"}:
        return _rapid_actor_score_safe(squad, actor)
    if mode == "charge":
        return _charge_actor_score_safe(squad, actor)
    return False


def _is_dynamic_max_ammo_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") not in _DYNAMIC_MAX_AMMO_SCORE_STATS:
        return False
    # Permanent unconditional self modifiers stay in the existing static cadence
    # compiler. Promoting them would turn ordinary teams into dynamic weapon sims.
    if _is_folded_static_self_modifier(effect):
        return False
    if (
        effect.effect_type != "buff"
        or effect.value is None
        or effect.parameters
        or effect.condition_rules
        or not target_scope_is_static(effect.target_spec)
        or not TriggerDispatcher.is_executable_effect(effect)
    ):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_max_ammo_recipient_score_safe(squad, a) for a in targets)


def _dynamic_max_ammo_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if _is_dynamic_max_ammo_score_supported(squad, effect):
            actors.update(_possible_ally_targets(squad, effect))
    return tuple(sorted(actors))


def _valid_dynamic_bullet_lifetime(effect) -> bool:
    bullets = effect.parameters.get("duration_bullets")
    if bullets is None:
        return True
    try:
        value = float(bullets)
    except (TypeError, ValueError):
        return False
    return value >= 1.0 and value.is_integer()


def _is_dynamic_reload_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") not in _DYNAMIC_RELOAD_SCORE_STATS:
        return False
    if effect.effect_type != "buff" or not _valid_dynamic_bullet_lifetime(effect):
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    if not _timed_self_state_end_source_score_safe(squad, effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_reload_recipient_score_safe(squad, actor) for actor in targets)


def _is_dynamic_force_reload_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") != "force_reload" or effect.effect_type != "instant":
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    if not _timed_self_state_end_source_score_safe(squad, effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_rapid_actor_score_safe(squad, actor) for actor in targets)


def _dynamic_force_reload_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if _is_dynamic_force_reload_score_supported(squad, effect):
            actors.update(_possible_ally_targets(squad, effect))
    return tuple(sorted(actors))


def _dynamic_reload_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if (
            (effect.stat or "") == "reload_speed_pct"
            and not _is_folded_static_self_modifier(effect)
            and _is_dynamic_reload_score_supported(squad, effect)
        ):
            actors.update(_possible_ally_targets(squad, effect))
    return tuple(sorted(actors))


def _dynamic_charge_bullet_lifetime_score_actors(
    squad: CompiledSquad,
) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if effect.parameters.get("duration_bullets") is None:
            continue
        if not is_direct_damage_buff_runtime_supported(effect):
            continue
        if not TriggerDispatcher.is_executable_effect(effect):
            continue
        for actor in _possible_ally_targets(squad, effect):
            if _charge_actor_score_safe(squad, actor):
                actors.add(actor)
    return tuple(sorted(actors))


def _dynamic_charge_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors: set[int] = set()
    charge = set(_charge_actor_indexes(squad))
    if not charge:
        return ()
    for effect in squad.effects:
        if (
            (effect.stat or "") in _DYNAMIC_CHARGE_SCORE_STATS
            and not _is_folded_static_self_modifier(effect)
            and _is_dynamic_charge_score_supported(squad, effect)
        ):
            actors.update(charge)
    actors.update(charge & set(_dynamic_reload_score_actors(squad)))
    actors.update(charge & set(_dynamic_ammo_charge_score_actors(squad)))
    actors.update(charge & set(_dynamic_max_ammo_score_actors(squad)))
    actors.update(_dynamic_charge_bullet_lifetime_score_actors(squad))
    actors.update(
        effect.actor
        for effect in squad.effects
        if effect.effect_type == "weapon_change"
        and _temporary_self_charge_weapon_change_score_supported(squad, effect)
    )
    return tuple(sorted(actors))


def _dynamic_rapid_reload_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors = {
        actor
        for actor in _dynamic_reload_score_actors(squad)
        if str(squad.members[actor].weapon.get("fire_mode") or "")
        in {"auto", "auto_warmup"}
    }
    actors.update(
        actor
        for actor, member in enumerate(squad.members)
        if member.weapon.get("control")
        and _rapid_actor_score_safe(squad, actor, require_cover_control=True)
    )
    actors.update(
        actor
        for actor in _dynamic_ammo_charge_score_actors(squad)
        if str(squad.members[actor].weapon.get("fire_mode") or "")
        in {"auto", "auto_warmup"}
    )
    actors.update(_dynamic_mg_warmup_score_actors(squad))
    actors.update(_dynamic_force_reload_score_actors(squad))
    actors.update(a for a in _dynamic_max_ammo_score_actors(squad) if str(squad.members[a].weapon.get("fire_mode") or "") in {"auto", "auto_warmup"})
    return tuple(sorted(actors))


def _is_score_safe_fixed_periodic(effect) -> bool:
    if TriggerDispatcher._periodic_permanent_self_direct_stack_shape_supported(effect):
        return True
    return (
        (effect.stat or "") in _PERIODIC_AUX_STATS
        and effect.effect_type == "buff"
        and effect.target_spec.runtime_supported
        and all(rule.is_runtime_supported for rule in effect.condition_rules)
        and bool(effect.triggers)
        and all(
            rule.mode is TriggerMode.PERIODIC
            and rule.interval is not None
            and float(rule.interval) > 0.0
            for rule in effect.triggers
        )
    )


def _is_patternless_unreachable(effect) -> bool:
    return (
        bool(effect.triggers)
        and all(
            rule.event_key in _PATTERNLESS_UNREACHABLE_EVENT_KEYS
            for rule in effect.triggers
        )
    )


def _direct_normal_effect_needs_score_support(effect) -> bool:
    stat = effect.stat or ""
    if stat != "def_pct":
        return True
    return effect.target_spec.mode.value == "enemy"


def _direct_skill_state_needs_score_support(effect) -> bool:
    stat = effect.stat or ""
    mode = effect.target_spec.mode.value
    if stat in {"pierce_enabled", "armor_break_enabled"}:
        return False
    if stat in {"def_pct", "received_dmg_pct"}:
        return mode == "enemy"
    return True


_SHIELD_SOURCE_STATS = frozenset({"shield_from_max_hp_pct", "shared_shield_from_max_hp_pct"})


def _uses_shield_runtime_semantics(effect) -> bool:
    return (
        any(rule.mode is ConditionMode.DURING_SHIELD for rule in effect.condition_rules)
        or any((rule.event_key or "") == "event:shield_applied" for rule in effect.triggers)
    )


def _shield_runtime_dependency_score_safe(squad: CompiledSquad, effect) -> bool:
    owner = effect.actor
    sources = tuple(
        source
        for source in squad.effects
        if (source.stat or "") in _SHIELD_SOURCE_STATS
        and owner in _possible_ally_targets(squad, source)
    )
    if not sources:
        return False
    if not all(TriggerDispatcher._timed_shield_shape_supported(source) for source in sources):
        return False
    source_names = {source.name for source in sources if source.name}
    if any(
        other.parameters.get("target_effect") in source_names
        for other in squad.effects
        if other is not effect
    ):
        return False
    return True


def _named_buff_event_dependency_score_safe(squad: CompiledSquad, effect) -> bool:
    keys = TriggerDispatcher._named_event_keys(effect)
    if not keys:
        return True
    for key in keys:
        if key == "event:heal_received":
            if not TriggerDispatcher.heal_received_dependency_score_safe(squad, effect):
                return False
            continue
        name = key[len("event:"):]
        providers = tuple(
            provider
            for provider in squad.effects
            if provider.effect_id != effect.effect_id
            and provider.effect_type == "buff"
            and provider.name == name
        )
        if not providers:
            return False
        for provider in providers:
            if TriggerDispatcher._named_event_keys(provider):
                return False
            if provider.parameters.get("event_scope") not in (None, "", "squad", "recipients"):
                return False
            if not provider.target_spec.runtime_supported:
                return False
            if not (
                TriggerDispatcher.is_executable_effect(provider)
                or TriggerDispatcher._named_event_marker_nop_shape_supported(provider)
            ):
                return False
    return True


def _direct_damage_buff_score_supported(squad: CompiledSquad, effect) -> bool:
    if not is_direct_damage_buff_runtime_supported(effect):
        return False
    if _uses_shield_runtime_semantics(effect) and not _shield_runtime_dependency_score_safe(squad, effect):
        return False
    if not _named_buff_event_dependency_score_safe(squad, effect):
        return False
    if effect.parameters.get("duration_bullets") is None:
        return True
    if not target_scope_is_static(effect.target_spec):
        return True
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(
        static_bullet_lifetime_cadence_safe(squad, actor)
        or _charge_actor_score_safe(squad, actor)
        for actor in targets
    )


def static_normal_score_blockers(squad: CompiledSquad) -> tuple[str, ...]:
    blockers: list[str] = []
    for actor, member in enumerate(squad.members):
        if member.weapon.get("control") and not _rapid_actor_score_safe(
            squad, actor, require_cover_control=True
        ):
            blockers.append(f"control:{member.name}")

    has_score_periodic = any(_is_score_safe_fixed_periodic(effect) for effect in squad.effects)

    for effect in squad.effects:
        stat = effect.stat or ""
        owner = squad.members[effect.actor].name
        label = f"{owner}:{effect.name or stat}:{stat}"

        if _is_patternless_unreachable(effect):
            continue

        if effect.effect_type == "weapon_change":
            if not _temporary_self_charge_weapon_change_score_supported(squad, effect):
                blockers.append(f"weapon_change:{owner}:{effect.name or 'unnamed'}")
            continue

        if stat in _CADENCE_OR_SHAPE_STATS:
            if _is_folded_static_self_modifier(effect):
                continue
            if (
                stat in _DYNAMIC_CHARGE_SCORE_STATS
                and _is_dynamic_charge_score_supported(squad, effect)
            ):
                continue
            if stat == "reload_speed_pct" and _is_dynamic_reload_score_supported(squad, effect):
                continue
            if stat in _DYNAMIC_MAX_AMMO_SCORE_STATS and _is_dynamic_max_ammo_score_supported(squad, effect):
                continue
            if stat in {"ammo_charge_pct", "ammo_charge_flat"} and _is_dynamic_ammo_charge_score_supported(squad, effect):
                continue
            if stat == "mg_warmup_speed_pct" and _is_dynamic_mg_warmup_score_supported(squad, effect):
                continue
            if stat == "force_reload" and _is_dynamic_force_reload_score_supported(squad, effect):
                continue
            blockers.append(f"cadence:{label}")
            continue

        if stat == "element_code_override":
            if not is_static_element_override_score_supported(effect):
                blockers.append(f"normal_state:{label}")
            continue

        if stat == "charge_speed_overflow_conversion_pct":
            if not TriggerDispatcher._charge_overflow_conversion_shape_supported(effect):
                blockers.append(f"normal_state:{label}")
            continue

        if stat in _UNRESOLVED_NORMAL_DAMAGE_STATS:
            blockers.append(f"normal_state:{label}")
            continue

        if stat in _NORMAL_DIRECT_DAMAGE_STATS and _direct_normal_effect_needs_score_support(effect):
            if _direct_damage_buff_score_supported(squad, effect):
                continue
            if _is_score_safe_fixed_periodic(effect):
                continue
            blockers.append(f"normal_delivery:{label}")
            continue

        if has_score_periodic and stat in _PERIODIC_GRID_INVALIDATORS:
            blockers.append(f"periodic_grid:{label}")

    return tuple(dict.fromkeys(blockers))


def static_score_blockers(squad: CompiledSquad) -> tuple[str, ...]:
    blockers = list(static_normal_score_blockers(squad))

    # Mirror the damage sink's compile-time support decision before running the
    # combat timeline. Unsupported comparison-critical skill damage must fail
    # closed here instead of burning a full Fast evaluation and only appearing
    # later in FastScore.unsupported. Runtime-dependent gauge checks remain safe:
    # SimpleDamageScoreSink treats an unattached runtime as compile-time proof.
    from .damage_runtime import SimpleDamageScoreSink
    from .model import EnemyStaticProfile

    damage_sink = SimpleDamageScoreSink(
        squad, EnemyStaticProfile(defense=0.0, duration=1.0)
    )
    for effect in squad.effects:
        if (
            effect.effect_type == "damage"
            and not _is_patternless_unreachable(effect)
            and not damage_sink.supports(effect)
        ):
            owner = squad.members[effect.actor].name
            blockers.append(
                f"skill_damage:{owner}:"
                f"{effect.name or effect.stat or '?'}:{effect.stat or '?'}"
            )

    for effect in squad.effects:
        if effect.effect_type != "buff" or _is_patternless_unreachable(effect):
            continue
        stat = effect.stat or ""
        if stat not in DIRECT_DAMAGE_STATE_STATS:
            continue
        if not _direct_skill_state_needs_score_support(effect):
            continue
        if _direct_damage_buff_score_supported(squad, effect):
            continue
        if _is_score_safe_fixed_periodic(effect):
            continue
        owner = squad.members[effect.actor].name
        blockers.append(
            f"skill_state_delivery:{owner}:{effect.name or stat}:{stat}"
        )
    return tuple(dict.fromkeys(blockers))


class StaticNormalAttackObserver:
    """Score static shot blocks plus selected live dynamic weapon shots."""

    __slots__ = (
        "runtime",
        "duration",
        "resolver",
        "specs",
        "cursors",
        "dynamic_charge_actors",
        "dynamic_reload_actors",
        "control_cover_anchor",
        "char_total",
    )

    def __init__(self, runtime: "BurstRuntime", *, duration: float) -> None:
        blockers = static_normal_score_blockers(runtime.squad)
        if blockers:
            detail = ", ".join(blockers[:8])
            if len(blockers) > 8:
                detail += f", +{len(blockers) - 8} more"
            raise NotImplementedError(
                "Fast static normal score blocked by unsupported comparison-critical effects: "
                + detail
            )

        runtime.dispatcher.enable_strict_score_delivery()
        self.runtime = runtime
        self.duration = float(duration)
        self.resolver = DamageTermResolver(
            runtime.squad,
            runtime.dispatcher.effects,
            runtime.state,
            runtime.enemy,
        )
        self.specs = tuple(compile_normal_attack_spec(member) for member in runtime.squad.members)
        self.dynamic_charge_actors = _dynamic_charge_score_actors(runtime.squad)
        self.dynamic_reload_actors = _dynamic_rapid_reload_score_actors(runtime.squad)
        dynamic = frozenset(self.dynamic_charge_actors) | frozenset(self.dynamic_reload_actors)
        blocks = compile_static_shot_blocks(runtime.squad, duration=self.duration)
        self.cursors = tuple(
            ShotBlockCursor(()) if actor in dynamic else ShotBlockCursor(rows)
            for actor, rows in enumerate(blocks)
        )
        self.control_cover_anchor = -1.0
        self.char_total = [0.0] * len(runtime.squad.members)
        if self.dynamic_charge_actors:
            runtime.weapons.attach_score_shot_sink(
                self.dynamic_charge_actors,
                self._score_dynamic_charge_shot,
            )
        if self.dynamic_reload_actors:
            runtime.weapons.attach_score_block_sink(
                self.dynamic_reload_actors,
                self._score_dynamic_reload_block,
            )
        runtime.dispatcher.attach_ammo_charge_sink(runtime.weapons.apply_ammo_charge)
        runtime.dispatcher.attach_force_reload_sink(runtime.weapons.apply_force_reload)

    def _score_shots(self, actor: int, count: int, *, eval_time: float) -> None:
        if count <= 0:
            return
        member = self.runtime.squad.members[actor]
        weapon = self.runtime.weapons.effective_weapon(actor, eval_time)
        spec = self.specs[actor]
        if weapon is not member.weapon:
            pellets = max(1, int(weapon.get("pellets", 1)))
            muzzles = max(1, int(weapon.get("muzzles", 1)))
            total_coeff = float(weapon.get("damage_coeff", 0.0))
            spec = NormalAttackSpec(
                coeff_per_hit=total_coeff / pellets if pellets > 1 else total_coeff,
                hits_per_shot=pellets * muzzles,
                core_dmg_mult=float(weapon.get("core_dmg_mult", 200.0)),
                full_charge_mult=float(weapon.get("full_charge_mult", 100.0)),
                normal_hit_coeff=float(weapon.get("normal_hit_coeff", 1.0)),
                is_full_charge=str(weapon.get("fire_mode") or "") == "charge",
            )
        terms = self.resolver.resolve(actor, now=eval_time)
        core_prob = self.runtime.enemy.core_rate_for_weapon(
            weapon,
            accuracy_pct=terms.accuracy_pct,
        )
        self.char_total[actor] += expected_normal_block_damage(
            spec,
            shot_count=count,
            base_atk=member.base_atk,
            enemy_def=self.runtime.enemy.defense,
            terms=terms,
            core_prob=core_prob,
            is_full_burst=self.runtime.machine.phase == "full_burst",
            is_optimal_range=False,
        )

    def _score_dynamic_charge_shot(self, actor: int, time: float) -> None:
        self._score_shots(actor, 1, eval_time=float(time))

    def _score_dynamic_reload_block(self, actor: int, count: int, time: float) -> None:
        self._score_shots(actor, count, eval_time=float(time))

    def consume_until(self, time: float, *, inclusive: bool) -> None:
        machine = self.runtime.machine
        if (
            machine.phase == "full_burst"
            and machine.full_burst_end_at > self.control_cover_anchor + 1e-9
        ):
            self.runtime.weapons.begin_full_burst(
                float(time),
                machine.casted,
                machine.full_burst_end_at,
            )
            self.control_cover_anchor = machine.full_burst_end_at

        self.runtime.weapons.advance_to(time, inclusive=inclusive)

        eval_time = float(time) if inclusive else nextafter(float(time), -inf)
        for actor, cursor in enumerate(self.cursors):
            count = cursor.consume_until(time, inclusive=inclusive)
            if count <= 0:
                continue
            self._score_shots(actor, count, eval_time=eval_time)

    def finish(self, *, events_processed: int) -> FastScore:
        self.consume_until(self.duration, inclusive=False)
        totals = tuple(self.char_total)
        return FastScore(
            squad_total=sum(totals),
            char_total=totals,
            duration=self.duration,
            events_processed=events_processed,
            unsupported=("skill_damage:not_implemented",),
        )


def score_static_normal_squad(
    squad: CompiledSquad,
    policy: "BurstPolicy",
    enemy: EnemyStaticProfile | None = None,
    *,
    duration: float | None = None,
) -> FastScore:
    from .burst_runtime import BurstRuntime

    horizon = policy.duration if duration is None else min(float(duration), policy.duration)
    runtime = BurstRuntime(squad, policy, enemy)
    observer = StaticNormalAttackObserver(runtime, duration=horizon)
    result = runtime.run(duration=horizon, score_observer=observer)
    return observer.finish(events_processed=result.events_processed)


def score_static_squad(
    squad: CompiledSquad,
    policy: "BurstPolicy",
    enemy: EnemyStaticProfile | None = None,
    *,
    duration: float | None = None,
) -> FastScore:
    from .burst_runtime import BurstRuntime
    from .damage_runtime import SimpleDamageScoreSink

    blockers = static_score_blockers(squad)
    if blockers:
        detail = ", ".join(blockers[:8])
        if len(blockers) > 8:
            detail += f", +{len(blockers) - 8} more"
        raise NotImplementedError(
            "Fast static score blocked by unsupported comparison-critical state: "
            + detail
        )

    horizon = policy.duration if duration is None else min(float(duration), policy.duration)
    enemy_profile = enemy or EnemyStaticProfile(duration=policy.duration)
    sink = SimpleDamageScoreSink(squad, enemy_profile)
    runtime = BurstRuntime(
        squad,
        policy,
        enemy_profile,
        damage_sink=sink,
    )
    observer = StaticNormalAttackObserver(runtime, duration=horizon)
    result = runtime.run(duration=horizon, score_observer=observer)
    normal = observer.finish(events_processed=result.events_processed)

    totals = tuple(
        normal.char_total[actor] + sink.char_total[actor]
        for actor in range(len(squad.members))
    )
    unsupported = tuple(
        f"skill_damage:{squad.members[effect.actor].name}:"
        f"{effect.name or effect.stat or '?'}:{effect.stat or '?'}"
        for effect in squad.effects
        if effect.effect_type == "damage"
        and not sink.supports(effect)
        and not _is_patternless_unreachable(effect)
    )
    return FastScore(
        squad_total=sum(totals),
        char_total=totals,
        duration=horizon,
        events_processed=result.events_processed,
        unsupported=unsupported,
    )
