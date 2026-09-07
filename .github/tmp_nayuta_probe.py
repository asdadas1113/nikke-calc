from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print("=== SOURCE MATCHES ===", flush=True)
needles = ("skill_damage", "weapon_change", "full_charge_hit")
for base in (ROOT / "calculator", ROOT / "fast_engine" / "engine"):
    for path in sorted(base.rglob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for idx, line in enumerate(lines):
            if any(n in line for n in needles):
                lo=max(0,idx-3); hi=min(len(lines),idx+5)
                print(f"--- {path.relative_to(ROOT)}:{idx+1}", flush=True)
                for j in range(lo,hi): print(f"{j+1}: {lines[j]}", flush=True)

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

print("=== STATIC NAYUTA ===", flush=True)
for team in ("스쿼드2", "레이드_네온벨벳", "레이드_소다"):
    case=snapshot.SQUADS[team]
    compiled=compile_moris_squad(spec.build_squad(list(case["members"])))
    nayuta=next(i for i,m in enumerate(compiled.members) if m.name=="나유타")
    wc=next(e for e in compiled.members[nayuta].effects if e.name=="기억 연소")
    print(team, "actor", nayuta, "base", compiled.members[nayuta].weapon, "wc", wc.parameters, "blockers", tuple(b for b in static_score_blockers(compiled) if ":나유타:" in b), flush=True)
