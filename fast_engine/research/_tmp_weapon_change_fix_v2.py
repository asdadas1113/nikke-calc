from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found: {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Normalize level-mapped weapon-change damage coefficients at the Fast compiler boundary.
replace_once(
    "fast_engine/engine/compiler.py",
    '''def _parameters(effect: dict[str, Any]) -> dict[str, Any]:\n    # Private Moris metadata is provenance/cache information, not Fast semantics.\n    return {\n        key: value\n        for key, value in effect.items()\n        if key not in _CORE_EFFECT_KEYS and not key.startswith("_")\n    }\n''',
    '''def _parameters(effect: dict[str, Any], skill_level: str) -> dict[str, Any]:\n    # Private Moris metadata is provenance/cache information, not Fast semantics.\n    params = {\n        key: value\n        for key, value in effect.items()\n        if key not in _CORE_EFFECT_KEYS and not key.startswith("_")\n    }\n    # Weapon-change advanced fields can carry the same per-skill-level tables as\n    # ordinary ``values``. Resolve only the comparison-critical coefficient used\n    # by the first Fast weapon-change slice; unrelated advanced maps stay opaque.\n    if effect.get("type") == "weapon_change":\n        raw_coeff = params.get("damage_coeff")\n        if isinstance(raw_coeff, dict):\n            resolved = _level_value(raw_coeff, skill_level)\n            if resolved is not None:\n                params["damage_coeff"] = resolved\n    return params\n''',
)
replace_once(
    "fast_engine/engine/compiler.py",
    '''                parameters=_parameters(effect),\n''',
    '''                parameters=_parameters(effect, skill_level),\n''',
)

# The old prototype expected a synthetic reset_ammo field and READY capability.
# Actual Moris IR models ammo reset as weapon-change semantics and keeps advanced
# fields PLANNED. Permit only that exact advanced-field family.
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''            effect.capability.disposition is CapabilityDisposition.READY\n            and effect.effect_type == "weapon_change"\n''',
    '''            effect.capability.disposition is CapabilityDisposition.PLANNED\n            and set(effect.capability.blockers).issubset({\n                "stat:None",\n                "field:weapon_type",\n                "field:damage_coeff",\n                "field:max_ammo",\n                "field:full_charge_mult",\n                "field:post_fire_delay",\n                "field:cover_during_delay",\n                "field:reload_seconds",\n                "field:reload_time",\n                "field:charge_seconds",\n                "field:charge_time",\n            })\n            and effect.effect_type == "weapon_change"\n''',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''            "post_fire_delay", "cover_during_delay", "reset_ammo",\n''',
    '''            "post_fire_delay", "cover_during_delay",\n''',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''            and params.get("max_ammo") == -1\n            and params.get("reset_ammo") is True\n            and isinstance(params.get("damage_coeff"), (int, float))\n''',
    '''            and params.get("max_ammo") == -1\n            and isinstance(params.get("damage_coeff"), (int, float))\n''',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''        charge = params.get("charge_seconds", params.get("charge_time"))\n        if not isinstance(charge, (int, float)) or float(charge) < 0.0:\n''',
    '''        charge = params.get("charge_seconds", params.get("charge_time", 1.0))\n        if not isinstance(charge, (int, float)) or float(charge) < 0.0:\n''',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''        charge = float(params.get("charge_seconds", params.get("charge_time", 0.0)))\n''',
    '''        charge = float(params.get("charge_seconds", params.get("charge_time", 1.0)))\n''',
)
replace_once(
    "fast_engine/engine/score.py",
    '''    charge = float(params.get("charge_seconds", params.get("charge_time", 0.0)))\n''',
    '''    charge = float(params.get("charge_seconds", params.get("charge_time", 1.0)))\n''',
)

# Moris weapon-change entry/restore always resets the magazine; no per-effect flag.
replace_once(
    "fast_engine/tests/test_dynamic_weapon_change.py",
    '''        self.assertTrue(effect.parameters.get("reset_ammo"))\n''',
    '''        self.assertEqual(effect.parameters.get("damage_coeff"), 51.46)\n        self.assertEqual(effect.parameters.get("full_charge_mult"), 250)\n''',
)
