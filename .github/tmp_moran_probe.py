from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

for team in ("스쿼드2", "레이드_아니스서머메이든", "레이드_라피앨리스", "레이드_트리나홍련"):
    members = list(snapshot.SQUADS[team]["members"])
    compiled = compile_moris_squad(spec.build_squad(members))
    print("TEAM", team, tuple(m.name for m in compiled.members), flush=True)
    print("BLOCKERS", tuple(b for b in static_score_blockers(compiled) if "프리바티:" in b), flush=True)
    actor = next(i for i, m in enumerate(compiled.members) if m.name == "프리바티")
    for effect in compiled.members[actor].effects:
        if effect.name and effect.name.startswith("EX 매거진"):
            print("EFFECT", effect.effect_id, effect.name, flush=True)
            print(" type", effect.effect_type, "stat", effect.stat, "target", effect.target_spec, flush=True)
            print(" value", effect.value, "duration", effect.duration, "max_stack", effect.max_stack, "max_trigger", effect.max_trigger, flush=True)
            print(" polarity", effect.polarity, "parameters", effect.parameters, flush=True)
            print(" conditions", [(r.mode.value, r.key, r.value, r.raw) for r in effect.condition_rules], flush=True)
            print(" triggers", [(r.mode.value, r.event_key, r.threshold, r.trigger_count_reducible, r.raw) for r in effect.triggers], flush=True)
            print(" capability", effect.capability.disposition.value, flush=True)
