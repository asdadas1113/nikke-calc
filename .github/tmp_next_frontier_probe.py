from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

CASES = (
    ('레이드_네온벨벳', '벨벳', '깔끔한 마무리'),
    ('레이드_작열짬', '모더니아', '섬멸 모드'),
)
DURATION=45.0

for team, actor_name, mode_name in CASES:
    moris=spec.build_squad(list(snapshot.SQUADS[team]['members']))
    squad=compile_moris_squad(moris)
    actor=next(i for i,m in enumerate(squad.members) if m.name==actor_name)
    member=squad.members[actor]
    mode=next(e for e in member.effects if e.name==mode_name and e.effect_type=='weapon_change')
    print('TEAM',team)
    print('MEMBERS',[(i,m.name,m.weapon.get('weapon_type'),m.weapon.get('fire_mode'),m.weapon.get('max_ammo'),m.weapon.get('control')) for i,m in enumerate(squad.members)])
    print('BLOCKERS',static_score_blockers(squad))
    print('BASE_WEAPON',dict(member.weapon))
    print('MODE',{
        'id':mode.effect_id,'type':mode.effect_type,'stat':mode.stat,'value':mode.value,'duration':mode.duration,
        'target':mode.target_spec.raw,'params':dict(mode.parameters),
        'triggers':[(r.mode.value,r.event_key,r.threshold,r.interval) for r in mode.triggers],
        'conditions':[(r.mode.value,r.key,r.value) for r in mode.condition_rules],
        'capability':(mode.capability.disposition.value,list(mode.capability.blockers)),
    })
    print('ACTOR_EFFECTS')
    for e in member.effects:
        print(' ',e.effect_id,e.name,e.effect_type,e.stat,e.value,e.duration,e.target_spec.raw,
              [(r.mode.value,r.event_key,r.threshold,r.interval) for r in e.triggers],
              [(r.mode.value,r.key,r.value) for r in e.condition_rules],dict(e.parameters),
              (e.capability.disposition.value,list(e.capability.blockers)))
    result=simulate(moris,config={'duration':DURATION,'rng_mode':'expected'},enemy=dict(DEFAULT_ENEMY),verbose=True)
    print('BURST_LOG',[(x.t,x.event,x.caster) for x in result.log.burst_log if x.caster==actor_name or not x.caster])
    print('MODE_BUFF_EVENTS',[(x.t,x.kind,x.name,x.target,x.expires_at,x.stat,x.value) for x in result.log.buff_events if x.name==mode_name])
    hits=[(h.t,h.skill_name,h.hit_tag,h.damage) for h in result.hits if h.caster==actor_name]
    print('HITS_FIRST60',hits[:60])
    print('RELOAD',[(x.t,x.event) for x in result.log.reload_log if x.caster==actor_name][:30])
    print('AMMO',[(x.t,x.ammo) for x in result.log.ammo_log if x.caster==actor_name][:80])
