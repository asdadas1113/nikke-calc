# Fast Engine 작업 인계 — 2026-09-06

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
2. `fast_engine/research/FINITE_REFERENCE_STACK_CAPTURE_CHECKPOINT_20260906.md`
3. `fast_engine/research/LAZY_DYNAMIC_RANK_TARGET_CHECKPOINT_20260906.md`
4. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`
5. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
6. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`

## 1. 현재 production 상태

latest semantic production commit:

- `2184b253ab22969fff63bc9a95b44aa8a6fc49d9` — finite reference-stack capture ownership

직전 semantics restoration:

- `cc11c5c08d907001ab6e7841c05da7f3179afa67` — lazy dynamic-rank first-read target ownership
- `0351fb40bd7faae5c62697c22588239b4c6868d4` — sparse same-timestamp actor transaction ownership

직전 safety commits:

- `438eef65426d1ed9e17b871db7cd74e334c8e921` — cross-actor post-shot ordering fail-closed
- `aadfde37ad7be708f6b3d3312ff828844a8a391a` — unsafe dynamic-rank timing fail-closed
- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — scored-state remover dependency fail-closed

safety guard는 실제 semantics ownership을 확보한 narrow shape에서만 철회한다. 미소유 surface는 계속 fail-closed다.

## 2. 최신 완료 — finite reference-stack capture

Moris의 `stack_count + scaling_ref` 의미론을 직접 확인했다.

- finite duration consumer: activation 순간 provider stack을 `scaling_stack`으로 capture
- provider stack이 이후 변해도 기존 finite consumer magnitude는 고정
- refresh/reactivation: current provider stack을 다시 capture
- permanent/infinite consumer: captured value 없이 live reference 유지
- activation 순간 provider가 없으면 `None`을 유지해 이후 live ref lookup fallback

Fast는 이를 다음 좁은 shape로 소유한다.

- finite positive-duration buff
- `scaling == stack_count`
- named `scaling_ref`
- consumer max stack 1
- no max-trigger / periodic tick
- same-caster exact-name provider가 정확히 하나
- provider가 executable self buff이고 자체 reference-scaling이 아님

결과:

- Maid Mast `취기` 기반 finite direct reference effects owned
- Arcana : Fortune Mate `소중한 추억 → 쌓여가는 사진첩` owned
- Tove `임시 개조` provider는 미소유이므로 계속 fail-closed
- Solin permanent/gauge live reference도 이번 slice에서 열지 않음

상세:

- `fast_engine/research/FINITE_REFERENCE_STACK_CAPTURE_CHECKPOINT_20260906.md`

## 3. 연쇄 복구 — Brady split stat_applied

Maid Mast `파이레츠 스피릿:split_dmg_pct`가 실제 owned producer가 되면서 Brady `나누고 싶은 맛`의 `event:stat_applied:split_dmg_pct` branch가 reachable해졌다.

40 s `레이드_앨리스브래디` 직접 trace:

- Fast activation 5개
- Moris activation 5개
- 모든 timestamp 1:1 동일
- pairwise diff 전부 `0.0`

따라서 이 exact split branch만 dependency-safe로 복구했다.

`dot_dmg_pct → 머물고 싶은 맛`은 provider가 아직 미소유이므로 계속 fail-closed다.

probe:

- run `33985501903`
- job `101358141415`

## 4. 이전 완료 semantics

### 4.1 lazy dynamic-rank resolution

- unresolved rank buff를 pending으로 보관
- first stat read에서 live ATK로 target snapshot
- activation time은 cohort identity로 사용
- same caster/time/raw selector sibling cohort 공유
- `컨트롤_미란다미하라` certification 복구

상세: `LAZY_DYNAMIC_RANK_TARGET_CHECKPOINT_20260906.md`

### 4.2 sparse same-timestamp actor transaction

- phase-30 equal-time weapon work roster actor order
- static shot cursor exact timestamp actor prefix consume
- global 60 Hz/per-shot loop 없음
- `레이드_레드후드퀀시` certification 복구

상세: `SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`

## 5. 현재 public frontier

latest semantic `2184b253ab22969fff63bc9a95b44aa8a6fc49d9` 기준:

- source cases: `24`
- unique ordered memberships: `23`
- certified: **2**
- gaps: **21**

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

fresh blocker families:

- normal delivery `49`
- normal state `34`
- skill damage `27`
- skill-state delivery `51`
- weapon change `12`
- cadence `59`
- control `4`
- periodic grid `1`

직전 lazy-rank checkpoint 대비:

- normal delivery `55 → 49`
- skill-state delivery `62 → 51`
- cadence `62 → 59`
- certified `2 → 2`

이번 slice는 새로운 membership을 성급히 인증하지 않고 기존 gaps 내부의 실제 reference semantics를 복구했다.

## 6. 검증

finite reference-stack promotion workflow:

- run `33985621674`
- job `101358468826`
- focused regressions: success
- Fast complete discovery: **284/284**
- structural 180 s median 약 `178.67 ms`, events `539`
- RHQ 30 s relative error 약 `+0.0386%` 유지
- frontier exact family assertion: success
- safe stat-applied match: Brady `나누고 싶은 맛 / split_dmg_pct` 하나뿐

임시 workflow 5개는 semantic commit에서 전부 제거했다.

이 handoff/checkpoint docs commit의 clean HEAD에서 canonical `ci.yml` 전체 gate를 다시 확인해 최종 상태로 사용한다.

## 7. 현재 phase

현재는 **false-supported safety closure → semantics restoration**을 계속한다.

복구 완료:

1. sparse same-timestamp actor transaction → RHQ certification 복구
2. lazy dynamic-rank first-read resolution → Miranda certification 복구
3. finite named reference-stack capture → Maid Mast/Arcana delivery 및 Brady split dependency 복구

아직 fail-closed:

1. generic full-burst conditional permanent passive
2. broader producer/mutator dependency ownership
3. permanent/live reference-stack generic semantics
4. unowned providers such as Tove `임시 개조`

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 8. 다음 단일 체크포인트

**generic full-burst conditional permanent passive semantics**

확인할 핵심:

- permanent buff가 full-burst 조건에서 언제 activation되는가
- full burst가 끝났을 때 condition false가 되면 active row를 remove하는가
- 한번 activation된 permanent passive가 이후에도 남는가
- battle start / full burst enter / full burst end에서 Moris state transition이 정확히 무엇인가
- public에서 실제 provider/consumer reachability가 있는 narrow shape가 무엇인가

static permanent modifier로 무조건 fold하거나 guard만 제거하지 않는다. 먼저 Moris trace를 직접 probe하고, current public reachable surface만 generic ownership한다.

broader producer/mutator dependency와 raw coverage expansion은 이 뒤로 둔다.

## 9. 작업공간 상태

- branch: `fast-engine-phase2-20260901`
- pre-doc latest semantic: `2184b253ab22969fff63bc9a95b44aa8a6fc49d9`
- master: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- temporary workflow: 없음
- `.github/workflows`: `ci.yml`, `pages.yml`만 유지

이 문서 커밋 후 latest branch HEAD와 canonical CI를 확인해 최종 clean gate로 기록한다.
