# Fast Engine 작업 인계 — 2026-09-06

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
2. `fast_engine/research/LAZY_DYNAMIC_RANK_TARGET_CHECKPOINT_20260906.md`
3. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`
4. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
5. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`

## 1. 현재 production 상태

latest semantic production commit:

- `cc11c5c08d907001ab6e7841c05da7f3179afa67` — lazy dynamic-rank target resolution ownership

직전 semantics restoration:

- `0351fb40bd7faae5c62697c22588239b4c6868d4` — sparse same-timestamp actor transaction ownership
- `7e3fb23cc184ddc48b552da60927bd31faa68250` — guard 시절 stale RHQ assertions 복구

직전 safety commits:

- `438eef65426d1ed9e17b871db7cd74e334c8e921` — cross-actor post-shot ordering fail-closed
- `aadfde37ad7be708f6b3d3312ff828844a8a391a` — unsafe dynamic-rank timing fail-closed
- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — scored-state remover dependency fail-closed

두 safety guard는 각각 실제 semantics ownership을 확보한 narrow shape에 대해서만 철회했다. 나머지 미소유 surface는 계속 fail-closed다.

## 2. 최신 완료 — lazy dynamic-rank resolution

Moris는 dynamic rank target buff를 activation 시 concrete target으로 확정하지 않는다. `target_chars=None`으로 보관한 뒤 첫 실제 buff read에서 live ATK로 target을 resolve하며, 같은 caster + activation time + exact raw selector sibling은 하나의 cohort를 공유한다.

Fast도 이를 좁게 소유했다.

- unresolved rank buff를 `ActiveEffectStore` pending target으로 보관
- 첫 해당 stat read 때 materialize
- cache identity는 activation time, 실제 ranking 값은 first-read 시점 live ATK
- unresolved rank buff는 자기 own ranking 계산에 끼지 않음
- pending activation이 damage cache를 stale하게 남기지 않도록 ally EFFECT dependency를 invalidate
- 이미 resolved된 effect refresh는 기존 cohort 유지

지원 범위는 max-stack 1, no bullet lifetime, no runtime condition, no recipient-scoped named-event/state dependency인 direct-damage rank buff로 한정한다.

따라서 미란다 `파워 업!` / `파워 업! 2`는 owned 되었지만 `웨이크업! 4`의 `duration_bullets:1`은 이번 lazy slice로 넓히지 않았다.

상세:

- `fast_engine/research/LAZY_DYNAMIC_RANK_TARGET_CHECKPOINT_20260906.md`

## 3. 직전 완료 — sparse same-timestamp actor transaction

Fast의 phase-30 equal-time weapon work를 roster actor order로 처리하고, static shot block은 exact timestamp에서 현재 actor prefix까지만 consume하도록 바꿨다. global 60 Hz/per-shot loop는 추가하지 않았다.

결과:

- RHQ ordering blockers 4개 제거
- `레이드_레드후드퀀시` certification 복구

상세:

- `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`

## 4. 현재 public frontier

latest semantic `cc11c5c08d907001ab6e7841c05da7f3179afa67` 기준:

- source cases: `24`
- unique ordered memberships: `23`
- certified: **2**
- coverage gaps: **21**

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

fresh blocker families:

- normal state `34`
- normal delivery `55`
- skill-state delivery `62`
- skill damage `27`
- cadence `62`
- weapon change `12`
- control `4`
- periodic grid `1`

감사 전의 2 certified를 단순 guard 제거로 되돌린 것이 아니다. RHQ는 sparse actor transaction, Miranda는 actual first-read lazy rank snapshot을 각각 구현해 복구했다.

## 5. 검증

lazy-rank promotion pre-commit workflow:

- run `33983062877`
- job `101351627750`
- focused lazy-rank regressions: success
- full Fast discovery: **279/279**
- public frontier assertion: **23 unique / 2 certified / 21 gaps**
- structural 180 s median 약 `180.66 ms`, events `539`
- RHQ 30 s existing Moris/Fast relative error 약 `+0.0386%` 유지

focused에서 실제 `컨트롤_미란다미하라` blocker-free certification과 방어력 55,000 near-tie 180초 Moris/Fast 순서·오차 계약을 복구했다.

semantic commit push는 workflow 내부 `GITHUB_TOKEN`이었기 때문에 별도 canonical push run을 재트리거하지 않는다. 이 handoff/checkpoint 직접 커밋의 clean HEAD에서 canonical `ci.yml` 전체 gate를 다시 확인해 최종 상태로 사용한다.

## 6. 현재 phase

현재는 **false-supported safety closure → semantics restoration**을 계속한다.

복구 완료:

1. sparse same-timestamp actor transaction → RHQ certification 복구
2. lazy dynamic-rank first-read resolution → Miranda certification 복구

아직 fail-closed:

1. finite reference-stack capture
2. generic full-burst conditional permanent passive
3. broader producer/mutator dependency ownership

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 7. 다음 단일 체크포인트

**finite reference-stack capture semantics**

우선 Maid Mast / Tove / Arcana 계열 public surface를 다시 감사한다.

핵심 확인:

- `scaling == stack_count` / `scaling_ref`의 source stack을 Moris가 어느 시점에 capture하는가
- target effect activation 뒤 source stack 변화가 기존 effect magnitude를 바꾸는가
- finite duration / refresh / reactivation에서 capture가 다시 일어나는가
- source provider가 없거나 도달 불가능한 경우를 어떻게 fail-closed할 것인가

단순 blocker 제거가 아니라 실제 capture/live-reference semantics를 probe한 뒤 좁은 generic ownership으로 구현한다.

`레이드_볼륨` Scarlet `ammo_charge_pct` 마지막 visible blocker만 먼저 제거하는 것은 계속 보류한다. Maid Mast reference-stack 의미론이 아직 미소유이므로 그것만 열면 false certification 위험이 있다.

## 8. 작업공간 상태

- branch: `fast-engine-phase2-20260901`
- latest semantic: `cc11c5c08d907001ab6e7841c05da7f3179afa67`
- master: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- temporary workflow: 없음
- `.github/workflows`: `ci.yml`, `pages.yml`만 유지

이 문서 커밋 후 최신 branch HEAD와 canonical CI를 확인해 최종 clean gate로 기록한다.
