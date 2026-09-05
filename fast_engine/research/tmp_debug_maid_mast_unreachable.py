from __future__ import annotations

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.score import _full_burst_end_stack_condition_unreachable_after_owned_decrement

for label in ('스쿼드4','레이드_앨리스브래디','레이드_볼륨'):
    compiled=compile_moris_squad(spec.build_squad(list(snapshot.SQUADS[label]['members'])))
    mast=compiled.names.index('마스트 : 로망틱 메이드')
    remover=next(e for e in compiled.members[mast].effects if e.name=='파이레츠 스피릿 3')
    hangover=next(e for e in compiled.members[mast].effects if e.name=='숙취')
    print('\n###',label)
    print('PROOF remover',_full_burst_end_stack_condition_unreachable_after_owned_decrement(compiled,remover))
    print('PROOF hangover',_full_burst_end_stack_condition_unreachable_after_owned_decrement(compiled,hangover))
    provider=next(e for e in compiled.members[mast].effects if e.name=='취기')
    for e in compiled.effects:
        stat=e.stat or ''
        if (stat.startswith('burst_stage_override:reenter') or stat in {'remove_named_buff','buff_stack_add','buff_stack_remove','debuff_stack_add','debuff_stack_remove'}):
            print('MUT',compiled.members[e.actor].name,e.name,stat,'params',dict(e.parameters),'triggers',[(r.mode.value,r.event_key,r.threshold,r.raw) for r in e.triggers],'conds',[(r.mode.value,r.key,r.value) for r in e.condition_rules], 'owned_generic', TriggerDispatcher._generic_allies_harmful_stack_decrement_provider(compiled,e) is provider)
