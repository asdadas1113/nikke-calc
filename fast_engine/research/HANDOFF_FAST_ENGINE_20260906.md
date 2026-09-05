# Fast Engine 작업 인계 — 2026-09-06

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
2. `fast_engine/research/FULL_BURST_CONDITIONAL_PERMANENT_PASSIVE_CHECKPOINT_20260906.md`
3. `fast_engine/research/FINITE_REFERENCE_STACK_CAPTURE_CHECKPOINT_20260906.md`
4. `fast_engine/research/LAZY_DYNAMIC_RANK_TARGET_CHECKPOINT_20260906.md`
5. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`
6. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
7. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`

## 1. 현재 production 상태

latest semantic production commit:

- `7df61bd3853cca202808a43d2d155a38a36df450` — full-burst conditional permanent passive ownership

직전 semantics restoration:

- `2184b253ab22969fff63bc9a95b44aa8a6fc49d9` — finite reference-stack capture ownership
- `cc11c5c08d907001ab6e7841c05da7f3179afa67` — lazy dynamic-rank first-read target ownership
- `0351fb40bd7faae5c62697c22588239b4c6868d4` — sparse same-timestamp actor transaction ownership

직전 safety commits:

- `438eef65426d1ed9e17b871db7cd74e334c8e921` — cross-actor post-shot ordering fail-closed
- `aadfde37ad7be708f6b3d3312ff828844a8a391a` — unsafe dynamic-rank timing fail-closed
- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — scored-state remover dependency fail-closed

safety guard는 실제 semantics ownership을 확보한 narrow shape에서만 철회한다. 미소유 surface는 계속 fail-closed다.

## 2. 최신 완료 — full-burst conditional permanent passive

Moris의 permanent `passive + during_full_burst` 의미론을 직접 확인했다.

- battle start에서 condition false여도 passive row 자체는 등록
- permanent runtime condition은 `get_buffs()`에서 live gate
- full burst start 즉시 contribution ON
- full burst end 즉시 contribution OFF
- `tick()`의 activate/expire transition log는 실제 phase edge보다 정확히 1/60 s 늦음
- 이 로그 지연은 딜 적용 지연이 아님

Fast는 exact phase edge에서 sparse materialize/de-materialize한다. global frame loop는 추가하지 않았다.

첫 owned shape는 의도적으로 좁다.

- direct ATK stat: `atk_pct`, `atk_flat`, `atk_caster_based_pct`
- self target
- duration `None/-1`
- max stack 1
- no parameters / max-trigger / tick interval
- exactly `passive + during_full_burst`

public anchor:

- Dorothy : Serendipity `광익 2` — owned
- `광익 3:accuracy_pct` — 계속 fail-closed

상세:

- `fast_engine/research/FULL_BURST_CONDITIONAL_PERMANENT_PASSIVE_CHECKPOINT_20260906.md`

## 3. Moris/Fast phase trace

통제 squad:

- `라피 : 레드 후드`
- `레드 후드`
- `프리카`
- `민트`
- `도로시 : 세렌디피티`

30 s Fast full-burst start:

- `3.399999999999993`
- `15.933333333333705`
- `28.46666666666633`

Fast end:

- `13.400000000000245`
- `25.93333333333314`

Moris `광익 2` transition logs are each exactly one `DT=1/60 s` later.

하지만 Moris timeline은 phase state와 buff cache를 같은 edge에서 먼저 갱신하고 같은 `t`의 buff read / pending burst damage를 처리하므로 actual contribution boundary는 Fast가 사용하는 exact start/end와 같다.

## 4. 이전 완료 semantics

### 4.1 finite reference-stack capture

- finite `stack_count + scaling_ref` consumer는 activation 순간 provider stack capture
- refresh에서 recapture
- permanent ref는 live이므로 별도 미소유
- Maid Mast/Arcana finite reference owned
- Tove provider는 계속 fail-closed
- Maid Mast split provider가 owned되며 Brady `나누고 싶은 맛` stat_applied branch도 5/5 timestamp exact match로 복구

### 4.2 lazy dynamic-rank resolution

- unresolved rank buff pending
- first stat read에서 live ATK target snapshot
- activation time cohort identity
- same caster/time/raw selector sibling cohort 공유
- Miranda certification 복구

### 4.3 sparse same-timestamp actor transaction

- equal-time weapon work roster actor order
- exact timestamp actor-prefix shot consumption
- global frame loop 없음
- RHQ certification 복구

## 5. 현재 public frontier

latest semantic `7df61bd3853cca202808a43d2d155a38a36df450` 기준:

- source cases: `24`
- unique ordered memberships: `23`
- certified: **2**
- gaps: **21**

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

fresh blocker families:

- normal delivery `47`
- normal state `34`
- skill damage `27`
- skill-state delivery `49`
- weapon change `12`
- cadence `59`
- control `4`
- periodic grid `1`

직전 finite-reference checkpoint 대비:

- normal delivery `49 → 47`
- skill-state delivery `51 → 49`
- certified `2 → 2`

Dorothy `광익 2`가 등장하는 두 membership에서 normal/skill blocker만 각각 하나씩 제거됐다.

## 6. 검증

full-burst passive promotion workflow:

- run `33987191917`
- job `101362856181`
- focused regressions: success
- Fast complete discovery: **288/288**
- structural 180 s median 약 `187.97 ms`, events `539`
- RHQ 30 s relative error 약 `+0.0386%` 유지
- frontier exact family assertion: success

semantic promotion 과정에서 temporary full-burst workflows 3개를 전부 제거했다.

참고로 직전 finite-reference docs clean HEAD canonical CI `33985770383`의 rerun job `101359495014`는 최종 full success였다.

- Fast 284/284
- calculator 137/137 (1 skip)
- optimizer 374/374
- bridge 31/31 (1 skip)
- site 385/385
- golden 29/29

이번 handoff/checkpoint docs commit의 clean HEAD에서는 canonical `ci.yml` 전체 gate를 다시 확인해 최종 상태로 사용한다.

## 7. 현재 phase

현재는 **false-supported safety closure → semantics restoration**을 계속한다.

복구 완료:

1. sparse same-timestamp actor transaction → RHQ certification 복구
2. lazy dynamic-rank first-read resolution → Miranda certification 복구
3. finite named reference-stack capture → Maid Mast/Arcana 및 Brady split dependency 복구
4. full-burst conditional permanent ATK passive → Dorothy `광익 2` delivery 복구

아직 fail-closed:

1. broader producer/mutator dependency ownership
2. permanent/live reference-stack generic semantics
3. `not_during_full_burst` 및 non-ATK permanent passive
4. Dorothy `광익 3:accuracy_pct`
5. Tove `임시 개조` 같은 unowned providers
6. other multi-stack / on-attack / hit-count full-burst families

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 8. 다음 단일 체크포인트

**broader producer/mutator dependency ownership**

먼저 current public blocker에서 scored direct-damage state를 실제로 만들거나 지우는 producer/mutator pair를 전수 추출한다.

핵심 확인:

- `remove_named_buff`가 지우는 provider가 실제 score-affecting state인가 marker-only state인가
- provider와 remover target cohort가 겹치는가
- activation/removal이 같은 timestamp일 때 Moris ordering은 무엇인가
- remover가 finite effect의 expiry/refresh와 만날 때 state lifetime이 어떻게 바뀌는가
- reachable provider가 여러 개인 경우 dependency를 어떻게 fail-closed할 것인가

단순히 provider가 executable이라는 이유로 remover를 자동 지원하지 않는다. Moris trace로 exact pair semantics를 확정한 뒤 narrow generic ownership을 구현한다.

raw coverage expansion, optimizer production integration, global frame loop는 계속 보류한다.

## 9. 작업공간 상태

- branch: `fast-engine-phase2-20260901`
- pre-doc latest semantic: `7df61bd3853cca202808a43d2d155a38a36df450`
- master: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- temporary workflow: 없음
- `.github/workflows`: `ci.yml`, `pages.yml`만 유지

이 문서 커밋 후 latest branch HEAD와 canonical CI를 확인해 최종 clean gate로 기록한다.
