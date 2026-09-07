from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers, _charge_actor_score_safe
from fast_engine.engine.target_scope import possible_ally_targets

TEAMS = ('레이드_라피앨리스', '레이드_앨리스브래디')
DURATION = 70.0

for team in TEAMS:
    moris = spec.build_squad(list(snapshot.SQUADS[team]['members']))
    squad = compile_moris_squad(moris)
    alice = next(i for i,m in enumerate(squad.members) if m.name == '앨리스')
    carrot = next(e for e in squad.members[alice].effects if e.name == '힘나는 당근')
    carrot2 = next(e for e in squad.members[alice].effects if e.name == '힘나는 당근 2')
    print('TEAM', team)
    print('MEMBERS', [(i,m.name,m.weapon.get('weapon_type'),m.weapon.get('fire_mode'),m.base_atk,m.weapon.get('control')) for i,m in enumerate(squad.members)])
    print('BLOCKERS', static_score_blockers(squad))
    print('CARROT', carrot.effect_id, carrot.stat, carrot.value, carrot.duration, carrot.target_spec.raw)
    print('CARROT2', carrot2.effect_id, carrot2.stat, carrot2.value, carrot2.duration, carrot2.target_spec.raw)
    print('POSSIBLE', [(squad.members[i].name, _charge_actor_score_safe(squad,i)) for i in possible_ally_targets(squad,carrot)])

    resolutions=[]
    orig=BuffManager._resolve_target
    def traced(self, raw, caster, *args, **kwargs):
        result=orig(self,raw,caster,*args,**kwargs)
        if caster == '앨리스' and raw == 'allies_top_atk:2':
            resolutions.append((float(getattr(self,'_cur_t',-1.0)), raw, tuple(result)))
        return result
    with patch.object(BuffManager,'_resolve_target',new=traced):
        result=simulate(moris,config={'duration':DURATION,'rng_mode':'expected'},enemy=dict(DEFAULT_ENEMY),verbose=True)
    print('RESOLUTIONS')
    for row in resolutions: print(' ',row)
    if result.log:
        print('CARROT_EVENTS')
        for ev in result.log.buff_events:
            if ev.name in {'힘나는 당근','힘나는 당근 2'}:
                print(' ',ev.t,ev.kind,ev.name,ev.caster,'->',ev.target,'exp',ev.expires_at,'stat',ev.stat,'value',ev.value)
    print('ALICE_FULL_CHARGE_FIRST20', [h.t for h in result.hits if h.caster=='앨리스' and 'full_charge_hit' in h.hit_tag and h.skill_name=='기본 공격'][:20])
