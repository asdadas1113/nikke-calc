from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from fast_engine.engine.capabilities import (
    CURRENT_RUNTIME_CAPABILITIES,
    CapabilityDisposition,
    EffectCategory,
    inspect_effect,
)

ROOT = Path(__file__).resolve().parents[2]


def build_manifest(root: Path = ROOT) -> dict:
    skills = json.loads((root / "data" / "parsed_skills.json").read_text(encoding="utf-8"))
    names = frozenset(skills)
    dispositions = Counter()
    categories = Counter()
    blockers = Counter()
    rows = []
    for char, effects in skills.items():
        for i, effect in enumerate(effects):
            cap = inspect_effect(
                char,
                i,
                effect,
                profile=CURRENT_RUNTIME_CAPABILITIES,
                root=root,
                character_names=names,
            )
            dispositions[cap.disposition.value] += 1
            categories[cap.category.value] += 1
            blockers.update(cap.blockers)
            rows.append(cap)
    return {
        "characters": len(skills),
        "effects": len(rows),
        "dispositions": dict(sorted(dispositions.items())),
        "categories": dict(sorted(categories.items())),
        "top_blockers": blockers.most_common(30),
        "fallback": [
            {
                "character": r.character,
                "index": r.index,
                "name": r.name,
                "stat": r.stat,
                "blockers": list(r.blockers),
            }
            for r in rows
            if r.disposition in {CapabilityDisposition.FALLBACK, CapabilityDisposition.UNKNOWN}
        ],
    }


def render_markdown(manifest: dict) -> str:
    lines = [
        "# Fast Engine capability manifest",
        "",
        "Generated from the current Moris parsed-skill snapshot and the **certified current Fast runtime profile**.",
        "Structural representability is not the same as runtime support: a generic effect remains `planned` until its primitive is implemented and parity/recall-tested.",
        "",
        f"- characters: **{manifest['characters']}**",
        f"- effects: **{manifest['effects']}**",
        "",
        "## Runtime dispositions",
        "",
        "| disposition | effects |",
        "| --- | ---: |",
    ]
    for key, value in manifest["dispositions"].items():
        lines.append(f"| `{key}` | {value} |")
    lines += ["", "## Semantic categories", "", "| category | effects |", "| --- | ---: |"]
    for key, value in manifest["categories"].items():
        lines.append(f"| `{key}` | {value} |")
    lines += [
        "",
        "## Explicit fallback surface",
        "",
    ]
    if manifest["fallback"]:
        for row in manifest["fallback"]:
            lines.append(
                f"- `{row['character']}` — `{row['stat']}` — {row['name']} "
                f"({', '.join(row['blockers'])})"
            )
    else:
        lines.append("None.")
    lines += [
        "",
        "## Interpretation",
        "",
        "- `ready`: primitive is certified in the current runtime revision.",
        "- `planned`: structurally understood but not yet certified in production Fast.",
        "- `mirror_moris_nop`: Moris authority currently ignores the effect; Fast mirrors that behavior and it does not block routing.",
        "- `model_excluded`: intentionally omitted by the patternless Fast enemy contract.",
        "- `fallback`: explicit special subsystem/Moris route until implemented.",
        "- `unknown`: audit failure; never silently approximate it.",
        "",
        "The Phase 2 greenfield baseline intentionally starts with no combat effects marked `ready`. StateStore/scheduler/compiler infrastructure does not count as certified skill execution.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--markdown", type=Path)
    ap.add_argument("--json", type=Path)
    ns = ap.parse_args()
    manifest = build_manifest(ns.root)
    if ns.markdown:
        ns.markdown.parent.mkdir(parents=True, exist_ok=True)
        ns.markdown.write_text(render_markdown(manifest), encoding="utf-8")
    if ns.json:
        ns.json.parent.mkdir(parents=True, exist_ok=True)
        ns.json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
