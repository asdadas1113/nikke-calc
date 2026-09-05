# Fast Engine 작업 인계 — 2026-09-06

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
2. `fast_engine/research/PRODUCER_MUTATOR_DEPENDENCY_CHECKPOINT_20260906.md`
3. `fast_engine/research/FULL_BURST_CONDITIONAL_PERMANENT_PASSIVE_CHECKPOINT_20260906.md`
4. `fast_engine/research/FINITE_REFERENCE_STACK_CAPTURE_CHECKPOINT_20260906.md`
5. `fast_engine/research/LAZY_DYNAMIC_RANK_TARGET_CHECKPOINT_20260906.md`
6. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`
7. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
8. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`

## 1. 현재 production 상태

latest semantic production commit:

- `804cc1eff5ea4c2eac61e68771f8d17c174cb930` — full-burst-end named self removal dependency ownership

직전 semantics restoration:

- `7df61bd3853cca202808a43d2d155a38a36df450` — full-burst conditional permanent passive ownership
- `2184b253ab22969fff63bc9a95b44aa8a6fc49d9` — finite reference-stack capture ownership
- `cc11c5c08d907001ab6e7841c05da7f3179afa67` — lazy dynamic-rank first-read target ownership
- `0351fb40bd7faae5c62697c22588239b4c6868d4` — sparse same-timestamp actor transaction ownership

직전 safety commits:

- `438eef65426d1ed9e17b871db7cd74e334c8e921` — cross-actor post-shot ordering fail-closed
- `aadfde37ad7be708f6b3d3312ff828844a8a391a` — unsafe dynamic-rank timing fail-closed
- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — scored-state remover dependency fail-closed

기존 safety guard는 유지한다. 실제 Moris semantics와 dependency가 증명된 narrow shape에서만 예외를 연다.

## 2. 최신 완료 — producer/mutator dependency first slice

public `remove_named_buff`를 전수 감사했다.

- source cases `24`
- unique memberships `23`
- `remove_named_buff` rows `72`

첫 owned public pair는 하나다.

- owner: `아르카나 : 포츈 메이트`
- provider: `추억 남기기 3`
- provider stat: `atk_dmg_pct +29.99`
- provider lifetime: permanent / max stack 1
- provider trigger: `burst_cast`
- remover: `쌓여가는 사진첩 3`
- remover trigger: `full_burst_end`
- target: same actor / self

Moris에서 provider는 B2 `burst_cast` timestamp에 즉시 활성화되고,
각 `full_burst_end` timestamp에 정확히 제거된다. 1/60 s 지연이 없다.

Fast도 BurstMachine phase transition 후 같은 timestamp의 `full_burst_end` signal을 dispatch하므로,
exact edge에서 named state를 제거한다.

상세:

- `fast_engine/research/PRODUCER_MUTATOR_DEPENDENCY_CHECKPOINT_20260906.md`

## 3. 중요한 fail-closed 경계

Arcana의 겉보기 이웃 pair는 소유하지 않았다.

- remover: `쌓여가는 사진첩 2`
- provider: `추억 남기기`
- provider stat: `crit_rate +20.09`

`추억 남기기`는 다음 효과들이 named state condition으로 직접 참조한다.

- `청춘의 기록`
- `기억과 추억`
- `기억과 추억 2`
- `행복한 기억`
- `소중한 추억`

따라서 이 remover를 열면 Arcana의 gauge/ammo/pellet/ATK state machine까지 함께 소유해야 한다.
이번 semantic에서는 계속 fail-closed다.

그 외 계속 fail-closed:

- Maid Mast `취기` multi-stack/conditional removal
- Snow White : Heavy Arms finite/on-attack removal
- Little Mermaid enemy hit-count removal
- Grave hit-count/reload removal
- finite expiry/refresh remover races
- duplicate-name providers
- state-end/named-state/live-reference consumers

## 4. 새 generic ownership 조건

`TriggerDispatcher._full_burst_end_self_direct_remove_dependency_supported()`가 첫 slice를 정의한다.

Remover 조건:

- `instant + remove_named_buff`
- self target
- no value/duration/stack/max-trigger/tick
- parameters exactly `target_effect`
- no conditions
- exactly one trigger: `full_burst_end`

Provider 조건:

- compiled squad 전체에서 같은 name provider가 정확히 하나
- same actor / self target
- `buff + atk_dmg_pct`
- permanent / max stack 1
- no parameters/conditions/max-trigger/tick
- exactly one trigger: `burst_cast`
- 기존 direct-damage runtime support 충족

추가 dependency guard:

- `event:state_end:<name>` consumer 없음
- named state condition consumer 없음
- 다른 `target_effect` mutator 없음
- live `scaling_ref` consumer 없음

Moris `remove_named_buff`는 이름 기준 전역 제거지만,
provider global uniqueness + same actor/self 조건 때문에 이 slice에서는 Fast target-scoped removal과 결과가 동일하다.

## 5. 이전 완료 semantics

### 5.1 full-burst conditional permanent passive

- permanent passive row + live condition gate
- actual contribution은 exact full-burst phase edge에서 ON/OFF
- Moris transition log만 1/60 s 늦음
- Fast는 global frame loop 없이 phase edge에서 sparse materialize/de-materialize
- Dorothy : Serendipity `광익 2` owned
- `광익 3:accuracy_pct`는 fail-closed

### 5.2 finite reference-stack capture

- finite `stack_count + scaling_ref` consumer는 activation 순간 provider stack capture
- refresh에서 recapture
- permanent reference는 live이므로 별도 미소유
- Maid Mast/Arcana finite reference owned
- Tove provider는 계속 fail-closed

### 5.3 lazy dynamic-rank resolution

- unresolved rank buff pending
- first stat read에서 live ATK target snapshot
- activation-time cohort identity
- same caster/time/raw selector sibling cohort 공유
- Miranda certification 복구

### 5.4 sparse same-timestamp actor transaction

- equal-time weapon work roster actor order
- exact timestamp actor-prefix shot consumption
- global frame loop 없음
- RHQ certification 복구

## 6. 현재 public frontier

latest semantic `804cc1eff5ea4c2eac61e68771f8d17c174cb930` 기준:

- source cases: `24`
- unique ordered memberships: `23`
- certified: **2**
- gaps: **21**

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

fresh blocker families:

- normal delivery `47`
- normal state `33`
- skill damage `27`
- skill-state delivery `49`
- weapon change `12`
- cadence `59`
- control `4`
- periodic grid `1`

직전 full-burst passive checkpoint 대비:

- normal state `34 → 33`
- 나머지 family unchanged
- certified `2 → 2`

제거된 blocker는 정확히 하나다.

- `normal_state:아르카나 : 포츈 메이트:쌓여가는 사진첩 3:remove_named_buff`

## 7. 검증

final semantic focused promotion:

- run `33991915684`
- job `101375546391`
- focused regressions: success
- semantic commit: `804cc1eff5ea4c2eac61e68771f8d17c174cb930`

public/frontier promotion:

- run `33991961043`
- job `101375669685`
- Fast complete discovery: **292/292**
- structural 180 s median: `143.92 ms`
- samples: `[142.99, 147.06, 143.92]`
- events: `539`
- RHQ Moris/reference: `236373847.0`
- RHQ Fast: `236465053.42473748`
- relative error: `0.0003858566668650809` (~`+0.0386%`)
- public owned remover count: exactly `1`

이번 checkpoint 문서/cleanup commit 후 clean HEAD에서 canonical `ci.yml` 전체 gate를 다시 확인한다.

## 8. 현재 phase

현재는 **false-supported safety closure → semantics restoration**을 계속한다.

복구 완료:

1. sparse same-timestamp actor transaction
2. lazy dynamic-rank first-read resolution
3. finite named reference-stack capture
4. full-burst conditional permanent ATK passive
5. globally-unambiguous permanent self provider → full-burst-end remover first slice

아직 fail-closed:

1. broader producer/mutator families beyond the first remover slice
2. permanent/live reference-stack generic semantics
3. `not_during_full_burst` 및 non-ATK permanent passive
4. Dorothy `광익 3:accuracy_pct`
5. Tove `임시 개조` 같은 unowned providers
6. multi-stack / on-attack / hit-count remover families
7. Arcana `추억 남기기` state-machine dependency family

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 9. 다음 단일 체크포인트

**roster-static mutually-exclusive named-state producer/remover ownership**

첫 public anchor 후보:

- Anis : Star `나만의 별` provider / `스타 폴 4` remover

먼저 확인할 것:

1. `has_burst1_ally` / `no_burst1_ally`가 compiled roster에서 정말 static mutually-exclusive인가
2. provider/remover가 같은 timestamp에서 함께 reachable한 경로가 없는가
3. Moris battle-start / full-burst-end ordering이 어떤가
4. provider name의 state/event/scaling consumers가 있는가
5. target cohort와 duplicate provider ambiguity가 없는가
6. roster-static condition을 근거로 remover blocker를 제거해도 normal/skill score가 변하지 않는가

후보 이름만 보고 지원하지 않는다. fresh public audit와 Moris trace 후 exact proven shape만 연다.

raw coverage expansion, optimizer production integration, global frame loop는 계속 보류한다.

## 10. 작업공간 상태

- branch: `fast-engine-phase2-20260901`
- pre-doc latest semantic: `804cc1eff5ea4c2eac61e68771f8d17c174cb930`
- master: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- temporary workflow/helper: docs/cleanup commit에서 전부 제거
- clean `.github/workflows`: `ci.yml`, `pages.yml`만 유지

이 문서 커밋 후 latest branch HEAD와 canonical CI를 확인해 최종 clean gate로 사용한다.
