from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from calculator.base_stat import calc_base_stats

_ROOT = Path(__file__).resolve().parents[2]
_NIKKE = json.loads((_ROOT / "data" / "parsed_nikke.json").read_text(encoding="utf-8"))
_MECHANICS = json.loads((_ROOT / "data" / "weapon_mechanics.json").read_text(encoding="utf-8"))
_DELAYS = json.loads((_ROOT / "data" / "weapon_delays.json").read_text(encoding="utf-8"))

from .capabilities import (
    CURRENT_RUNTIME_CAPABILITIES,
    CapabilityDisposition,
    inspect_effect,
)
from .conditions import compile_condition
from .model import CompiledCharacter, CompiledEffect, CompiledSquad
from .moris_bridge import effect_skill_level, registered_effects
from .targets import compile_target
from .triggers import TriggerIndex, compile_trigger_rule


def _pick(key: str, *sources: dict[str, Any] | None, default=None):
    for source in sources:
        if source is not None and source.get(key) is not None:
            return source[key]
    return default


def _weapon_view(name: str, meta: dict[str, Any], char: dict[str, Any]) -> dict[str, Any]:
    """Compile Moris weapon metadata into a branch-light Fast view.

    This mirrors the *data precedence* used by CharState without importing its
    frame-loop execution model. Values that depend on live buffs stay runtime
    concerns.
    """
    weapon_type = str(meta["weapon_type"])
    mech = _MECHANICS["weapon_type_defaults"][weapon_type]
    delay_exc = _DELAYS["_exceptions"].get(name, {})
    delay_wt = _DELAYS["_defaults_by_weapon_type"].get(weapon_type, {})
    fire_mode = str(meta.get("fire_mode") or mech["type"])
    fire_rate = float(_pick(
        "fire_rate", delay_exc, meta, mech, default=mech.get("fire_rate_min", 1.0)
    ))
    fire_rate_max = _pick("fire_rate_max", delay_exc, meta, mech)
    fr_step = _pick("fire_rate_change_pershot", delay_exc, meta)
    if fire_rate_max is not None and fr_step:
        warmup_bullets = (float(fire_rate_max) - fire_rate) / float(fr_step)
    else:
        warmup_bullets = float(mech.get("warmup_bullets", 1.0))
    charge_frames = char.get("charge_time_frames")
    charge_time = (float(charge_frames) / 60.0) if charge_frames is not None else float(meta.get("charge_time") or 0.0)
    clip_chars = _MECHANICS.get("clip_characters", {}).get(weapon_type, [])
    normal_hit_coeff = float(
        (_MECHANICS.get("normal_hit_coeff") or {}).get(weapon_type, 1.0)
    )
    accuracy_table = _MECHANICS.get("accuracy") or {}
    accuracy_spec = accuracy_table.get(weapon_type) or {}
    return {
        "weapon_type": weapon_type,
        "fire_mode": fire_mode,
        "max_ammo": int(meta["max_ammo"]),
        "reload_time": float(meta["reload_time"]),
        "fire_rate": fire_rate,
        "fire_rate_max": None if fire_rate_max is None else float(fire_rate_max),
        "warmup_bullets": float(warmup_bullets),
        "warmup_cooldown_time": float(mech.get("cooldown_time", 1.0)),
        "post_fire_delay": float(_pick("post_fire_delay", delay_exc, delay_wt, mech, default=0.0)),
        "post_reload_delay": float(_pick("post_reload_delay", delay_exc, delay_wt, default=0.0)),
        "reload_start_delay": float(_pick("reload_start_delay", delay_exc, delay_wt, default=0.0)),
        "cover_during_delay": bool(delay_exc.get("cover_during_delay", False)),
        "charge_time": charge_time,
        "pellets": int(_pick("pellets", delay_exc, meta, mech, default=1)),
        "muzzles": int(_pick("muzzles", delay_exc, meta, mech, default=1)),
        "is_clip": name in clip_chars,
        "damage_coeff": float(meta.get("damage_coeff") or 0.0),
        "core_dmg_mult": float(meta.get("core_dmg_mult") or 200.0),
        "full_charge_mult": float(meta.get("full_charge_mult") or 100.0),
        "normal_hit_coeff": normal_hit_coeff,
        # Static accuracy model inputs are compiled once. Runtime only supplies
        # the current accuracy_pct and boss core_px; no JSON lookup is needed in
        # the scoring hot path.
        "core_base_diameter": float(accuracy_spec.get("base_diameter", 10.0)),
        "core_acc_slope": float(accuracy_spec.get("acc_slope", 0.0)),
        "core_model_n": float(accuracy_table.get("_model_n", 2.55)),
    }


_CORE_EFFECT_KEYS = frozenset({
    "source", "type", "name", "trigger", "target", "stat", "polarity",
    "values", "fixed_value", "duration", "duration_values", "max_stack",
    "max_trigger", "tick_interval", "trigger_values",
})


def _level_value(mapping: Any, skill_level: str, default: float | None = None) -> float | None:
    if not isinstance(mapping, dict):
        return default
    raw = mapping.get(skill_level, mapping.get("10"))
    if raw is None:
        return default
    return float(raw)


def _effect_value(effect: dict[str, Any], skill_level: str) -> float | None:
    if "fixed_value" in effect:
        return float(effect["fixed_value"])
    return _level_value(effect.get("values"), skill_level)


def _effect_duration(effect: dict[str, Any], skill_level: str) -> float | None:
    duration = effect.get("duration")
    if duration is None and "duration_values" in effect:
        duration = _level_value(effect.get("duration_values"), skill_level, 0.0)
    return None if duration is None else float(duration)


def _trigger_value(effect: dict[str, Any], skill_level: str) -> float | None:
    return _level_value(effect.get("trigger_values"), skill_level)


def _parameters(effect: dict[str, Any]) -> dict[str, Any]:
    # Private Moris metadata is provenance/cache information, not Fast semantics.
    return {
        key: value
        for key, value in effect.items()
        if key not in _CORE_EFFECT_KEYS and not key.startswith("_")
    }


def _promote_exact_last_bullet_capability(capability, timings, effect, owner_meta):
    """Certify the first fail-closed slice of exact `last_bullet_fire`.

    Moris charge weapons emit `last_bullet_fire` when the final charge *starts*,
    not when that projectile later fires, so charge mode stays PLANNED. Likewise,
    a last-bullet effect that changes weapon cadence would invalidate precompiled
    future magazine boundaries. For now only non-charge instant burst CDR is
    certified; the broad weapon-hit family and cadence-mutating last-bullet buffs
    remain PLANNED until dynamic multi-signal weapon boundaries exist.
    """
    weapon_type = str(owner_meta.get("weapon_type") or "")
    fire_mode = str(
        owner_meta.get("fire_mode")
        or _MECHANICS.get("weapon_type_defaults", {}).get(weapon_type, {}).get("type")
        or ""
    )
    safe_effect = (
        fire_mode in {"auto", "auto_warmup"}
        and effect.get("type") == "instant"
        and effect.get("stat") == "burst_cooldown_reduce"
    )
    if (
        safe_effect
        and capability.disposition is CapabilityDisposition.PLANNED
        and capability.blockers == ("timing:weapon_hit",)
        and timings
        and all(rule.raw == "last_bullet_fire" for rule in timings)
    ):
        return replace(
            capability,
            disposition=CapabilityDisposition.READY,
            blockers=(),
        )
    return capability


def compile_moris_squad(squad: list[dict], *, require_five: bool = True) -> CompiledSquad:
    """Compile already-built Moris character dicts into immutable Fast input.

    Input assembly remains Moris-owned (`context.spec.build_squad`). Effect
    expansion is also Moris-owned at this boundary: the compile-only bridge uses
    the exact BuffManager registration path so overload/equipment, cube,
    collection, manual stats and favorite-stage skill variants cannot silently
    disappear. The Fast combat runtime itself never instantiates BuffManager.
    """
    if require_five and len(squad) != 5:
        raise ValueError(f"Fast Solo Raid squad must contain 5 members, got {len(squad)}")

    seen: set[str] = set()
    actor_by_name: dict[str, int] = {}
    stats_by_actor: list[dict[str, float]] = []
    meta_by_actor: list[dict[str, Any]] = []
    for actor, char in enumerate(squad):
        name = str(char["name"])
        if name in seen:
            raise ValueError(f"duplicate squad member: {name}")
        seen.add(name)
        meta = _NIKKE.get(name)
        if meta is None:
            raise ValueError(f"unknown Moris character: {name}")
        actor_by_name[name] = actor
        stats_by_actor.append(calc_base_stats(char))
        meta_by_actor.append(meta)

    registered = registered_effects(squad)
    char_names = frozenset(_NIKKE)
    effects_by_actor: list[list[CompiledEffect]] = [[] for _ in squad]

    for effect_id, (effect, caster_name) in enumerate(registered):
        actor = actor_by_name[caster_name]
        char = squad[actor]
        actor_effect_index = len(effects_by_actor[actor])
        skill_level = effect_skill_level(char, effect)
        trigger_value = _trigger_value(effect, skill_level)
        timings = tuple(
            compile_trigger_rule(timing, trigger_value=trigger_value)
            for timing in (effect.get("trigger") or {}).get("timing", ())
        )
        raw_conditions = tuple(str(c) for c in (effect.get("trigger") or {}).get("condition", ()))
        condition_rules = tuple(compile_condition(c, trigger_value=trigger_value) for c in raw_conditions)
        target_spec = compile_target(effect.get("target"), actor_by_name=actor_by_name)
        capability = inspect_effect(
            caster_name,
            actor_effect_index,
            effect,
            profile=CURRENT_RUNTIME_CAPABILITIES,
            root=_ROOT,
            character_names=char_names,
        )
        capability = _promote_exact_last_bullet_capability(
            capability, timings, effect, meta_by_actor[actor]
        )
        effects_by_actor[actor].append(
            CompiledEffect(
                effect_id=effect_id,
                actor=actor,
                actor_effect_index=actor_effect_index,
                source=effect.get("source"),
                source_tag=str(effect.get("_source_tag") or "skill"),
                name=str(effect.get("name") or effect.get("stat") or "effect"),
                effect_type=str(effect.get("type") or "buff"),
                stat=effect.get("stat"),
                polarity=effect.get("polarity"),
                target=effect.get("target"),
                target_spec=target_spec,
                conditions=raw_conditions,
                condition_rules=condition_rules,
                triggers=timings,
                value=_effect_value(effect, skill_level),
                duration=_effect_duration(effect, skill_level),
                max_stack=(None if effect.get("max_stack") is None else float(effect["max_stack"])),
                max_trigger=(None if effect.get("max_trigger") is None else int(effect["max_trigger"])),
                tick_interval=(None if effect.get("tick_interval") is None else float(effect["tick_interval"])),
                parameters=_parameters(effect),
                capability=capability,
            )
        )

    members: list[CompiledCharacter] = []
    for actor, char in enumerate(squad):
        name = str(char["name"])
        meta = meta_by_actor[actor]
        stats = stats_by_actor[actor]
        members.append(
            CompiledCharacter(
                name=name,
                base_atk=float(stats["atk"]),
                base_def=float(stats["def"]),
                base_hp=float(stats["hp"]),
                element=meta.get("element_code"),
                character_class=str(meta.get("class") or ""),
                squad_group=meta.get("squad"),
                burst_stage=str(meta.get("burst_stage") or ""),
                burst_cooldown=float(meta.get("burst_cooldown") or 40.0),
                burst_regen_time=float(char.get("burst_regen_time", 2.0)),
                weapon_type=str(meta.get("weapon_type") or ""),
                weapon=_weapon_view(name, meta, char),
                effects=tuple(effects_by_actor[actor]),
                skill_levels=dict(char.get("skill_levels") or {}),
                favorite_stage=int(char.get("favorite_stage", 0)),
            )
        )

    effects = tuple(effect for member in members for effect in member.effects)
    return CompiledSquad(tuple(members), TriggerIndex.from_effects(effects, actor_count=len(members)))
