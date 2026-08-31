from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from calculator.base_stat import calc_base_stats
from calculator.buff_manager import char_effects

_ROOT = Path(__file__).resolve().parents[2]
_NIKKE = json.loads((_ROOT / "data" / "parsed_nikke.json").read_text(encoding="utf-8"))

from .capabilities import CURRENT_RUNTIME_CAPABILITIES, inspect_character_effects
from .model import CompiledCharacter, CompiledSquad


_WEAPON_KEYS = (
    "weapon_type",
    "max_ammo",
    "reload_time",
    "fire_rate",
    "fire_rate_max",
    "fire_rate_change_pershot",
    "pellets",
    "muzzles",
    "damage_coeff",
    "core_dmg_mult",
    "full_charge_mult",
    "charge_time",
)


def _weapon_view(meta: dict[str, Any]) -> dict[str, Any]:
    return {key: meta[key] for key in _WEAPON_KEYS if key in meta}


def compile_moris_squad(squad: list[dict], *, require_five: bool = True) -> CompiledSquad:
    """Compile already-built Moris character dicts into immutable Fast input.

    Input assembly remains Moris-owned (`context.spec.build_squad`).  This
    function intentionally does not reimplement profile/equipment/favorite
    selection. Compile-time use of Moris helpers is cheap and keeps both engines
    on the same account/build semantics.
    """

    if require_five and len(squad) != 5:
        raise ValueError(f"Fast Solo Raid squad must contain 5 members, got {len(squad)}")

    out: list[CompiledCharacter] = []
    seen: set[str] = set()
    for char in squad:
        name = str(char["name"])
        if name in seen:
            raise ValueError(f"duplicate squad member: {name}")
        seen.add(name)
        meta = _NIKKE.get(name)
        if meta is None:
            raise ValueError(f"unknown Moris character: {name}")
        stats = calc_base_stats(char)
        favorite_stage = int(char.get("favorite_stage", 3))
        effects = tuple(char_effects(name, favorite_stage))
        capabilities = inspect_character_effects(
            name, effects, profile=CURRENT_RUNTIME_CAPABILITIES,
            root=_ROOT, character_names=frozenset(_NIKKE),
        )
        out.append(
            CompiledCharacter(
                name=name,
                base_atk=float(stats["atk"]),
                base_def=float(stats["def"]),
                base_hp=float(stats["hp"]),
                element=meta.get("element_code"),
                burst_stage=str(meta.get("burst_stage", "")),
                burst_cooldown=float(meta.get("burst_cooldown") or 0.0),
                weapon_type=str(meta.get("weapon_type", "")),
                weapon=_weapon_view(meta),
                effects=effects,
                effect_capabilities=capabilities,
                skill_levels=dict(char.get("skill_levels") or {}),
                favorite_stage=favorite_stage,
            )
        )
    return CompiledSquad(tuple(out))
