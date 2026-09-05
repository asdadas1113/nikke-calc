# Fast Engine 작업 인계 — 2026-09-06

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
2. `fast_engine/research/ROSTER_STATIC_NAMED_REMOVE_CHECKPOINT_20260906.md`
3. `fast_engine/research/PRODUCER_MUTATOR_DEPENDENCY_CHECKPOINT_20260906.md`
4. `fast_engine/research/FULL_BURST_CONDITIONAL_PERMANENT_PASSIVE_CHECKPOINT_20260906.md`
5. `fast_engine/research/FINITE_REFERENCE_STACK_CAPTURE_CHECKPOINT_20260906.md`
6. `fast_engine/research/LAZY_DYNAMIC_RANK_TARGET_CHECKPOINT_20260906.md`
7. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`
8. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
9. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`

## 1. 현재 production 상태

latest semantic production commit:

- `969b75c4ade19c8e2eea1951f38c5d76df4ced62` — roster-static false B1 named-removal score dependency proof

직전 semantics restoration:

- `804cc1eff5ea4c2eac61e68771f8d17c174cb930` — full-burst-end named self removal dependency ownership
- `7df61bd3853cca202808a43d2d155a38a36df450` — full-burst conditional permanent passive ownership
- `2184b253ab22969fff63bc9a95b44aa8a6fc49d9` — finite reference-stack capture ownership
- `cc11c5c08d907001ab6e7841c05da7f3179afa67` — lazy dynamic-rank first-read target ownership
- `0351fb40bd7faae5c62697c22588239b4c6868d4` — sparse same-timestamp actor transaction ownership

직전 safety commits:

- `438eef65426d1ed9e17b871db7cd74e334c8e921` — cross-actor post-shot ordering fail-closed
- `aadfde37ad7be708f6b3d3312ff828844a8a391a` — unsafe dynamic-rank timing fail-closed
- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — scored-state remover dependency fail-closed

safety guard는 실제 semantics 또는 reachability가 증명된 narrow shape에서만 철회한다.

## 2. 최신 완료 — roster-static named-removal proof

첫 public anchor:

- `아니스 : 스타:나만의 별`
- remover `스타 폴 4`

public 아니스 membership 3개 모두:

- 아니스 외 B1 ally 없음
- 다른 actor의 `burst_stage_override:*` effect 없음
- `나만의 별:no_burst1_ally` true
- `스타 폴 4:has_burst1_ally` false

Moris에서는 `나만의 별`이 battle start와 각 full-burst end에 유지/refresh되고 제거되지 않는다.

B1 control roster에서는 반대로:

- `나만의 별` 없음
- `모두의 별`만 활성
- `스타 폴 4` branch reachable

따라서 runtime remover 지원은 추가하지 않았다.

`score.py`의 `_roster_static_burst1_condition_unreachable()`가 다음 경우만 condition false를 증명한다.

- exactly one B1 presence condition
- mode `has_burst1_ally` 또는 `no_burst1_ally`
- 다른 actor에 `burst_stage_override:*` effect 없음
- compiled roster stage 기준 condition false

stage override 가능성이 하나라도 있으면 fail-closed다.

상세:

- `fast_engine/research/ROSTER_STATIC_NAMED_REMOVE_CHECKPOINT_20260906.md`

## 3. 현재 public frontier

canonical frontier filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외

latest semantic 기준:

- source cases: `24`
- unique ordered memberships: `23`
- certified: **2**
- gaps: **21**

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

fresh blocker families:

- normal delivery `47`
- normal state `30`
- skill damage `27`
- skill-state delivery `49`
- weapon change `12`
- cadence `59`
- control `4`
- periodic grid `1`

직전 checkpoint 대비:

- normal state `33 → 30`
- 나머지 family unchanged
- certified `2 → 2`

사라진 blocker는 아니스 : 스타가 포함된 3 unique membership의
`normal_state:아니스 : 스타:스타 폴 4:remove_named_buff`뿐이다.

## 4. 검증

semantic focused promotion:

- run `33996736322`
- job `101388480908`
- focused regressions success
- semantic commit `969b75c4ade19c8e2eea1951f38c5d76df4ced62`

public/full promotion:

- run `33996858664`
- job `101388805370`
- frontier exact assertion success
- Fast complete discovery **297/297**
- structural median `159.57 ms`
- samples `[158.71, 162.0, 159.57]`
- events `539`
- RHQ relative error `0.0003858566668650809` (~`+0.0386%`)

Moris regression에서 public no-B1와 B1 control의 branch 상호배타성도 직접 고정했다.

## 5. 현재 phase

현재는 **false-supported safety closure → semantics restoration**을 계속한다.

복구 완료:

1. sparse same-timestamp actor transaction
2. lazy dynamic-rank first-read resolution
3. finite named reference-stack capture
4. full-burst conditional permanent ATK passive
5. globally-unambiguous permanent self provider → full-burst-end remover first slice
6. roster-static false B1 remover score reachability proof

아직 fail-closed:

1. 실제 reachable conditional named removers
2. permanent/live reference-stack generic semantics
3. `not_during_full_burst` 및 non-ATK permanent passive
4. Dorothy `광익 3:accuracy_pct`
5. Tove `임시 개조` 같은 unowned providers
6. multi-stack / on-attack / hit-count remover families
7. Arcana `추억 남기기` state-machine dependency family
8. Maid Mast `취기` / `파이레츠 스피릿 3` conditional multi-stack family

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 6. 다음 단일 체크포인트

**Maid Mast conditional multi-stack named-removal semantics**

첫 public anchor:

- `마스트 : 로망틱 메이드`
- remover `파이레츠 스피릿 3:remove_named_buff`
- target state family `취기`

먼저 확인할 것:

1. `취기`의 provider/stack producer와 max-stack 도달 경로
2. remover condition의 실제 reachability
3. shot/reload/full-burst와 removal same-timestamp ordering
4. accuracy/cadence/score-planning 의존성
5. named-state consumer / duplicate provider ambiguity
6. finite/reference interaction

단순히 provider 또는 remover가 executable이라는 이유로 열지 않는다. Moris trace와 score-planning 안전성까지 증명된 exact shape만 소유한다.

## 7. 작업공간 상태

이 handoff/checkpoint cleanup commit에서 다음 temporary 파일을 모두 제거한다.

- `.github/workflows/tmp-roster-static-mutator-audit.yml`
- `fast_engine/research/tmp_roster_static_mutator_audit.py`
- `fast_engine/research/tmp_roster_static_patch.py`
- `fast_engine/research/tmp_roster_static_promotion.py`

최종 clean `.github/workflows`는 다시:

- `ci.yml`
- `pages.yml`

만 남겨야 한다.

- branch: `fast-engine-phase2-20260901`
- latest semantic: `969b75c4ade19c8e2eea1951f38c5d76df4ced62`
- master: `fb2fd9157aa14499daf6b9f185beb685d4393f90`

이 docs/cleanup commit의 clean HEAD에서 canonical `ci.yml` 전체 gate를 최종 확인한다.
