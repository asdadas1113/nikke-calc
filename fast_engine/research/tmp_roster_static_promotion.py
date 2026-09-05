from __future__ import annotations

from collections import Counter

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

source = []
for label, cfg in snapshot.SQUADS.items():
    if str(label).startswith('지그_'):
        continue
    members = tuple(str(m) for m in cfg['members'])
    if len(members) != 5 or any(m.startswith('test_') for m in members):
        continue
    source.append((str(label), members))

unique = []
seen = set()
for label, members in source:
    if members in seen:
        continue
    seen.add(members)
    unique.append((label, members))

certified = []
gaps = []
families = Counter()
anis_rows = []
for label, members in unique:
    compiled = compile_moris_squad(spec.build_squad(list(members)))
    blockers = tuple(static_score_blockers(compiled))
    if blockers:
        gaps.append(label)
    else:
        certified.append(label)
    families.update(row.split(':', 1)[0] for row in blockers)
    if '아니스 : 스타' in members:
        anis_rows.append((label, blockers))

print('PROMOTION_SOURCE_CASES', len(source))
print('PROMOTION_UNIQUE_MEMBERSHIPS', len(unique))
print('PROMOTION_CERTIFIED', len(certified), certified)
print('PROMOTION_GAPS', len(gaps))
print('PROMOTION_BLOCKERS', dict(sorted(families.items())))
print('PROMOTION_ANIS_ROWS', anis_rows)

assert len(source) == 24, len(source)
assert len(unique) == 23, len(unique)
assert certified == ['레이드_레드후드퀀시', '컨트롤_미란다미하라'], certified
assert len(gaps) == 21, len(gaps)
assert dict(sorted(families.items())) == {
    'cadence': 59,
    'control': 4,
    'normal_delivery': 47,
    'normal_state': 30,
    'periodic_grid': 1,
    'skill_damage': 27,
    'skill_state_delivery': 49,
    'weapon_change': 12,
}, dict(sorted(families.items()))
assert {label for label, _ in anis_rows} == {'스쿼드5', '레이드_앨리스브래디', '레이드_일레그'}
for label, blockers in anis_rows:
    assert 'normal_state:아니스 : 스타:스타 폴 4:remove_named_buff' not in blockers, (label, blockers)
    assert 'cadence:아니스 : 스타:슈팅 스타2:charge_time_fixed' in blockers, (label, blockers)
    assert 'skill_damage:아니스 : 스타:슈팅 스타1:auto_damage' in blockers, (label, blockers)
    assert 'skill_state_delivery:아니스 : 스타:스타더스트 3:projectile_explosion_dmg_pct' in blockers, (label, blockers)
