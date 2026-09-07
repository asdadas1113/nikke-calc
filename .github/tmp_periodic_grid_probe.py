from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import patch
from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
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
print('GRENADE',grenade.effect_id,grenade.name,grenade.stat,[(r.mode.value,r.interval,r.event_key) for r in grenade.triggers])
print('MODIFIER',modifier.effect_id,modifier.name,modifier.stat,modifier.value,modifier.duration,modifier.parameters)

duration=35.0
config={'duration':duration,'rng_mode':'expected'}
enemy=dict(DEFAULT_ENEMY)
policy=compile_burst_policy(moris,c,config)
enemy_profile=EnemyStaticProfile(defense=float(enemy.get('def',31784.0)),element=enemy.get('code'),core_px=float(enemy.get('core_px',0.0) or 0.0),duration=duration)

# Current Fast with a real score sink: fixed 2s grid, no effect_interval yet.
fast=[]
sink=SimpleDamageScoreSink(c,enemy_profile)
orig_fast=TriggerDispatcher.dispatch_periodic
def traced_fast(dispatcher,effect_id,rule_index,*,time,context):
    result=orig_fast(dispatcher,effect_id,rule_index,time=time,context=context)
    if effect_id==grenade.effect_id:
        fast.append((time,effect_id in result.activated_effect_ids))
    return result
with patch.object(TriggerDispatcher,'dispatch_periodic',new=traced_fast):
    BurstRuntime(c,policy,enemy_profile,damage_sink=sink).run(duration=duration)
print('FAST_GRENADE',fast)
print('FAST_GRENADE_DAMAGE',sink.char_total[ada])

# Moris activation boundary oracle. Periodic damage routes through _activate after
# every:Ns condition succeeds, so this captures exact grenade fire frames.
moris_grenade=[]
moris_modifier=[]
orig_activate=BuffManager._activate
def traced_activate(self,eff,caster,t,suppress_event=False):
    if caster=='에이다' and eff.get('name')=='섬광 수류탄 투척':
        moris_grenade.append(float(t))
    if caster=='에이다' and eff.get('name')=='섬광 수류탄 투척 발동 시간 조건':
        moris_modifier.append(float(t))
    return orig_activate(self,eff,caster,t,suppress_event=suppress_event)
with patch.object(BuffManager,'_activate',new=traced_activate):
    res=simulate(moris,config=config,enemy=enemy,verbose=True)
print('MORIS_GRENADE',moris_grenade)
print('MORIS_MODIFIER',moris_modifier)
print('MORIS_BURSTS',[(r.t,r.event,r.caster) for r in res.log.burst_log])

# Compile/runtime support sanity.
tmp_dispatcher=TriggerDispatcher(c, __import__('fast_engine.engine.state',fromlist=['StateStore']).StateStore.from_compiled_squad(c), enemy_profile, __import__('fast_engine.engine.burst',fromlist=['BurstMachine']).BurstMachine(c,policy), __import__('fast_engine.engine.scheduler',fromlist=['EventScheduler']).EventScheduler(), damage_sink=SimpleDamageScoreSink(c,enemy_profile))
print('GRENADE_CAN_ACTIVATE',tmp_dispatcher.can_activate_effect(grenade))
print('GRENADE_RUNTIME_EXEC',tmp_dispatcher.is_runtime_executable_effect(grenade))
print('MODIFIER_CAN_ACTIVATE',tmp_dispatcher.can_activate_effect(modifier))
print('MODIFIER_RUNTIME_EXEC',tmp_dispatcher.is_runtime_executable_effect(modifier))
