from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from context import snapshot,spec
from fast_engine.engine.compiler import compile_moris_squad
import fast_engine.engine.score as s

for name,case in snapshot.SQUADS.items():
    members=tuple(case['members'])
    if '프리바티' not in members: continue
    compiled=compile_moris_squad(spec.build_squad(list(members)))
    print('\nTEAM',name,members,flush=True)
    for i,m in enumerate(compiled.members):
        print('ACTOR',i,m.name,'mode',m.weapon.get('fire_mode'),'clip',bool(m.weapon.get('is_clip')),'cover',bool(m.weapon.get('cover_during_delay')),'upper',s._reload_speed_positive_upper_bound(compiled,i),'rapid_safe',s._rapid_actor_score_safe(compiled,i) if m.weapon.get('fire_mode') in {'auto','auto_warmup'} else None,'charge_safe',s._charge_actor_score_safe(compiled,i) if m.weapon.get('fire_mode')=='charge' else None,flush=True)
    for e in compiled.effects:
        if e.actor==members.index('프리바티') and e.name in {'EX 매거진 2','EX 매거진 3'}:
            print('EFFECT',e.effect_id,e.name,e.stat,'reload_support',s._is_dynamic_reload_score_supported(compiled,e),'max_support',s._is_dynamic_max_ammo_score_supported(compiled,e),'targets',s._possible_ally_targets(compiled,e),flush=True)
