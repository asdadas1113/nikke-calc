from __future__ import annotations

from .conditions import ConditionMode
from .core_events import is_static_expected_core_count_rule
from .targets import TargetMode
from .triggers import TriggerMode

# Damage-facing states that the Fast score path can lower directly without
# HP/gauge/resource-derived semantics. This includes both numeric DealForm terms
# and boolean normal-attack mode toggles. They are not automatically executable:
# timing/condition/target must also pass the fail-closed policy below.
DIRECT_DAMAGE_STATE_STATS = frozenset({
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
    "burst_dmg_pct",
    "burst_dmg_aoe_pct",
    "pierce_dmg_pct",
    "armor_break_dmg_pct",
    "dot_dmg_pct",
    "projectile_explosion_dmg",
    "projectile_explosion_dmg_pct",
    "projectile_attachment_dmg",
    "projectile_attachment_dmg_pct",
    "sequential_dmg_pct",
    "part_dmg",
    "part_dmg_pct",
    "charge_dmg_pct",
    "charge_dmg_mag_pct",
    "received_dmg_pct",
    "personal_received_dmg_pct",
    "split_dmg_pct",
    "element_bonus",
    "element_bonus_pct",
    "def_pct",
    "personal_enemy_def_down_pct",
    "pierce_enabled",
    "armor_break_enabled",
})

_SAFE_CONDITIONS = frozenset({
    ConditionMode.DURING_FULL_BURST,
    ConditionMode.NOT_DURING_FULL_BURST,
    ConditionMode.DURING_SHIELD,
    ConditionMode.BURST_CASTED,
    ConditionMode.BURST_NOT_CASTED,
    ConditionMode.SELF_STATE,
    ConditionMode.NOT_SELF_STATE,
    ConditionMode.TARGET_STATE,
    ConditionMode.NOT_TARGET_STATE,
    ConditionMode.SELF_STACK_AT_LEAST,
    ConditionMode.TARGET_STACK_AT_LEAST,
    ConditionMode.TARGET_CODE,
    ConditionMode.BACK_ROW,
    ConditionMode.SQUAD_ALLY_EXISTS,
    ConditionMode.HAS_BURST1_ALLY,
    ConditionMode.NO_BURST1_ALLY,
    ConditionMode.HAS_DEFENDER_ALLY,
    ConditionMode.NO_DEFENDER_ALLY,
})

_SAFE_TARGETS = frozenset({
    TargetMode.SELF,
    TargetMode.ALL_ALLIES,
    TargetMode.ALL_ALLIES_EXCL_SELF,
    TargetMode.NAMED_ACTOR,
    TargetMode.ENEMY,
    TargetMode.ADJACENT,
    TargetMode.WEAPON,
    TargetMode.WEAPON_EXCL_SELF,
    TargetMode.CHARACTER_CLASS,
    TargetMode.ELEMENT,
    TargetMode.ELEMENT_WEAPON,
    TargetMode.SAME_SQUAD,
    TargetMode.WITH_BUFF,
    TargetMode.WITHOUT_BUFF,
    TargetMode.BURST3,
    TargetMode.BURST_CASTED,
    TargetMode.BURST_NOT_CASTED,
    TargetMode.BURST_CASTED_B3,
    TargetMode.BURST_CASTED_WEAPON,
    TargetMode.TOP_ATK,
    TargetMode.TOP_ATK_EXCL_SELF,
    TargetMode.LOWEST_ATK_BURST3,
    TargetMode.TOP_DEF,
})

_SAFE_EVENT_KEYS = frozenset({
    "battle_start",
    "event:enemy_spawn",
    "event:target_spawn",
    "burst_cast",
    "full_burst_start",
    "full_burst_end",
    "event:ally_burst_cast",
    "event:shield_applied",
    "last_bullet",
})

# Bullet-lifetime support is deliberately limited to controller events that happen
# before the recipient weapon shot. Weapon-bound activation needs separate
# same-shot consumption semantics and remains fail-closed.
_SAFE_BULLET_LIFETIME_EVENT_KEYS = frozenset({
    "battle_start",
    "burst_cast",
    "full_burst_start",
    "full_burst_end",
    "event:ally_burst_cast",
})


def _target_supported(spec) -> bool:
    if spec.mode is TargetMode.COMPOSITE:
        return all(_target_supported(child) for child in spec.children)
    return spec.mode in _SAFE_TARGETS


def _timing_supported(rule) -> bool:
    if rule.mode is TriggerMode.PERIODIC:
        return False
    if rule.event_key == "full_charge_hit":
        return (
            rule.mode is TriggerMode.EVENT
            or (rule.mode is TriggerMode.MODULO and rule.trigger_count_reducible)
        )
    if rule.event_key == "hit_count":
        return rule.mode is TriggerMode.MODULO and rule.trigger_count_reducible
    if rule.event_key == "core_hit":
        return is_static_expected_core_count_rule(rule)
    if rule.event_key in _SAFE_EVENT_KEYS:
        return True
    if (
        rule.mode is TriggerMode.EVENT
        and rule.event_key
        and rule.event_key.startswith("event:")
        and not rule.event_key.startswith("event:state_end:")
    ):
        # Runtime can represent a named-buff activation signal. Score
        # certification separately proves that a concrete executable provider
        # exists, so external events such as heal_received remain fail-closed.
        return True
    if rule.event_key and rule.event_key.startswith("burst_enter:"):
        return True
    if rule.event_key and rule.event_key.startswith("squad_burst_cast:"):
        return True
    return False


def _one_shot_lifetime_supported(effect) -> bool:
    """Return whether a duration_bullets effect can use static N-shot expiry.

    The historical helper name is kept for callers/tests. The certified lane now
    accepts any positive integer N while retaining the same target, stack and
    pre-shot trigger restrictions used by the original one-shot implementation.
    """

    raw = effect.parameters.get("duration_bullets")
    if raw is None:
        return True
    try:
        bullets = float(raw)
    except (TypeError, ValueError):
        return False
    if bullets < 1.0 or not bullets.is_integer():
        return False
    if effect.duration not in (None, -1.0):
        return False
    max_stack = effect.max_stack if effect.max_stack is not None else 1.0
    if float(max_stack) != 1.0:
        return False
    if effect.target_spec.mode in {TargetMode.ENEMY, TargetMode.COMPOSITE}:
        return False
    if not effect.triggers:
        return False
    for rule in effect.triggers:
        key = rule.event_key or ""
        if key in _SAFE_BULLET_LIFETIME_EVENT_KEYS:
            continue
        if key.startswith("burst_enter:") or key.startswith("squad_burst_cast:"):
            continue
        return False
    return True


def is_static_element_override_score_supported(effect) -> bool:
    """Certify immutable battle-start element-advantage overrides for scoring.

    Moris keeps ``element_code_override`` separate from the roster element code:
    while the buff is active, matching ``target_code`` simply ORs into the usual
    element-advantage predicate. Fast folds only the shape that cannot change
    after battle start; mutable/conditional variants remain fail-closed.
    """

    target_code = effect.parameters.get("target_code")
    return (
        effect.effect_type == "buff"
        and (effect.stat or "") == "element_code_override"
        and effect.target_spec.mode is TargetMode.SELF
        and effect.duration in (None, -1.0)
        and "irremovable" in str(effect.polarity or "")
        and not effect.condition_rules
        and bool(effect.triggers)
        and all(
            rule.mode is TriggerMode.EVENT and rule.event_key == "battle_start"
            for rule in effect.triggers
        )
        and isinstance(target_code, str)
        and bool(target_code)
    )


def is_direct_damage_buff_runtime_supported(effect) -> bool:
    """Return True only when Fast can both represent and *deliver* this buff."""

    if effect.effect_type != "buff" or (effect.stat or "") not in DIRECT_DAMAGE_STATE_STATS:
        return False
    if not _one_shot_lifetime_supported(effect):
        return False
    if not _target_supported(effect.target_spec):
        return False
    if any(rule.mode not in _SAFE_CONDITIONS for rule in effect.condition_rules):
        return False
    if not effect.triggers or not all(_timing_supported(rule) for rule in effect.triggers):
        return False
    return True
