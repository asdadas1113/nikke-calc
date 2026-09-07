from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.research.public_ranking_probe import _source_corpus

members = next(m for m, label in _source_corpus() if label == '레이드_네온벨벳')
squad = spec.build_squad(list(members))
config = spec.build_config(squad, {
    'duration': 30.0,
    'first_burst_time': 3.0,
    'rng_mode': 'expected',
})
result = simulate(squad, config=config, enemy=dict(DEFAULT_ENEMY), verbose=True, seed=42)
log = result.log
assert log is not None

print('MEMBERS', members)
print('BURST_LOG')
for row in log.burst_log:
    print(row.t, row.event, row.caster)

mode_events = [e for e in log.buff_events if e.name in {'깔끔한 마무리', '깔끔한 마무리 2'} and e.caster == '벨벳']
print('MODE_EVENTS')
for e in mode_events:
    print(e.t, e.kind, e.name, e.target, e.expires_at, e.stat, e.value)

velvet_hits = [e for e in result.hits if e.caster == '벨벳']
base = [e for e in velvet_hits if e.skill_name == '기본 공격' and 'full_charge_hit' in e.hit_tag]
mg = [e for e in velvet_hits if e.skill_name == '기본 공격' and 'full_charge_hit' not in e.hit_tag]
print('BASE_SR_HITS', [(e.t,e.hit_tag,e.damage) for e in base])
print('MG_COUNT', len(mg))
print('MG_FIRST_LAST', [(e.t,e.hit_tag) for e in mg[:12]], [(e.t,e.hit_tag) for e in mg[-12:]])

activations = [e for e in mode_events if e.kind == 'activate' and e.name == '깔끔한 마무리 2']
for i,a in enumerate(activations,1):
    t0=float(a.t); t1=float(a.expires_at)
    rows=[e for e in mg if t0-1e-9 <= e.t < t1-1e-9]
    print('MODE_INTERVAL',i,t0,t1,'MG_SHOTS',len(rows),'FIRST',[(e.t,e.hit_tag) for e in rows[:8]],'LAST',[(e.t,e.hit_tag) for e in rows[-8:]])

print('HIT50_SKILL_HITS')
for e in velvet_hits:
    if e.skill_name != '기본 공격':
        print(e.t, e.skill_name, e.hit_tag, e.damage)

print('RELEVANT_BUFF_EVENTS')
for e in log.buff_events:
    if e.caster == '벨벳' and any(key in e.name for key in ('사랑의 탄환','나쁜 손버릇','깔끔한 마무리')):
        print(e.t,e.kind,e.name,e.target,e.expires_at,e.stat,e.value,e.stack)

print('VELVET_AMMO_AROUND_EDGES')
edges=[]
for a in activations:
    edges.extend([float(a.t), float(a.expires_at)])
for e in log.ammo_log:
    if e.caster == '벨벳' and any(abs(e.t-edge) <= 0.12 for edge in edges):
        print(e.t,e.ammo)
