from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from context import snapshot, spec
from calculator.timeline import simulate
from calculator.buff_manager import BuffManager
from fast_engine.engine.compiler import compile_moris_squad

team='레이드_아스카루드밀라'
row=snapshot.SQUADS[team]
moris=spec.build_squad(list(row['members']))
compiled=compile_moris_squad(moris)
print('TEAM', row['members'])

hp_stats={
    'heal_hp_pct','lifesteal_pct','current_hp_reduce','current_hp_restore_pct',
    'max_hp_pct','max_hp_only_pct','hp_caster_based_pct','hp_only_caster_based_pct',
    'hp_pct','hp_flat','hp_recovery_pct','heal_received_pct'
}
print('\nHP_RELEVANT_EFFECTS')
for e in compiled.effects:
    if (e.stat or '') in hp_stats or 'hp' in (e.stat or '').lower() or 'heal' in (e.stat or '').lower():
        print({
            'actor':compiled.members[e.actor].name,'name':e.name,'type':e.effect_type,'stat':e.stat,
            'value':e.value,'target':e.target,'duration':e.duration,'max_stack':e.max_stack,
            'params':dict(e.parameters),'conditions':tuple(repr(x) for x in e.condition_rules),
            'triggers':tuple(repr(x) for x in e.triggers),
        })

orig=BuffManager._resolve_target
seen=[]
def traced(self,target,caster):
    out=orig(self,target,caster)
    if isinstance(target,str) and target.startswith('allies_lowest_hp:'):
        row=(float(getattr(self,'_cur_t',0.0)),caster,target,tuple(out),dict(self.state.get('hp_pct',{})))
        if not seen or row[:4] != seen[-1][:4] or row[4] != seen[-1][4]:
            seen.append(row)
            if len(seen)<=30:
                print('LOWEST_RESOLVE',row)
    return out

with patch.object(BuffManager,'_resolve_target',new=traced):
    result=simulate(moris,config={'duration':20.0,'rng_mode':'expected'},verbose=True)

print('\nRESOLVE_COUNT',len(seen))
print('ROYAL4')
for x in result.log.buff_events:
    if x.name=='로얄 에타이어 4' and x.kind=='activate': print(vars(x))
print('NAGA_LOG_NOTE dynamic instant log falls back to caster before handler; do not use target field as semantic recipient')
