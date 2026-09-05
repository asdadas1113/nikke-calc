from __future__ import annotations

import calculator.buff_manager as bm
from calculator.timeline import simulate
from context import snapshot, spec

TARGET='마스트 : 로망틱 메이드'
Orig=bm.BuffManager.notify

def traced(self,event,t,caster,*args,**kwargs):
    if event in {'burst_enter:1','full_burst_start','full_burst_end'}:
        rows=[]
        for ab in self._active:
            if ab.effect.get('name')=='취기' and ab.caster==TARGET:
                rows.append((ab.stack,ab.expires_at,id(ab)))
        print('NOTIFY_PRE',round(float(t),9),event,caster,'취기',rows)
    out=Orig(self,event,t,caster,*args,**kwargs)
    if event in {'burst_enter:1','full_burst_start','full_burst_end'}:
        rows=[]
        for ab in self._active:
            if ab.effect.get('name')=='취기' and ab.caster==TARGET:
                rows.append((ab.stack,ab.expires_at,id(ab)))
        print('NOTIFY_POST',round(float(t),9),event,caster,'취기',rows)
    return out

bm.BuffManager.notify=traced

for label in ['스쿼드4','레이드_루주','레이드_볼륨','레이드_브리드디젤']:
    case=snapshot.SQUADS[label]
    squad=spec.build_squad(list(case['members']))
    print('\n###',label,list(case['members']))
    for ch in squad:
        for eff in bm.char_effects(ch['name'], ch.get('favorite_stage')):
            text=str(eff)
            if ('burst_enter:1' in text or 'burst_reenter' in text or 'burst_stage_override' in text or
                ('취기' in text and ch['name']!=TARGET)):
                print('RELATED',ch['name'],eff)
    cfg=dict(case.get('config',{})); cfg.update({'duration':42.0,'rng_mode':'expected'})
    result=simulate(squad,config=cfg,seed=42,verbose=True)
    print('BURSTS',[(round(float(e.t),9),e.event,e.caster) for e in result.log.burst_log])
    print('DRUNK',[(round(float(e.t),9),e.kind,e.stack,e.value) for e in result.log.buff_events if e.name=='취기'])
    inst=getattr(result.log,'instant_events',[]) or []
    print('INSTANT_DRUNK',[(round(float(e.t),9),getattr(e,'name',''),getattr(e,'stat',''),getattr(e,'value',None)) for e in inst if '취기' in str(vars(e) if hasattr(e,'__dict__') else e) or '파이레츠 스피릿 3' in str(vars(e) if hasattr(e,'__dict__') else e)])
