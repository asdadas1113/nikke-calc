from __future__ import annotations

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.target_scope import possible_ally_targets

ANCHOR='앵커 : 이노센트 메이드'

for label,cfg in snapshot.SQUADS.items():
    if str(label).startswith('지그_'):
        continue
    members=tuple(str(m) for m in cfg['members'])
    if len(members)!=5 or ANCHOR not in members or any(m.startswith('test_') for m in members):
        continue
    compiled=compile_moris_squad(spec.build_squad(list(members)))
    mutators=[e for e in compiled.effects if compiled.members[e.actor].name==ANCHOR and (e.stat or '')=='debuff_stack_remove']
    print('\n###',label,members)
    for m in mutators:
        print('MUTATOR',m.name,m.value,m.target_spec.mode,m.polarity,[(r.mode.value,r.event_key,r.threshold,r.raw) for r in m.triggers],dict(m.parameters),[ (r.mode.value,r.key,r.value) for r in m.condition_rules],possible_ally_targets(compiled,m))
    for e in compiled.effects:
        maxs=e.max_stack
        if e.effect_type!='buff' or not (e.polarity or '').startswith('harmful') or maxs is None or float(maxs)<=1:
            continue
        targets=possible_ally_targets(compiled,e)
        if not targets:
            continue
        print('HARMFUL_STACK',compiled.members[e.actor].name,e.name,e.stat,'value',e.value,'max',e.max_stack,'target',e.target_spec.mode,'targets',targets,'duration',e.duration,'triggers',[(r.mode.value,r.event_key,r.threshold,r.raw) for r in e.triggers],'conds',[(r.mode.value,r.key,r.value) for r in e.condition_rules],'params',dict(e.parameters))
