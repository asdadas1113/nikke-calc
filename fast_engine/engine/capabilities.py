from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

_ROOT = Path(__file__).resolve().parents[2]

HIT_FORMULA_STATS = frozenset({
    "atk_pct", "atk_flat", "def_ignore_pct", "crit_rate", "normal_atk_crit_rate",
    "crit_dmg", "normal_atk_crit_dmg", "core_dmg_pct", "atk_dmg_pct",
    "burst_dmg_pct", "burst_dmg_aoe_pct", "pierce_dmg_pct", "armor_break_dmg_pct",
    "dot_dmg_pct", "projectile_explosion_dmg_pct", "projectile_explosion_dmg",
    "projectile_attachment_dmg_pct", "projectile_attachment_dmg",
    "sequential_dmg_pct", "part_dmg_pct", "part_dmg", "received_dmg_pct", "personal_received_dmg_pct", "split_dmg_pct",
    "element_bonus_pct", "element_bonus", "personal_enemy_def_down_pct",
    "normal_atk_dmg_pct", "charge_dmg_pct", "charge_dmg_mag_pct",
})
DERIVED_STATE_STATS = frozenset({
    "atk_caster_based_pct", "atk_from_hp_pct", "def_caster_based_pct",
    "charge_speed_caster_based_pct", "charge_dmg_per_max_ammo_pct",
    "charge_speed_overflow_conversion_pct", "dmg_scale_mag_pct", "hp_copy", "atk_copy",
    "hp_caster_based_pct", "hp_only_caster_based_pct", "max_hp_pct", "max_hp_only_pct",
    "damage_accumulate_ratio_pct", "accumulate_max_scale_pct", "def_pct", "accuracy_pct", "atk_buff_mag_pct",
})
DAMAGE_EVENT_STATS = frozenset({
    "damage", "bonus_damage", "burst_damage", "split_damage", "dot_damage", "armor_break_damage", "core_damage",
    "projectile_attachment_damage", "projectile_explosion_damage", "auto_damage", "fixed_damage_from_dealt_pct", "damage_accumulate",
})
CADENCE_STATS = frozenset({
    "reload_speed_pct", "charge_speed_pct", "charge_time_fixed", "reload_time_fixed", "attack_speed_pct", "mg_warmup_speed_pct",
    "max_ammo_pct", "max_ammo_flat", "ammo_charge_pct", "ammo_charge_flat", "infinite_ammo", "max_ammo_infinite",
    "gauge_consume_as_ammo", "force_reload", "burst_cooldown_reduce", "burst_cooldown", "burst_reentry", "fullburst_duration",
    "skill_cooldown_reduce_pct", "skill_cooldown_pct", "effect_interval", "force_skill_use", "burst_charge_pct",
    "burst_charge_speed_pct", "charge_time_flat", "pellet_count", "pellet_count_fixed",
})
STATE_STATS = frozenset({
    "remove_named_buff", "buff_stack_add", "buff_stack_remove", "buff_max_stack_add", "buff_stack_init", "named_buff_duration_extend",
    "trigger_count_reduce", "persona_state", "debuff_stack_add", "debuff_stack_remove", "gauge_charge", "gauge_consume",
    "gauge_charge_enabled", "gauge_max_add", "effect_target_count_add", "effect_range_pct", "element_code_override",
    "armor_break_enabled", "pierce_enabled", "charge_speed_buff_immune", "charge_speed_debuff_immune",
})
HP_SHIELD_STATS = frozenset({
    "heal_hp_pct", "lifesteal_pct", "current_hp_reduce", "heal_received_pct", "outgoing_heal_pct", "heal_given_pct",
    "heal_equal_split", "heal_split", "heal_overcharge_store", "heal_overcharge_store_atk_pct", "heal_overcharge_discharge",
    "shield_from_max_hp_pct", "shared_shield_from_max_hp_pct", "shield_heal_from_caster_max_hp_pct", "next_shield_hp_pct",
    "shield_restore_pct", "revive", "undying", "invincible", "shield_invincible", "indomitable", "decoy",
    "decoy_from_max_hp_pct", "decoy_heal_from_caster_max_hp_pct", "cover_heal_pct", "cover_revive",
    "cover_hp_caster_based_pct", "cover_heal_from_caster_max_hp_pct", "cover_max_hp_caster_based_pct",
    "cover_received_dmg_split", "received_dmg_split",
})
CONTROL_STATS = frozenset({"taunt", "stun", "stun_immune", "stealth", "targeting_exclude", "focus_fire", "debuff_cleanse", "debuff_immune", "harmful_immune_count", "enemy_buff_cleanse"})
FAST_PATTERN_EXCLUDED = frozenset({"cover_disabled", "cover_def_pct", "shield_dmg_pct", "intercept_dmg_pct", "explosion_range", "pierce_range", "optimal_range_min", "optimal_range_max", "optimal_range_max_pct", "optimal_range_dmg_pct"})
SPECIAL_STATS = frozenset({"feather_refresh", "squad_ammo_consume_as"})
_COMMON_FIELDS = frozenset({"source", "type", "name", "trigger", "target", "stat", "polarity", "values", "fixed_value", "duration", "max_stack", "max_trigger", "scaling", "scaling_ref", "trigger_values", "tick_interval", "note", "favorite"})

class EffectCategory(str, Enum):
    HIT_FORMULA="hit_formula"; DERIVED_STATE="derived_state"; DAMAGE_EVENT="damage_event"; CADENCE_TIMELINE="cadence_timeline"; STATE_TRIGGER="state_trigger"; HP_SHIELD="hp_shield"; CONTROL="control"; MORIS_NOP="moris_nop"; FAST_PATTERN_EXCLUDED="fast_pattern_excluded"; SPECIAL="special"; UNKNOWN="unknown"
class CapabilityDisposition(str, Enum):
    READY="ready"; MIRROR_MORIS_NOP="mirror_moris_nop"; MODEL_EXCLUDED="model_excluded"; PLANNED="planned"; FALLBACK="fallback"; UNKNOWN="unknown"

@dataclass(frozen=True, slots=True)
class EffectCapability:
    character:str; index:int; source:str|None; name:str; effect_type:str; stat:str|None; category:EffectCategory
    timing_families:tuple[str,...]; condition_families:tuple[str,...]; target_family:str; advanced_fields:tuple[str,...]
    disposition:CapabilityDisposition; blockers:tuple[str,...]=()
    @property
    def blocks_fast(self)->bool:
        return self.disposition in {CapabilityDisposition.PLANNED,CapabilityDisposition.FALLBACK,CapabilityDisposition.UNKNOWN}

@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    supported_categories:frozenset[EffectCategory]=frozenset(); supported_stats:frozenset[str]=frozenset(); supported_stat_prefixes:tuple[str,...]=()
    supported_timing_families:frozenset[str]=frozenset(); supported_timing_exact:frozenset[str]=frozenset(); supported_timing_prefixes:tuple[str,...]=()
    supported_condition_families:frozenset[str]=frozenset(); supported_target_families:frozenset[str]=frozenset(); supported_advanced_fields:frozenset[str]=frozenset(); marker_states:bool=False
    def supports_stat(self,stat:str|None,category:EffectCategory,effect_type:str)->bool:
        if stat is None: return self.marker_states and category is EffectCategory.STATE_TRIGGER and effect_type=="buff"
        return stat in self.supported_stats or any(stat.startswith(p) for p in self.supported_stat_prefixes)
    def supports_timing(self,raw:str)->bool:
        fam=timing_family(raw); return fam in self.supported_timing_families or raw in self.supported_timing_exact or any(raw.startswith(p) for p in self.supported_timing_prefixes)

CURRENT_RUNTIME_CAPABILITIES = CapabilityProfile(
    supported_categories=frozenset({EffectCategory.CADENCE_TIMELINE, EffectCategory.DERIVED_STATE}),
    supported_stats=frozenset({
        "burst_cooldown_reduce", "burst_cooldown", "fullburst_duration",
        "reload_speed_pct", "charge_speed_pct", "charge_speed_caster_based_pct",
        "max_ammo_pct", "max_ammo_flat", "ammo_charge_pct", "ammo_charge_flat", "charge_time_flat",
    }),
    supported_stat_prefixes=("burst_stage_override:",),
    supported_timing_families=frozenset({"lifecycle", "burst"}),
    supported_timing_prefixes=("full_charge_count:",),
    supported_condition_families=frozenset({"named_state", "stack", "roster"}),
    supported_target_families=frozenset({"ally_static", "named_character", "ally_dynamic_rank"}),
)

@lru_cache(maxsize=4)
def _impl_status(root:str)->dict[str,str]:
    text=(Path(root)/"context"/"IMPL-STATUS.md").read_text(encoding="utf-8"); out={}
    for line in text.splitlines():
        if not line.startswith("| `"): continue
        cols=[c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols)<2: continue
        status=next((c for c in cols[1:] if any(m in c for m in ("✅","⚠️","❌","🚫"))),None)
        if status is None: continue
        key=cols[0].strip("`")
        if not key.startswith('"'): out[key]=status
    return out

def moris_status(stat:str|None,*,root:Path=_ROOT)->str:
    if not stat:return "unknown"
    impl=_impl_status(str(root))
    if stat in impl:return impl[stat]
    if stat.startswith(("sequential_damage:","bonus_damage:","armor_break_damage:","burst_stage_override:","debuff_immune:")):return "✅"
    return "unknown"

def classify_effect(effect:dict[str,Any],*,root:Path=_ROOT)->EffectCategory:
    typ=str(effect.get("type") or ""); raw_stat=effect.get("stat"); stat=str(raw_stat) if raw_stat is not None else None; status=moris_status(stat,root=root)
    if "❌" in status or "🚫" in status:return EffectCategory.MORIS_NOP
    if typ=="weapon_change":return EffectCategory.CADENCE_TIMELINE
    if stat and stat.startswith(("sequential_damage:","bonus_damage:","armor_break_damage:")):return EffectCategory.DAMAGE_EVENT
    if typ=="damage" or stat in DAMAGE_EVENT_STATS:return EffectCategory.DAMAGE_EVENT
    if stat in HIT_FORMULA_STATS:return EffectCategory.HIT_FORMULA
    if stat in DERIVED_STATE_STATS:return EffectCategory.DERIVED_STATE
    if stat in CADENCE_STATS or (stat and stat.startswith("burst_stage_override:")):return EffectCategory.CADENCE_TIMELINE
    if stat in STATE_STATS or (stat and stat.startswith("debuff_immune:")):return EffectCategory.STATE_TRIGGER
    if stat in HP_SHIELD_STATS:return EffectCategory.HP_SHIELD
    if stat in CONTROL_STATS:return EffectCategory.CONTROL
    if stat in FAST_PATTERN_EXCLUDED:return EffectCategory.FAST_PATTERN_EXCLUDED
    if stat in SPECIAL_STATS:return EffectCategory.SPECIAL
    if stat is None and typ=="buff":return EffectCategory.STATE_TRIGGER
    if stat is None and typ=="instant":return EffectCategory.SPECIAL
    return EffectCategory.UNKNOWN

def timing_family(timing:str)->str:
    if timing in {"battle_start","passive"}:return "lifecycle"
    if timing.startswith(("burst_cast","conditional_burst_cast_count","burst_enter:","full_burst_start","full_burst_end","squad_burst_cast")):return "burst"
    if timing.startswith(("hit_count","conditional_hit_count","full_charge","core_hit","crit_hit","pellet_hit","multi_hit","non_full_charge_hit","charge_hold","part_hit_count","body_hit_count","weapon_hit")) or timing in {"on_attack","last_bullet","last_bullet_fire"}:return "weapon_hit"
    if timing.startswith("every:"):return "periodic"
    if timing.startswith("stack_reach:"):return "state_counter"
    if timing.startswith(("hp_below","received_hit","fatal_hit")):return "incoming_hp"
    if timing.startswith("squad_ammo_consume:"):return "ammo"
    if timing.startswith("event:"):return "named_event"
    if timing in {"enemy_death","squad_part_break","squad_part_hit","feather_tick"}:return "encounter_event"
    return "custom"

def condition_family(condition:str)->str:
    if condition.startswith(("self_state:","not_self_state:","target_state:","not_target_state:")):return "named_state"
    if condition.startswith(("self_stack_above:","target_stack_above:")):return "stack"
    if condition.startswith(("gauge_above:","gauge_below:","gauge_eq:","gauge_mod:")):return "gauge"
    if condition.startswith(("self_hp_","ally_hp_")):return "hp"
    if condition.startswith("prob:") or condition=="trigger_hit_crit":return "rng"
    if condition in {"during_full_burst","not_during_full_burst","during_charge","burst_casted","burst_not_casted","back_row"}:return "simple_runtime"
    if condition.startswith(("target_code:","enemy_count_")) or condition=="core_hit":return "enemy"
    if condition in {"no_burst1_ally","has_burst1_ally","no_defender_ally","has_defender_ally","squad_ally_exists"}:return "roster"
    if "cover" in condition:return "cover"
    if condition in {"during_shield","target_stunned"}:return "control_hp"
    if condition.startswith("self_stat_above:"):return "derived_stat"
    if condition=="focusing":return "special"
    return "custom"

def target_family(target:Any,*,character_names:frozenset[str]=frozenset())->str:
    if isinstance(target,list):return "composite"
    if not isinstance(target,str):return "custom"
    if target in {"self","all_allies","all_allies_excl_self"} or target.startswith(("allies:","allies_adjacent:")):return "ally_static"
    if target.startswith(("allies_weapon:","allies_weapon_excl_self:","allies_class:","allies_code:","allies_code_weapon:","allies_code_weapon_leftmost:","allies_burst3","allies_same_squad","allies_named:","all_allies_burst_","allies_burst_casted_","allies_top_base_charge_time:")):return "ally_filter_static"
    if target.startswith(("allies_top_atk","allies_lowest_hp","allies_top_def","allies_lowest_atk_burst3","allies_below_def","allies_weapon_top_atk","allies_down_top_atk_excl:")):return "ally_dynamic_rank"
    if target.startswith(("allies_with_buff:","allies_without_buff:","allies_burst3_persona","allies_random_debuffed:")):return "ally_state_filter"
    if target.startswith("allies_random:"):return "ally_random"
    if "cover" in target or target=="all_projectiles":return "unsupported_model"
    if target.startswith(("enemy","enemies","target","same_target","all_enemies")) or target in {"target","enemy","same_target","target_body","target_and_nearby"}:return "enemy_singleton"
    if target in character_names:return "named_character"
    return "custom"

def _advanced_fields(effect:dict[str,Any])->tuple[str,...]:
    return tuple(sorted(k for k in set(effect)-_COMMON_FIELDS if not k.startswith("_")))

def inspect_effect(character:str,index:int,effect:dict[str,Any],*,profile:CapabilityProfile=CURRENT_RUNTIME_CAPABILITIES,root:Path=_ROOT,character_names:frozenset[str]=frozenset())->EffectCapability:
    category=classify_effect(effect,root=root); typ=str(effect.get("type") or ""); stat=effect.get("stat"); stat=str(stat) if stat is not None else None
    trigger=effect.get("trigger") or {}; raw_timings=tuple(str(t) for t in trigger.get("timing",[])); timings=tuple(sorted({timing_family(t) for t in raw_timings})); conditions=tuple(sorted({condition_family(str(c)) for c in trigger.get("condition",[])})); target=target_family(effect.get("target"),character_names=character_names); advanced=_advanced_fields(effect)
    if category is EffectCategory.MORIS_NOP: disposition=CapabilityDisposition.MIRROR_MORIS_NOP; blockers=[]
    elif category is EffectCategory.FAST_PATTERN_EXCLUDED: disposition=CapabilityDisposition.MODEL_EXCLUDED; blockers=[]
    elif category is EffectCategory.SPECIAL: disposition=CapabilityDisposition.FALLBACK; blockers=[f"special:{stat or typ}"]
    elif category is EffectCategory.UNKNOWN: disposition=CapabilityDisposition.UNKNOWN; blockers=[f"unknown_stat:{stat}"]
    else:
        blockers=[]
        if category not in profile.supported_categories:blockers.append(f"category:{category.value}")
        if not profile.supports_stat(stat,category,typ):blockers.append(f"stat:{stat}")
        for raw in raw_timings:
            if not profile.supports_timing(raw):blockers.append(f"timing:{timing_family(raw)}")
        for fam in conditions:
            if fam not in profile.supported_condition_families:blockers.append(f"condition:{fam}")
        if target not in profile.supported_target_families:blockers.append(f"target:{target}")
        for field in advanced:
            if field not in profile.supported_advanced_fields:blockers.append(f"field:{field}")
        disposition=CapabilityDisposition.READY if not blockers else CapabilityDisposition.PLANNED
    return EffectCapability(character,index,effect.get("source"),str(effect.get("name") or ""),typ,stat,category,timings,conditions,target,advanced,disposition,tuple(blockers))

def inspect_character_effects(character:str,effects:Iterable[dict[str,Any]],*,profile:CapabilityProfile=CURRENT_RUNTIME_CAPABILITIES,root:Path=_ROOT,character_names:frozenset[str]=frozenset())->tuple[EffectCapability,...]:
    return tuple(inspect_effect(character,i,effect,profile=profile,root=root,character_names=character_names) for i,effect in enumerate(effects))
