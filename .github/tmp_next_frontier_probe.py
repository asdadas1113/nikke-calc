from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

TEAM='레이드_네온벨벳'; ACTOR='벨벳'; MODE='깔끔한 마무리'; DURATION=32.0
moris=spec.build_squad(list(snapshot.SQUADS[TEAM]['members']))
squad=compile_moris_squad(moris)
idx=next(i for i,m in enumerate(squad.members) if m.name==ACTOR)
member=squad.members[idx]
mode=next(e for e in member.effects if e.name==MODE and e.effect_type=='weapon_change')
print('BLOCKERS',static_score_blockers(squad))
print('BASE',dict(member.weapon))
print('MODE',mode.effect_id,mode.duration,dict(mode.parameters),[(r.mode.value,r.event_key) for r in mode.triggers])
result=simulate(moris,config={'duration':DURATION,'rng_mode':'expected'},enemy=dict(DEFAULT_ENEMY),verbose=True)
casts=[x.t for x in result.log.burst_log if x.caster==ACTOR and 'stage:2 사용' in x.event]
print('CASTS',casts)
hits=[h for h in result.hits if h.caster==ACTOR and h.skill_name=='기본 공격']
ammo=[x for x in result.log.ammo_log if x.caster==ACTOR]
for cast in casts[:2]:
    expiry=cast+float(mode.duration)
    print('WINDOW',cast,'EXP',expiry)
    print(' HITS',[(h.t,h.hit_tag,h.damage) for h in hits if cast-1.5 <= h.t <= expiry+2.5])
    print(' AMMO',[(x.t,x.ammo) for x in ammo if cast-1.5 <= x.t <= expiry+2.5])
    print(' RELOAD',[(x.t,x.event) for x in result.log.reload_log if x.caster==ACTOR and cast-1.5 <= x.t <= expiry+2.5])
# Hit-count bonus boundaries in mode, useful to prove global count phase continuity.
print('BONUS',[(h.t,h.skill_name,h.hit_tag,h.damage) for h in result.hits if h.caster==ACTOR and h.skill_name=='사랑의 탄환 6'][:20])
