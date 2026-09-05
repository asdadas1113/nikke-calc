from __future__ import annotations

from collections import Counter

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

ANCHOR = '앵커 : 이노센트 메이드'
MAID = '마스트 : 로망틱 메이드'
REMOVE = 'normal_state:마스트 : 로망틱 메이드:파이레츠 스피릿 3:remove_named_buff'
GENERIC = 'normal_state:앵커 : 이노센트 메이드:불가사리(모양) 오므라이스 3:debuff_stack_remove'
ANCHOR_LABELS = {'스쿼드4', '레이드_앨리스브래디', '레이드_볼륨'}
NO_ANCHOR_LABELS = {'레이드_루주', '레이드_브리드디젤'}

source=[]
for label,cfg in snapshot.SQUADS.items():
    label=str(label)
    if label.startswith('지그_'):
        continue
    members=tuple(str(m) for m in cfg['members'])
    if len(members)!=5 or any(m.startswith('test_') for m in members):
        continue
    source.append((label,members))

unique=[]; seen=set()
for label,members in source:
    if members in seen:
        continue
    seen.add(members); unique.append((label,members))

families=Counter(); certified=[]; gaps=[]; maid_rows=[]
for label,members in unique:
    compiled=compile_moris_squad(spec.build_squad(list(members)))
    blockers=tuple(static_score_blockers(compiled))
    families.update(row.split(':',1)[0] for row in blockers)
    if blockers: gaps.append(label)
    else: certified.append(label)
    if MAID in members:
        maid_rows.append((label,ANCHOR in members,blockers))

print('PROMOTION_SOURCE_CASES',len(source))
print('PROMOTION_UNIQUE_MEMBERSHIPS',len(unique))
print('PROMOTION_CERTIFIED',len(certified),certified)
print('PROMOTION_GAPS',len(gaps))
print('PROMOTION_BLOCKERS',dict(sorted(families.items())))
print('PROMOTION_MAID_ROWS',maid_rows)

assert len(source)==24, len(source)
assert len(unique)==23, len(unique)
assert certified==['레이드_레드후드퀀시','컨트롤_미란다미하라'], certified
assert len(gaps)==21, gaps
assert dict(sorted(families.items()))=={
    'cadence':59,
    'control':4,
    'normal_delivery':47,
    'normal_state':27,
    'periodic_grid':1,
    'skill_damage':27,
    'skill_state_delivery':49,
    'weapon_change':12,
}, dict(sorted(families.items()))
assert {label for label,_,_ in maid_rows} == ANCHOR_LABELS | NO_ANCHOR_LABELS
for label,has_anchor,blockers in maid_rows:
    rows=set(blockers)
    if label in ANCHOR_LABELS:
        assert has_anchor
        assert REMOVE not in rows, (label,blockers)
        assert GENERIC not in rows, (label,blockers)
    else:
        assert label in NO_ANCHOR_LABELS and not has_anchor
        assert REMOVE in rows, (label,blockers)
print('PROMOTION_ASSERTIONS_OK')
