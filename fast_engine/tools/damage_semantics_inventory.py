from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

from fast_engine.engine.capabilities import classify_effect


def classify(effect: dict[str, Any], impl: dict[str, str] | None = None, *, root: Path = ROOT) -> str:
    """Compatibility wrapper around the production Fast semantics classifier."""
    return classify_effect(effect, root=root).value


def inventory(root: Path) -> dict[str, Any]:
    skills = json.loads((root / "data" / "parsed_skills.json").read_text(encoding="utf-8"))
    effects = [(name, idx, eff) for name, arr in skills.items() for idx, eff in enumerate(arr)]

    counts = Counter()
    unknown_stats = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = []
    for char, idx, eff in effects:
        category = classify(eff, root=root)
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
