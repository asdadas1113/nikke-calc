# Fast Engine sparse same-timestamp actor transaction 체크포인트 — 2026-09-06

## 1. 목적

`438eef65426d1ed9e17b871db7cd74e334c8e921`에서 fail-closed한 cross-actor post-shot same-timestamp ordering을 실제 Fast semantics ownership으로 복구한다.

Moris의 의미론은 같은 frame/timestamp에서 대략 다음 순서를 가진다.

> actor N shot/score → actor N post-shot trigger/state mutation → actor N+1 shot/score

기존 Fast static score observer는 첫 phase-30 trigger 전에 timestamp `t`의 모든 static actor shot을 inclusive consume하여 이 actor transaction을 flatten했다.

이번 작업의 제약은 명확하다.

- global 60 Hz Moris식 frame loop를 만들지 않는다.
- 모든 shot을 개별 global event로 materialize하지 않는다.
- 의미 있는 동일 timestamp의 phase-30 weapon transaction에서만 roster actor order를 보존한다.
- 기존 fail-closed safety를 구현 소유 없이 넓게 제거하지 않는다.

## 2. production 구현

semantic production commit:

- `0351fb40bd7faae5c62697c22588239b4c6868d4` — `Fast: own sparse same-timestamp actor transactions`

stale regression restoration commit:

- `7e3fb23cc184ddc48b552da60927bd31faa68250` — `test: restore certified RHQ expectations`

### 2.1 phase-30 actor ordering

`fast_engine/engine/scheduler.py`의 equal-time 정렬을 다음처럼 좁게 바꿨다.

- 기본: `(time, phase, sequence)` 의미를 유지
- phase 30이며 actor가 있는 weapon/reload/trigger work만 `(time, phase, actor, sequence)`로 정렬
- 다른 phase는 기존 insertion-stable semantics 유지

따라서 동일 timestamp의 의미 있는 weapon work만 roster actor 순서를 가진다.

### 2.2 sparse score actor transaction

scheduler가 현재 처리 중인 phase-30 `(timestamp, actor)`를 execution context에 기록한다.

`ShotBlockCursor.consume_until(t, inclusive=True)`는 그 exact timestamp에서:

- 현재 actor 이하의 static shot은 기존처럼 소비
- 뒤 roster actor의 exact-`t` shot은 아직 소비하지 않고 남김
- `t`보다 과거 shot은 정상 소비

같은 timestamp의 다음 actor event가 오면 cutoff가 전진한다. 더 이상 같은 timestamp event가 없으면 cutoff를 해제해 기존 BurstRuntime의 end-of-timestamp inclusive drain이 나머지 shot을 소비한다.

즉 static shot block 압축을 유지하면서 다음 순서를 복구한다.

> shot(actor N) → post-shot state mutation → shot(actor N+1)

### 2.3 dynamic weapon 경계

기존 dynamic charge/weapon boundary도 scheduler phase 30을 사용한다. 따라서 별도 global shot loop 없이 static/dynamic boundary가 동일 actor-ordered transaction에 들어간다.

### 2.4 guard 철회 범위

실제 transaction ownership이 생겼으므로 `same_timestamp_actor_order` fail-closed guard를 제거했다.

다른 safety closure는 유지한다.

- unsafe dynamic-rank timing guard 유지
- comparison-critical remover dependency guard 유지
- unowned reference-stack scaling guard 유지
- unowned permanent conditional passive guard 유지
- exact target grammar guard 유지
- `last_bullet_fire`를 post-shot `last_bullet`과 alias하지 않음

## 3. RHQ 복구

public team `레이드_레드후드퀀시`에서 기존 ordering guard 4개가 제거됐다.

- 프리카 `무대, 시작할게.`
- 프리카 `무대, 시작할게. 2`
- 프리카 `무대, 시작할게. 3`
- 민트 `보컬 효과`

Quency의 self-only hit-count state는 원래 이 ordering hole이 아니었고 그대로다.

현재 public certification accounting은:

- source cases: `24`
- unique ordered memberships: `23`
- certified: **1**
- certified membership: **`레이드_레드후드퀀시`**
- coverage gaps: **22**

`컨트롤_미란다미하라`는 lazy dynamic-rank timing이 아직 미소유이므로 계속 fail-closed다.

## 4. permanent regressions

새 파일:

- `fast_engine/tests/test_damage_same_timestamp_actor_transaction.py`

고정한 invariant:

1. equal-time phase-30 event는 insertion order보다 roster actor order를 우선한다.
2. exact timestamp static shot은 현재 actor prefix까지만 inclusive consume된다.
3. timestamp transaction 종료 뒤에는 later actor shot이 정상 drain된다.

기존 RHQ 관련 회귀도 pre-guard certified expectation으로 복구했다.

- dynamic weapon change public certification
- projectile named-stack chain certification
- post-shot `last_bullet` ownership
- Moris frame timing/ranking near-tie fixture
- full-charge lifetime / charge-speed public frontier assertions
- stat-applied charge-speed public frontier assertion

첫 canonical run `33979331938`에서는 Fast damage shard가 통과했지만 complete discovery에서 guard 시절 stale assertion 2개가 발견됐다. 두 테스트는 구현 오류가 아니라 `same_timestamp_actor_order` blocker 존재를 계속 기대하고 있었다. 이를 pre-guard semantic regression으로 복구한 뒤 재실행했다.

## 5. canonical 검증

최종 semantic/test HEAD 전 canonical CI:

- run: `33979473026`
- job: `101341973396`
- result: **success**

결과:

- Fast damage: **170/170**
- Fast complete discovery: **278/278**
- calculator: **137/137 (1 skip)**
- optimizer: **374/374**
- bridge: **31/31 (1 skip)**
- site: **385/385**
- golden snapshot: **29/29**

RHQ 30 s regression:

- Moris: `236,373,847`
- Fast: `236,465,053.42473748`
- relative error: `+0.0003858567` ≈ **+0.0386%**

structural performance:

- 180 s static score median: 약 **175.7 ms**
- events: **539**
- performance contract: success

직전 runner의 약 99 ms보다 이번 hosted runner 측정은 느렸지만 contract threshold는 그대로 유지했고 통과했다. 구조적 event count도 539로 유지됐다.

## 6. 결론

`certified 0 → 1`은 blocker를 무조건 삭제해서 만든 변화가 아니다. 먼저 같은 timestamp actor transaction을 sparse semantics로 소유한 뒤 해당 safety guard를 철회했고, RHQ의 Moris parity와 전체 canonical regression을 다시 통과시켰다.

이번 구현은 global 60 Hz loop를 도입하지 않았다. static shot block 압축과 continuous-time scheduler를 유지하면서 결과에 영향을 주는 same-timestamp weapon actor 사이에서만 순서를 보존한다.

## 7. 다음 단일 체크포인트

다음은 **lazy dynamic-rank resolution / same-event cohort semantics**다.

주요 public surface:

- `컨트롤_미란다미하라`
- 미란다 `파워 업!`
- 미란다 `파워 업! 2`
- 동일 `burst_cast` timestamp의 Brid / Rouge ATK mutation과 top-ATK selector ordering

목표는 rank guard를 단순 제거하는 것이 아니라 Moris의 lazy target selection 시점을 실제로 소유해 두 번째 certified membership 복구 여부를 판단하는 것이다.

reference-stack capture, full-burst conditional permanent passive, broader mutator ownership은 그 이후다.

## 8. 작업공간

- branch: `fast-engine-phase2-20260901`
- semantic production: `0351fb40bd7faae5c62697c22588239b4c6868d4`
- stale-test restoration: `7e3fb23cc184ddc48b552da60927bd31faa68250`
- `master`: `fb2fd9157aa14499daf6b9f185beb685d4393f90` — 수정/병합하지 않음
- temporary workflow: 없음
- `.github/workflows`: `ci.yml`, `pages.yml`만 유지
