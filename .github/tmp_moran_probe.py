from __future__ import annotations

import dataclasses
from pathlib import Path

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

TEAMS = [
    "스쿼드4",
    "레이드_이브레이븐",
    "레이드_아니스서머메이든",
    "레이드_브리드디젤",
    "레이드_트리나홍련",
]


def dump_obj(obj):
    if dataclasses.is_dataclass(obj):
        try:
            return dataclasses.asdict(obj)
        except Exception:
            return repr(obj)
    return repr(obj)


def grep_context(path: str, tokens: tuple[str, ...], pad: int = 3):
    p = Path(path)
    if not p.exists():
        return
    lines = p.read_text(encoding="utf-8").splitlines()
    hits = []
    for i, line in enumerate(lines):
        if any(tok in line for tok in tokens):
            hits.append(i)
    seen = set()
    print(f"\n=== GREP {path} tokens={tokens} hits={len(hits)} ===")
    for i in hits:
        lo = max(0, i - pad)
        hi = min(len(lines), i + pad + 1)
        key = (lo, hi)
        if key in seen:
            continue
        seen.add(key)
        for j in range(lo, hi):
            print(f"{j+1:5d}: {lines[j]}")
        print("---")


print("=== PUBLIC MORAN TEAMS ===")
for team in TEAMS:
    row = snapshot.SQUADS[team]
    moris = spec.build_squad(list(row["members"]))
    squad = compile_moris_squad(moris)
    moran_idx = next(i for i, m in enumerate(squad.members) if m.name == "목단")
    print(f"\n### {team}")
    print("members", [m.name for m in squad.members])
    print("moran_index", moran_idx)
    print("moran_weapon", dump_obj(squad.members[moran_idx].weapon))
    blockers = static_score_blockers(squad)
    print("all_blockers", blockers)
    print("moran_blockers", tuple(x for x in blockers if ":목단:" in x))
    print("moran_effects")
    for e in squad.members[moran_idx].effects:
        print({
            "id": e.effect_id,
            "name": e.name,
            "type": e.effect_type,
            "stat": e.stat,
            "value": e.value,
            "duration": e.duration,
            "max_stack": e.max_stack,
            "max_trigger": e.max_trigger,
            "tick_interval": e.tick_interval,
            "target": e.target,
            "target_spec": dump_obj(e.target_spec),
            "polarity": e.polarity,
            "parameters": dict(e.parameters),
            "conditions": [dump_obj(x) for x in e.condition_rules],
            "triggers": [dump_obj(x) for x in e.triggers],
            "capability": dump_obj(e.capability),
        })

print("\n=== MORIS 25s TRACE: 스쿼드4 ===")
row = snapshot.SQUADS["스쿼드4"]
moris = spec.build_squad(list(row["members"]))
result = simulate(moris, config={"duration": 25.0, "rng_mode": "expected", **row.get("config", {})}, verbose=True)
print("char_totals", result.char_damage)
for attr in ("buff_events", "instant_events", "damage_events", "skill_events", "normal_events"):
    seq = getattr(result.log, attr, None)
    if seq is None:
        continue
    print(f"\nLOG {attr} count={len(seq)}")
    shown = 0
    for item in seq:
        text = repr(item)
        if "목단" in text or "정정당당" in text:
            print(text)
            shown += 1
            if shown >= 120:
                print("... truncated ...")
                break

for path in (
    "calculator/buff_manager.py",
    "calculator/timeline.py",
    "calculator/damage.py",
    "fast_engine/engine/compiler.py",
    "fast_engine/engine/dispatcher.py",
    "fast_engine/engine/score.py",
    "fast_engine/engine/weapon.py",
    "fast_engine/engine/weapon_runtime.py",
    "fast_engine/engine/normal_runtime.py",
    "fast_engine/engine/damage_runtime.py",
):
    grep_context(
        path,
        (
            "weapon_change",
            "weapon_override",
            "dynamic_weapon",
            "current_weapon",
            "self_state",
            "additional_damage",
            "hit_count",
        ),
        pad=2,
    )
