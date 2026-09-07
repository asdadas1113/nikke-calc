from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot
from context.spec import build_config, build_squad
from calculator.timeline import simulate
from calculator.sim_result import _is_normal

TEAMS=("스쿼드2","레이드_네온벨벳","레이드_소다")
for team in TEAMS:
    case=snapshot.SQUADS[team]
    members=list(case["members"])
    squad=build_squad(members)
    cfg=build_config(squad,{"duration":30.0,"first_burst_time":3.0})
    result=simulate(
        squad,
        config=cfg,
        enemy={"def":0,"code":"","core_px":0,"has_parts":False},
        seed=42,
        verbose=True,
    )
    print("\n===",team,tuple(members),flush=True)
    print("BURSTS",[(round(e.t,6),e.event,e.caster) for e in result.log.burst_log if e.t < 20],flush=True)
    hits=[h for h in result.hits if h.caster=="나유타" and h.t < 20]
    print("NAYUTA_HITS",[(round(h.t,6),h.skill_name,h.hit_tag,h.damage,_is_normal(h)) for h in hits],flush=True)
    mode=[h for h in hits if h.skill_name=="기억 연소"]
    print("MODE_TIMES",[round(h.t,6) for h in mode],flush=True)
    print("MODE_MAIN",[(round(h.t,6),h.damage,h.hit_tag) for h in mode],flush=True)
    derived=[h for h in hits if h.skill_name in {"위선 5","위선 6"}]
    print("MODE_DERIVED",[(round(h.t,6),h.skill_name,h.damage,h.hit_tag) for h in derived],flush=True)
    print("AMMO",[(round(e.t,6),e.ammo) for e in result.log.ammo_log if e.caster=="나유타" and e.t < 20],flush=True)
    print("RELOAD",[(round(e.t,6),e.event) for e in result.log.reload_log if e.caster=="나유타" and e.t < 20],flush=True)
    print("TOTAL",result.char_total.get("나유타"),flush=True)
