from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import patch
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers

TEAM='레이드_헬름아쿠아스노우'
moris=spec.build_squad(list(snapshot.SQUADS[TEAM]['members']))
c=compile_moris_squad(moris)
print('MEMBERS', [m.name for m in c.members])
print('BLOCKERS', static_score_blockers(c))
ada=next(i for i,m in enumerate(c.members) if m.name=='에이다')
grenade=next(e for e in c.members[ada].effects if e.name=='섬광 수류탄 투척')
modifier=next(e for e in c.members[ada].effects if (e.stat or '')=='effect_interval')
for e in c.effects:
    if (e.stat or '') == 'effect_interval' or any(getattr(r,'mode',None).value == 'periodic' for r in e.triggers):
        print('EFFECT', e.effect_id, c.members[e.actor].name, e.name, e.effect_type, e.stat, e.value, 'duration',e.duration,'max_stack',e.max_stack,'params',e.parameters,'target',e.target_spec.mode.value,'cap',e.capability.disposition.value,tuple(e.capability.blockers))
        for r in e.triggers:
            print('  TRIGGER', r.mode.value, r.event_key, r.interval, r.threshold, r.trigger_count_reducible)
        print('  COND', [(r.mode.value,r.key,r.value) for r in e.condition_rules])
print('SAFE PERIODICS')
for e in c.effects:
    safe=(TriggerDispatcher._periodic_permanent_self_direct_stack_shape_supported(e) or TriggerDispatcher._periodic_finite_self_crit_shape_supported(e) or TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(e))
    if safe:
        print('SAFE',e.effect_id,c.members[e.actor].name,e.name,e.stat,[r.interval for r in e.triggers])

duration=30.0
config={'duration':duration,'rng_mode':'expected'}
enemy=dict(DEFAULT_ENEMY)
policy=compile_burst_policy(moris,c,config)
fast=[]
orig=TriggerDispatcher.dispatch_periodic
def traced(dispatcher,effect_id,rule_index,*,time,context):
    result=orig(dispatcher,effect_id,rule_index,time=time,context=context)
    if effect_id==grenade.effect_id:
        fast.append((time,effect_id in result.activated_effect_ids, dispatcher.effects.has_stat(ada,'effect_interval',now=time)))
    return result
with patch.object(TriggerDispatcher,'dispatch_periodic',new=traced):
    BurstRuntime(c,policy,EnemyStaticProfile(defense=float(enemy.get('def',31784.0)),element=enemy.get('code'),core_px=float(enemy.get('core_px',0.0) or 0.0),duration=duration)).run(duration=duration)
print('FAST_GRENADE',fast)
res=simulate(moris,config=config,enemy=enemy,verbose=True)
print('MORIS_LOG_ATTRS', [x for x in dir(res.log) if not x.startswith('_')])
for attr in dir(res.log):
    if attr.startswith('_'): continue
    try: rows=getattr(res.log,attr)
    except Exception: continue
    if not isinstance(rows,(list,tuple)): continue
    hits=[row for row in rows if '섬광 수류탄' in repr(row) or '에이다' in repr(row)]
    if hits:
        print('MORIS',attr,len(hits))
        for row in hits[:80]: print(' ',repr(row))
print('MODIFIER_RUNTIME_EXEC',TriggerDispatcher(c, __import__('fast_engine.engine.state',fromlist=['StateStore']).StateStore.from_compiled_squad(c), EnemyStaticProfile(duration=1), __import__('fast_engine.engine.burst',fromlist=['BurstMachine']).BurstMachine(c,policy), __import__('fast_engine.engine.scheduler',fromlist=['EventScheduler']).EventScheduler()).is_runtime_executable_effect(modifier))
