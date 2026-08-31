from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

HIT_FORMULA_STATS = {
    "atk_pct", "atk_flat", "def_ignore_pct", "crit_rate", "normal_atk_crit_rate",
    "crit_dmg", "normal_atk_crit_dmg", "core_dmg_pct", "atk_dmg_pct",
    "burst_dmg_pct", "burst_dmg_aoe_pct", "pierce_dmg_pct", "armor_break_dmg_pct",
    "dot_dmg_pct", "projectile_explosion_dmg_pct", "projectile_attachment_dmg_pct",
    "sequential_dmg_pct", "part_dmg_pct", "received_dmg_pct", "split_dmg_pct",
    "element_bonus_pct", "normal_atk_dmg_pct", "charge_dmg_pct", "charge_dmg_mag_pct",
}

DERIVED_STATE_STATS = {
    "atk_caster_based_pct", "atk_from_hp_pct", "def_caster_based_pct",
    "charge_speed_caster_based_pct", "charge_dmg_per_max_ammo_pct",
    "charge_speed_overflow_conversion_pct", "dmg_scale_mag_pct", "hp_copy", "atk_copy",
    "hp_caster_based_pct", "hp_only_caster_based_pct", "max_hp_pct", "max_hp_only_pct",
    "damage_accumulate_ratio_pct", "accumulate_max_scale_pct", "def_pct", "accuracy_pct",
    "atk_buff_mag_pct",
}

DAMAGE_EVENT_STATS = {
    "damage", "bonus_damage", "burst_damage", "split_damage", "dot_damage",
    "armor_break_damage", "core_damage", "projectile_attachment_damage",
    "projectile_explosion_damage", "auto_damage", "fixed_damage_from_dealt_pct",
    "damage_accumulate",
}

CADENCE_STATS = {
    "reload_speed_pct", "charge_speed_pct", "charge_time_fixed", "reload_time_fixed",
    "attack_speed_pct", "mg_warmup_speed_pct", "max_ammo_pct", "max_ammo_flat",
    "ammo_charge_pct", "ammo_charge_flat", "infinite_ammo", "max_ammo_infinite",
    "gauge_consume_as_ammo", "force_reload", "burst_cooldown_reduce", "burst_cooldown",
    "burst_reentry", "fullburst_duration", "skill_cooldown_reduce_pct", "skill_cooldown_pct",
    "effect_interval", "force_skill_use", "burst_charge_pct", "burst_charge_speed_pct",
    "charge_time_flat", "pellet_count", "pellet_count_fixed",
}

STATE_STATS = {
    "remove_named_buff", "buff_stack_add", "buff_stack_remove", "buff_max_stack_add",
    "buff_stack_init", "named_buff_duration_extend", "trigger_count_reduce", "persona_state",
    "debuff_stack_add", "debuff_stack_remove", "gauge_charge", "gauge_consume",
    "gauge_charge_enabled", "gauge_max_add", "effect_target_count_add", "effect_range_pct",
    "element_code_override", "armor_break_enabled", "pierce_enabled",
    "charge_speed_buff_immune", "charge_speed_debuff_immune",
}

HP_SHIELD_STATS = {
    "heal_hp_pct", "lifesteal_pct", "current_hp_reduce", "heal_received_pct",
    "outgoing_heal_pct", "heal_given_pct", "heal_equal_split", "heal_split",
    "heal_overcharge_store", "heal_overcharge_store_atk_pct", "heal_overcharge_discharge",
    "shield_from_max_hp_pct", "shared_shield_from_max_hp_pct", "shield_heal_from_caster_max_hp_pct",
    "next_shield_hp_pct", "shield_restore_pct", "revive", "undying", "invincible",
    "shield_invincible", "indomitable", "decoy", "decoy_from_max_hp_pct",
    "decoy_heal_from_caster_max_hp_pct", "cover_heal_pct", "cover_revive",
    "cover_hp_caster_based_pct", "cover_heal_from_caster_max_hp_pct",
    "cover_max_hp_caster_based_pct", "cover_received_dmg_split", "received_dmg_split",
}

CONTROL_STATS = {
    "taunt", "stun", "stun_immune", "stealth", "targeting_exclude", "focus_fire",
    "debuff_cleanse", "debuff_immune", "harmful_immune_count", "enemy_buff_cleanse",
}

SPECIAL_STATS = {
    "feather_refresh", "squad_ammo_consume_as", "heal_overcharge_store_atk_pct",
    "heal_overcharge_discharge", "received_dmg_split",
}

FAST_PATTERN_EXCLUDED = {
    "cover_disabled", "cover_def_pct", "shield_dmg_pct", "intercept_dmg_pct",
    "explosion_range", "pierce_range", "optimal_range_min", "optimal_range_max",
    "optimal_range_max_pct", "optimal_range_dmg_pct",
}


def _parse_impl_status(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 2:
            continue
        status = next((c for c in cols[1:] if any(m in c for m in ("✅", "⚠️", "❌", "🚫"))), None)
        if status is None:
            continue
        key = cols[0].strip("`")
        if key.startswith('"'):
            continue
        out[key] = status
    return out


def _status_for(stat: str | None, impl: dict[str, str]) -> str:
    if not stat:
        return "unknown"
    if stat in impl:
        return impl[stat]
    if stat.startswith(("sequential_damage:", "bonus_damage:", "armor_break_damage:", "burst_stage_override:", "debuff_immune:")):
        return "✅"
    return "unknown"


def classify(effect: dict[str, Any], impl: dict[str, str]) -> str:
    typ = str(effect.get("type") or "")
    stat = effect.get("stat")
    stat = str(stat) if stat is not None else None
    status = _status_for(stat, impl)

    if "❌" in status or "🚫" in status:
        return "moris_nop"
    if typ == "weapon_change":
        return "cadence_timeline"
    if stat and stat.startswith(("sequential_damage:", "bonus_damage:", "armor_break_damage:")):
        return "damage_event"
    if typ == "damage" or stat in DAMAGE_EVENT_STATS:
        return "damage_event"
    if stat in HIT_FORMULA_STATS:
        return "hit_formula"
    if stat in DERIVED_STATE_STATS:
        return "derived_state"
    if stat in CADENCE_STATS or (stat and stat.startswith("burst_stage_override:")):
        return "cadence_timeline"
    if stat in STATE_STATS or (stat and stat.startswith("debuff_immune:")):
        return "state_trigger"
    if stat in HP_SHIELD_STATS:
        return "hp_shield"
    if stat in CONTROL_STATS:
        return "control"
    if stat in FAST_PATTERN_EXCLUDED:
        return "fast_pattern_excluded"
    if stat in SPECIAL_STATS:
        return "special"
    if stat is None and typ == "buff":
        return "state_trigger"
    if stat is None and typ == "instant":
        return "special"
    return "unknown"


def inventory(root: Path) -> dict[str, Any]:
    skills = json.loads((root / "data" / "parsed_skills.json").read_text(encoding="utf-8"))
    impl = _parse_impl_status((root / "context" / "IMPL-STATUS.md").read_text(encoding="utf-8"))
    effects = [(name, idx, eff) for name, arr in skills.items() for idx, eff in enumerate(arr)]

    counts = Counter()
    unknown_stats = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = []
    for char, idx, eff in effects:
        category = classify(eff, impl)
        counts[category] += 1
        stat = eff.get("stat")
        if category == "unknown":
            unknown_stats[str(stat)] += 1
        if len(examples[category]) < 8:
            examples[category].append({
                "character": char,
                "index": idx,
                "source": eff.get("source"),
                "name": eff.get("name"),
                "type": eff.get("type"),
                "stat": stat,
                "trigger": eff.get("trigger"),
                "target": eff.get("target"),
            })
        rows.append({"character": char, "index": idx, "category": category, "effect": eff})

    return {
        "characters": len(skills),
        "effects": len(effects),
        "counts": dict(sorted(counts.items())),
        "unknown_stats": dict(unknown_stats.most_common()),
        "examples": dict(examples),
        "rows": rows,
    }


def render_markdown(inv: dict[str, Any]) -> str:
    lines = [
        "# Fast Engine damage-semantics inventory",
        "",
        "Generated from the current Moris `parsed_skills.json` plus documented implementation status.",
        "This is a design audit, not a claim that Fast already supports these effects.",
        "",
        f"- characters: **{inv['characters']}**",
        f"- effects: **{inv['effects']}**",
        "",
        "## Category counts",
        "",
        "| category | effects |",
        "| --- | ---: |",
    ]
    for key, value in inv["counts"].items():
        lines.append(f"| `{key}` | {value} |")
    lines += ["", "## Unknown stats", ""]
    if inv["unknown_stats"]:
        for key, value in inv["unknown_stats"].items():
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("None.")
    lines += ["", "## Special / fallback surface", ""]
    specials = inv.get("examples", {}).get("special", [])
    if specials:
        for row in specials:
            lines.append(f"- `{row['character']}` — `{row['stat']}` — {row['name']}")
    else:
        lines.append("None.")
    lines += [
        "",
        "## Interpretation",
        "",
        "- `hit_formula`: state consumed directly by the single-hit damage kernel after activation/target resolution.",
        "- `derived_state`: runtime value must be derived from ATK/HP/ammo/gauge/etc. before damage can be evaluated.",
        "- `damage_event`: creates or releases damage and therefore needs event semantics, not only a buff scalar.",
        "- `cadence_timeline`: changes how many attacks/bursts occur or when they occur.",
        "- `state_trigger`: named state/stack/gauge/event plumbing that can change future effects.",
        "- `hp_shield`: character-owned HP/shield semantics. Boss incoming-damage chronology remains outside initial Fast scope.",
        "- `control`: control/debuff mechanics; only the subset affecting theoretical static ranking will eventually need Fast implementation.",
        "- `moris_nop`: Moris authority currently does not implement the documented stat; Fast should initially mirror that NOP unless authority changes.",
        "- `fast_pattern_excluded`: deliberately outside the initial patternless Fast target model.",
        "- `special`: explicit generic/special subsystem work or Moris fallback until implemented.",
        "- `unknown`: audit blocker. Do not silently compile to zero.",
        "",
        "## Next gate",
        "",
        "The current snapshot has no unknown rows. Use these categories to build the capability manifest and state/trigger store before implementing the damage kernel.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--markdown", type=Path)
    ns = ap.parse_args()
    inv = inventory(ns.root)
    slim = {k: v for k, v in inv.items() if k != "rows"}
    if ns.json:
        ns.json.parent.mkdir(parents=True, exist_ok=True)
        ns.json.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    if ns.markdown:
        ns.markdown.parent.mkdir(parents=True, exist_ok=True)
        ns.markdown.write_text(render_markdown(inv), encoding="utf-8")
    print(json.dumps({k: v for k, v in slim.items() if k not in {"examples"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
