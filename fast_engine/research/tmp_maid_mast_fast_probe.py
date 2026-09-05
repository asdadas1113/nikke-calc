from __future__ import annotations

from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.effects import ActiveEffectStore

TARGET='마스트 : 로망틱 메이드'

orig_activate=ActiveEffectStore.activate_group
orig_adjust=ActiveEffectStore.adjust_named_stack
orig_remove=ActiveEffectStore.remove_named_state

def act(self,effect,targets,now,scheduler,*args,**kwargs):
    if effect.name=='취기':
        before=[(t,self.named_stack(t,'취기',now=now)) for t in targets]
        out=orig_activate(self,effect,targets,now,scheduler,*args,**kwargs)
        after=[(t,self.named_stack(t,'취기',now=now)) for t in targets]
        print('FAST_ACT',round(float(now),9),effect.actor,effect.name,before,'->',after)
        return out
    return orig_activate(self,effect,targets,now,scheduler,*args,**kwargs)

def adj(self,target,name,delta,*args,**kwargs):
    now=kwargs.get('now',0.0)
    if name=='취기':
        print('FAST_ADJ_PRE',round(float(now),9),target,name,delta,self.named_stack(target,name,now=now))
    out=orig_adjust(self,target,name,delta,*args,**kwargs)
    if name=='취기':
        print('FAST_ADJ_POST',round(float(now),9),target,name,self.named_stack(target,name,now=now))
    return out

def rem(self,target,name,*args,**kwargs):
    now=kwargs.get('now',0.0)
    if name=='취기':
        print('FAST_REM_PRE',round(float(now),9),target,name,self.named_stack(target,name,now=now))
    out=orig_remove(self,target,name,*args,**kwargs)
    if name=='취기':
        print('FAST_REM_POST',round(float(now),9),target,name,self.named_stack(target,name,now=now),out)
    return out

ActiveEffectStore.activate_group=act
ActiveEffectStore.adjust_named_stack=adj
ActiveEffectStore.remove_named_state=rem

for label in ['스쿼드4','레이드_루주','레이드_볼륨','레이드_브리드디젤','레이드_앨리스브래디']:
    case=snapshot.SQUADS[label]
    moris=spec.build_squad(list(case['members']))
    compiled=compile_moris_squad(moris)
    cfg=dict(case.get('config',{})); cfg['duration']=42.0
    policy=compile_burst_policy(moris,compiled,cfg)
    runtime=BurstRuntime(compiled,policy)
    mast=compiled.names.index(TARGET)
    print('\n###',label,list(case['members']),'mast',mast)
    for e in compiled.effects:
        if e.actor==mast or 'stack' in (e.stat or ''):
            if e.name=='취기' or e.name.startswith('파이레츠') or e.name=='숙취' or 'stack' in (e.stat or ''):
                print('EFFECT',compiled.members[e.actor].name,e.name,e.stat,'target',e.target_spec.mode,'value',e.value,'max',e.max_stack,'triggers',[(r.mode.value,r.event_key,r.raw) for r in e.triggers],'conds',[(r.mode.value,r.key,r.value) for r in e.condition_rules],'params',dict(e.parameters),'can',runtime.dispatcher.can_activate_effect(e),'runtime_exec',runtime.dispatcher.is_runtime_executable_effect(e),'sink_state',runtime.damage_sink.supports_state_operation(e) if runtime.damage_sink else None)
    result=runtime.run(duration=42.0)
    print('FAST_BURSTS',result.full_burst_starts,result.full_burst_ends)
    print('FAST_CASTS',[(round(float(t),9),compiled.names[a],stage) for t,a,stage in result.casts])
    print('FAST_FINAL_DRUNK',runtime.dispatcher.effects.named_stack(mast,'취기',now=42.0),runtime.dispatcher.effects.has_named_state(mast,'취기',now=42.0))
