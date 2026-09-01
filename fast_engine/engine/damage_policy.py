from __future__ import annotations

from .conditions import ConditionMode
from .targets import TargetMode
from .triggers import TriggerMode

# Stats that DamageTermResolver can lower directly without HP/gauge/resource-derived
# semantics. These are not automatically executable: timing/condition/target must
# also pass the fail-closed policy below.
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
})

_SAFE_CONDITIONS = frozenset({
    ConditionMode.DURING_FULL_BURST,
    ConditionMode.NOT_DURING_FULL_BURST,
    ConditionMode.BURST_CASTED,
    ConditionMode.BURST_NOT_CASTED,
    ConditionMode.SELF_STATE,
    ConditionMode.NOT_SELF_STATE,
    ConditionMode.TARGET_STATE,
    ConditionMode.NOT_TARGET_STATE,
    ConditionMode.SELF_STACK_AT_LEAST,
    ConditionMode.TARGET_STACK_AT_LEAST,
    ConditionMode.TARGET_CODE,
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
    # Fixed-grid periodic is intentionally left to the already-certified narrow
    # auxiliary lane (e.g. Milk) until skill_cooldown/effect_interval replanning
    # exists for all damage stats.
    if rule.mode is TriggerMode.PERIODIC:
        return False
    if rule.event_key == "full_charge_hit":
        # MultiSignalChargeCadenceRuntime now has an actor-selective producer for
        # literal every-full-charge events, while retaining compressed MODULO
        # boundaries for full_charge_count:N.
        return (
            rule.mode is TriggerMode.EVENT
            or (rule.mode is TriggerMode.MODULO and rule.trigger_count_reducible)
        )
    if rule.event_key == "hit_count":
        # Generic every-hit production is still intentionally absent. Only
        # reducible hit_count:N crossings are certified.
        return rule.mode is TriggerMode.MODULO and rule.trigger_count_reducible
    if rule.event_key in _SAFE_EVENT_KEYS:
        return True
    if rule.event_key and rule.event_key.startswith("burst_enter:"):
        return True
    if rule.event_key and rule.event_key.startswith("squad_burst_cast:"):
        return True
    return False


def is_direct_damage_buff_runtime_supported(effect) -> bool:
    """Return True only when Fast can both represent and *deliver* this buff.

    The function is intentionally conservative. Supporting a numeric stat is not
    enough: every timing must have an actual Fast producer, every condition must
    be evaluable from current state, and target resolution must be deterministic.
    Unsupported effects stay absent rather than silently activating with guessed
    semantics.
    """

    if effect.effect_type != "buff" or (effect.stat or "") not in DIRECT_DAMAGE_STATE_STATS:
        return False
    if not _target_supported(effect.target_spec):
        return False
    if any(rule.mode not in _SAFE_CONDITIONS for rule in effect.condition_rules):
        return False
    if not effect.triggers or not all(_timing_supported(rule) for rule in effect.triggers):
        return False
    return True
