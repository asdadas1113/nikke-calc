# Fast Engine 작업 인계 — 2026-09-06

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
2. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`
3. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
4. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`

## 1. 현재 production 상태

latest semantic production commit:

- `0351fb40bd7faae5c62697c22588239b4c6868d4` — sparse same-timestamp actor transaction ownership

follow-up regression commit:

- `7e3fb23cc184ddc48b552da60927bd31faa68250` — guard 시절 stale RHQ assertion 2개를 certified expectation으로 복구

직전 safety commits:

- `438eef65426d1ed9e17b871db7cd74e334c8e921` — cross-actor post-shot ordering fail-closed
- `aadfde37ad7be708f6b3d3312ff828844a8a391a` — unsafe dynamic-rank timing fail-closed
- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — scored-state remover dependency fail-closed

`438eef...`의 ordering guard는 의미론을 실제 소유한 뒤 제거했다. 다른 safety closure는 유지한다.

## 2. 이번 완료 — sparse same-timestamp actor transaction

기존 Fast 문제:

- 첫 phase-30 trigger 전에 timestamp `t`의 모든 static actor shot을 먼저 score
- Moris의 actor별 `shot → post-shot mutation → next actor shot` 순서를 flatten

현재 구현:

- global 60 Hz/per-shot loop 없음
- phase-30 equal-time weapon work만 roster actor order로 정렬
- static ShotBlockCursor는 exact-`t`에서 현재 actor prefix까지만 inclusive consume
- same timestamp가 끝나면 기존 end-of-timestamp drain으로 나머지 shot 처리
- dynamic weapon boundary도 기존 phase-30 scheduler를 통해 같은 actor transaction에 참여

public 결과:

- RHQ ordering blockers 4개 제거
  - 프리카 `무대, 시작할게.` / `2` / `3`
  - 민트 `보컬 효과`
- public `23 unique / 1 certified / 22 gaps`
- certified: `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`는 rank timing guard 때문에 계속 fail-closed

상세:

- `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`

## 3. 검증

최종 semantic/test 상태 canonical CI:

- run `33979473026`
- job `101341973396`
- **전체 success**

canonical results:

- Fast damage `170/170`
- Fast complete discovery `278/278`
- calculator `137/137 (1 skip)`
- optimizer `374/374`
- bridge `31/31 (1 skip)`
- site `385/385`
- golden `29/29`
- structural 180 s median 약 `175.7 ms`, events `539`

RHQ 30 s Moris/Fast direct regression:

- Moris `236,373,847`
- Fast `236,465,053.42473748`
- relative error 약 `+0.0386%`

첫 run `33979331938`의 complete discovery 실패 2개는 guard 존재를 계속 기대하던 shard-outside stale assertions였고, 구현은 Fast damage shard부터 이미 통과했다. stale assertions를 pre-guard certified regression으로 복구한 뒤 최종 canonical run이 전부 초록이다.

## 4. 현재 phase

현재는 **false-supported safety closure → semantics restoration**을 계속한다.

복구 완료:

1. sparse same-timestamp actor transaction → RHQ certification 복구

아직 fail-closed:

1. lazy dynamic-rank resolution / same-event cohort
2. finite reference-stack capture
3. generic full-burst conditional permanent passive
4. broader producer/mutator dependency ownership

raw coverage expansion이나 optimizer integration으로 돌아가지 않는다.

## 5. 다음 단일 체크포인트

**lazy dynamic-rank resolution / same-event cohort semantics**

우선 public anchor:

- `컨트롤_미란다미하라`
- 미란다 `파워 업!`
- 미란다 `파워 업! 2`

확인해야 할 핵심:

- 같은 `burst_cast` timestamp에 Brid `풀 마스콘`, Rouge `더 게임 마스터` 등 ATK mutation이 존재한다.
- Moris가 `allies_top_atk_excl:*` target을 어느 transaction 지점에서 lazy resolve하는지 직접 probe한다.
- synthetic target inversion만 보지 말고 실제 public reachability와 Moris/Fast target/activation trace를 대조한다.
- ownership이 증명되기 전 `rank_target_timing` guard를 제거하지 않는다.
- global frame loop를 만들지 않는다. sparse/same-event cohort 방식으로 해결 가능한지 먼저 본다.

성공하면 `컨트롤_미란다미하라`가 두 번째 certified membership으로 복구될 가능성이 있다. 실패하면 guard를 유지하고 다음 semantics로 넘어간다.

## 6. 작업공간 상태

- branch: `fast-engine-phase2-20260901`
- pre-doc HEAD: `7e3fb23cc184ddc48b552da60927bd31faa68250`
- latest semantic: `0351fb40bd7faae5c62697c22588239b4c6868d4`
- master: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- temporary workflow: 없음
- `.github/workflows`: `ci.yml`, `pages.yml`만 유지

이 문서 커밋 후 최신 branch HEAD와 canonical CI를 다시 확인해 최종 clean gate로 기록한다.
