from pathlib import Path

CHECKPOINT = Path('fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md')
HANDOFF = Path('fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md')

CHECKPOINT.write_text(r'''# Fast Engine false-supported 안전성 봉합 체크포인트 — 2026-09-06

## 1. 목적

2026-09-05 독립 감사에서 Fast가 실제로 소유하지 않은 Moris 의미론을 일부 입력에서 `blockers=[]`, `unsupported=[]` 상태로 통과시키는 false-supported 구조가 확인됐다.

이 체크포인트의 목적은 coverage를 늘리는 것이 아니라 다음 invariant를 복구하는 것이다.

> Fast가 Moris 의미론을 소유하지 못한 comparison-critical 입력은 숫자를 내지 않는다.

감사의 synthetic 오차율은 구조 재현용이다. 아래 public blocker 증가는 해당 public team이 synthetic case와 같은 크기의 실제 오차를 냈다는 뜻이 아니다. public 영향은 reachability와 blocker surface를 별도로 판단한다.

## 2. 감사에서 확인된 6개 구조 문제

1. reference-stack scaling (`scaling: stack_count` / `scaling_ref`)을 계산하지 않고 direct state로 통과
2. generic permanent conditional passive (`during_full_burst`)가 상태 전환 없이 통과
3. unsupported state mutator가 comparison-critical producer를 바꿔도 조용히 skip 가능
4. dynamic ATK-rank target을 Moris보다 일찍 확정
5. `allies_burst3` prefix가 persona suffix selector까지 과매칭
6. same-timestamp actor transaction을 모든 static shot 선소비로 flatten

감사 synthetic A/B에서는 ranking inversion까지 재현됐지만, 이는 current public team의 실제 inversion 증거로 사용하지 않는다.

## 3. 완료된 안전성 봉합

### 3.1 canonical CI discovery 완전성

canonical CI가 explicit shard만 실행하지 않고 `fast_engine/tests/test_*.py` 전체 discovery를 반드시 실행하도록 보강했다. 이후 false-supported 회귀가 새 파일로 추가돼도 canonical gate에서 누락되지 않는다.

### 3.2 exact target grammar

`allies_burst3`만 exact 지원하며 `allies_burst3_persona_excl_self` 같은 미소유 semantic suffix는 `UNSUPPORTED`로 fail closed한다. persona 의미론 자체를 구현한 것은 아니다.

### 3.3 reference-stack scaling

Fast가 아직 capture semantics를 소유하지 않는 `scaling == stack_count` 또는 `scaling_ref` comparison-critical state를 fail closed한다. 이 과정에서 Maid Mast reference-stack provider를 전제로 했던 Brady stat-applied 인증도 철회됐다.

### 3.4 generic conditional permanent passive

Fast가 transition ownership을 갖지 않은 `during_full_burst` permanent direct passive는 fail closed한다. Dorothy Serendipity `광익 2/3`가 실제 public blocker surface로 드러났다.

### 3.5 scored-state remover dependency

production:

- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — `Fast: fail closed on scored-state removers`

unsupported `remove_named_buff`를 무조건 팀 전체 blocker로 만들지 않는다. Fast가 실제 score에 사용하는 named state를 해당 remover가 변경할 수 있을 때만 막는다. marker-only removal과 이미 소유한 specialized remover path는 그대로 허용한다.

Little Mermaid `터진 거품 3`처럼 Fast가 사용하는 `received_dmg_pct` state를 제거하는 실제 public dependency가 새 blocker로 드러났다.

### 3.6 unsafe dynamic rank target timing

production:

- `aadfde37ad7be708f6b3d3312ff828844a8a391a` — `Fast: fail closed on unsafe rank target timing`

`컨트롤_미란다미하라`에서 Miranda `파워 업!` / `파워 업! 2`의 `allies_top_atk_excl:*` 선택과 같은 `burst_cast` timestamp에 Brid `풀 마스콘`, Rouge `더 게임 마스터` ATK mutation이 실제 존재한다.

Fast는 아직 Moris의 lazy rank resolution transaction을 소유하지 않으므로 해당 team 인증을 철회했다.

대표 blockers:

- `normal_state:미란다:파워 업!:rank_target_timing`
- `normal_state:미란다:파워 업! 2:rank_target_timing`

### 3.7 same-timestamp cross-actor post-shot ordering

production:

- `438eef65426d1ed9e17b871db7cd74e334c8e921` — `Fast: fail closed on cross-actor post-shot ordering`

Moris는 같은 frame에서 actor 순서대로 shot → trigger/state mutation을 진행하므로 앞 actor의 post-shot buff가 뒤 actor의 같은-frame shot에 영향을 줄 수 있다. Fast static observer는 현재 `TRIGGER_BOUNDARY` 전에 모든 static actor의 timestamp `t` shot을 먼저 소비하므로 이 transaction을 flatten한다.

현재 guard는 global 60 Hz/per-shot Moris loop를 추가하지 않는다. post-shot direct score buff가 실제로 뒤 actor 또는 enemy state를 통해 뒤 actor에게 영향을 줄 수 있는 경우만 fail closed한다. self-only/earlier-only target은 이 blocker를 받지 않는다.

기존 마지막 certified team `레이드_레드후드퀀시`에서도 1.0 s에 Red Hood / Frika / Mint full-charge shot이 겹치며 Frika actor 2의 `full_charge_hit` all-allies buffs가 뒤 actor shot에 영향을 줄 수 있어 실제 public reachability가 확인됐다.

현재 RHQ blockers:

- `normal_state:프리카:무대, 시작할게.:same_timestamp_actor_order`
- `normal_state:프리카:무대, 시작할게. 2:same_timestamp_actor_order`
- `normal_state:프리카:무대, 시작할게. 3:same_timestamp_actor_order`
- `normal_state:민트:보컬 효과:same_timestamp_actor_order`

Quency의 self-only hit-count buff는 이 ordering blocker를 받지 않음을 회귀로 고정했다.

## 4. 현재 public frontier

`438eef65426d1ed9e17b871db7cd74e334c8e921` 기준 fresh frontier:

- source cases: 24
- unique ordered memberships: 23
- certified: **0**
- coverage gaps: **23**

blocker family counts:

- `normal_state`: 76
- `normal_delivery`: 55
- `skill_state_delivery`: 62
- `skill_damage`: 27
- `cadence`: 62
- `weapon_change`: 12
- `control`: 4
- `periodic_grid`: 1

기존 certified progression:

- 감사 전: 2 (`컨트롤_미란다미하라`, `레이드_레드후드퀀시`)
- rank timing fail-closed 후: 1 (`레이드_레드후드퀀시`)
- same-timestamp ordering fail-closed 후: 0

이는 engine 계산 성능이 나빠진 것이 아니라 certification contract를 보수적으로 정상화한 결과다. 현재 certified universe가 비었으므로 과거 `2-team` pairwise/top-N ranking metric은 현재 production certification의 품질 지표로 재사용하지 않는다.

## 5. 검증

same-timestamp production promotion run:

- workflow run: `33977615285`
- job: `101336989277`
- focused repaired regressions: success
- full Fast discovery: **277 tests / 277 pass**
- public frontier assertion: `23 unique / 0 certified`
- performance contract fixture: blocker-safe real 5-person fixture로 교체
  - `라피 / 델타 / 프로덕트 12 / iDoll 오션 / iDoll 썬`
  - 180 s Moris normal parity probe: max individual relative error 약 `0.718%`, team 약 `0.181%`
  - Fast 180 s median 약 `178.55 ms`, events `539`

테스트 임계값을 느슨하게 하지 않았다. 기존 1% parity contract를 만족하는 blocker-safe fixture를 새로 선정했다.

## 6. 다음 구현 우선순위

coverage blocker를 단순 제거하는 단계로 바로 복귀하지 않는다. 다음은 fail-closed를 다시 실제 semantics ownership으로 바꾸는 단계다.

1. **sparse same-timestamp actor transaction**
   - global 60 Hz loop 없이 의미 있는 timestamp에서만 actor order를 분할한다.
   - RHQ certification 복구에 직접 연결될 가능성이 가장 높다.
2. **lazy dynamic-rank resolution / same-event cohort semantics**
   - Miranda surface 복구 후보.
3. **finite reference-stack capture semantics**
   - Maid Mast / Tove / Arcana 등 실제 public surface.
4. **generic full-burst conditional permanent passive transition**
   - Dorothy Serendipity surface.
5. **producer/mutator dependency ownership 확장**
   - 현재 narrow `remove_named_buff` safety guard를 실제 state-operation semantics로 점진 교체.

`레이드_볼륨`의 Scarlet `ammo_charge_pct` 마지막 visible blocker를 먼저 여는 것은 계속 보류한다. Maid Mast reference-stack semantics가 아직 fail-closed이므로 Scarlet blocker만 제거하면 거짓 인증 위험이 다시 생긴다.

## 7. 작업공간 상태

- 작업 브랜치: `fast-engine-phase2-20260901`
- latest semantic: `438eef65426d1ed9e17b871db7cd74e334c8e921`
- `master`: 수정/병합하지 않음
- temporary workflow: 정리 완료
- `.github/workflows`: `ci.yml`, `pages.yml`만 유지

다음 재개점은 **sparse same-timestamp actor transaction semantics 설계/검증**이다.
''', encoding='utf-8')

t = HANDOFF.read_text(encoding='utf-8')

old = """1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`\n2. `fast_engine/research/CHARGE_RELOAD_CANCEL_CONTROL_CHECKPOINT_20260905.md`\n"""
new = """1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`\n2. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`\n3. `fast_engine/research/CHARGE_RELOAD_CANCEL_CONTROL_CHECKPOINT_20260905.md`\n"""
if t.count(old) != 1:
    raise SystemExit('handoff reading-order anchor changed')
t = t.replace(old, new, 1)

old = """현재 최신 production semantic commit:\n\n- `1902a71a4283528f3bea009ee4d3af6aba476a13` — pure charge `reload.cancel_on_full` ownership\n\n직전 production semantic commit:\n\n- `745d9f1afcf10d092bb58bf9e0235724a5c41946` — patternless `squad_part_hit` blocker hygiene\n\n직전 주요 semantic commit:\n\n- `37a7da91974222ab49bb0ef6b869d06a34100a4d` — post-shot `full_charge_hit` next-bullet lifetime delivery\n"""
new = """현재 최신 production semantic commit:\n\n- `438eef65426d1ed9e17b871db7cd74e334c8e921` — cross-actor post-shot same-timestamp ordering fail-closed\n\n직전 safety production commits:\n\n- `aadfde37ad7be708f6b3d3312ff828844a8a391a` — unsafe dynamic-rank target timing fail-closed\n- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — comparison-critical scored-state remover dependency fail-closed\n\n직전 coverage production semantic commits:\n\n- `1902a71a4283528f3bea009ee4d3af6aba476a13` — pure charge `reload.cancel_on_full` ownership\n- `745d9f1afcf10d092bb58bf9e0235724a5c41946` — patternless `squad_part_hit` blocker hygiene\n- `37a7da91974222ab49bb0ef6b869d06a34100a4d` — post-shot `full_charge_hit` next-bullet lifetime delivery\n"""
if t.count(old) != 1:
    raise SystemExit('handoff semantic anchor changed')
t = t.replace(old, new, 1)

old = """## 1. 현재 phase / public accounting\n\n현재는 **coverage expansion** 단계다.\n\nFast-certified real public memberships:\n\n- `컨트롤_미란다미하라`\n- `레이드_레드후드퀀시`\n\n표준 public accounting:\n\n- source cases: `24`\n- unique ordered memberships: `23`\n- certified: `2`\n- coverage gaps: `21`\n\nlatest standardized public ranking은 Helm periodic enemy candidate gate에서 실제 재실행했고 certified universe는 여전히 2개다.\n\n- clean relative error median: `+0.0626832%`\n- min: `+0.0349533%`\n- max: `+0.0904131%`\n- pairwise accuracy: `1.0`\n- top-N recall: `1.0`\n\nHelm periodic enemy gate run `33932690769`에서 ranking probe를 재실행했고 certified universe는 이후에도 2개로 유지됐다. 최신 fresh frontier는 cadence `59`, normal delivery `41`, skill-state delivery `43`, skill damage `27`, weapon change `12`, normal state `7`, control `4`, periodic grid `1`이다.\n\noptimizer production integration은 아직 하지 않는다.\n"""
new = """## 1. 현재 phase / public accounting\n\n현재는 **false-supported safety closure 이후 semantics restoration** 단계다. raw coverage expansion은 일시 중단한다.\n\nFast-certified real public memberships:\n\n- 현재 **없음**\n\n표준 public accounting (`438eef65426d1ed9e17b871db7cd74e334c8e921`):\n\n- source cases: `24`\n- unique ordered memberships: `23`\n- certified: `0`\n- coverage gaps: `23`\n\n현재 fresh blocker families:\n\n- normal state `76`\n- normal delivery `55`\n- skill-state delivery `62`\n- skill damage `27`\n- cadence `62`\n- weapon change `12`\n- control `4`\n- periodic grid `1`\n\n감사 전 certified 2개 중 `컨트롤_미란다미하라`는 lazy rank timing 미소유로, `레이드_레드후드퀀시`는 same-timestamp cross-actor post-shot ordering 미소유로 인증을 철회했다. 이는 synthetic error magnitude를 public team에 전이한 판정이 아니라, 실제 public reachability가 있는 미소유 semantics를 fail-closed한 것이다.\n\ncertified universe가 비어 있으므로 과거 2-team relative error / pairwise / top-N 수치는 현재 production certification metric으로 사용하지 않는다.\n\n다음 단일 우선순위는 global frame loop 없이 의미 있는 timestamp에서만 actor order를 보존하는 **sparse same-timestamp actor transaction** semantics다. 그 다음 lazy rank, reference-stack capture, generic full-burst conditional passive 순으로 복구한다.\n\n`레이드_볼륨`의 Scarlet ammo blocker 제거는 Maid Mast reference-stack semantics 소유 전까지 보류한다. optimizer production integration도 아직 하지 않는다.\n\n상세: `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`\n"""
if t.count(old) != 1:
    raise SystemExit('handoff phase/accounting anchor changed')
t = t.replace(old, new, 1)
HANDOFF.write_text(t, encoding='utf-8')

# Remove temporary recorder artifacts in the same commit that records the docs.
for name in (
    '.github/workflows/tmp-record-false-supported-safety-checkpoint.yml',
    '.github/workflows/tmp-run-false-supported-safety-recorder.yml',
    '.tmp_record_false_supported_safety_checkpoint.py',
):
    Path(name).unlink(missing_ok=True)
