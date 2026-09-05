# Fast Engine lazy dynamic-rank target 체크포인트 — 2026-09-06

## 1. 목적

false-supported 안전성 감사에서 철회했던 `컨트롤_미란다미하라` 인증을 실제 Moris lazy rank target 의미론 소유로 복구한다.

대상 public anchor:

- 미란다 `파워 업!` — `atk_pct`, `allies_top_atk_excl:2`
- 미란다 `파워 업! 2` — `crit_dmg`, 같은 selector

기존 Fast는 effect activation 순간 `TargetResolver.resolve()`를 호출했다. Moris는 dynamic rank target을 `target_chars=None`으로 활성화한 뒤 첫 실제 buff read에서 target을 resolve한다. 따라서 같은 activation 뒤 target 확정 전까지 적용된 ATK mutation을 반영해야 한다.

## 2. Moris 의미론

Moris `BuffManager`의 lazy selector는 activation 시 concrete target을 저장하지 않는다.

첫 `get_buffs()`에서 `_resolve_lazy()`가 호출되며 cohort identity는 다음으로 공유된다.

- caster
- activation time
- exact raw target selector

실제 ATK 순위는 resolve 시점의 live state로 계산된다. unresolved lazy buff 자신은 아직 concrete target이 없으므로 그 순위 계산에 끼어들지 않는다.

즉 필요한 semantics는 event 순서 재배치가 아니라 **activation identity를 보존한 first-read target snapshot**이다.

## 3. 구현

production semantic commit:

- `cc11c5c08d907001ab6e7841c05da7f3179afa67` — `Fast: own lazy dynamic-rank target resolution`

### 3.1 pending target state

`ActiveEffectStore`에 아직 concrete recipient가 없는 pending rank effect를 보관한다.

- activation time / expiry를 원래 시각으로 유지
- 첫 해당 stat 조회 때만 materialize
- 이미 resolved된 같은 effect가 재활성화되면 Moris처럼 기존 cohort를 유지해 refresh
- pending activation 시 가능한 ally EFFECT cache를 보수적으로 invalidate

### 3.2 live ATK ranking과 cohort identity 분리

`TargetResolver`는 optional `selection_time`을 받아:

- cache identity는 activation time 사용
- 실제 rank 값은 first-read `now`의 live ATK 사용

따라서 같은 caster + activation time + raw selector sibling은 query 순서와 무관하게 같은 cohort를 공유한다.

### 3.3 self-resolution 방지

rank를 계산하는 `effective_atk()` 동안 unresolved rank buffs를 materialize하지 않는다. Moris의 `target_chars=None` 상태와 동일하게 자기 자신의 아직 미확정 ATK buff가 자기 target 선정에 영향을 주지 않는다.

### 3.4 좁은 지원 범위

이번 ownership은 다음 shape만 연다.

- dynamic ATK-rank target mode
  - `TOP_ATK`
  - `TOP_ATK_EXCL_SELF`
  - `LOWEST_ATK_BURST3`
- direct-damage state buff
- `max_stack == 1`
- `max_trigger is None`
- `tick_interval is None`
- `duration_bullets` 없음
- recipient-scoped named-event가 아님
- runtime condition 없음
- effect name을 concrete target state/event consumer가 요구하지 않음

따라서 미란다 `웨이크업! 4`의 `duration_bullets:1` lifetime path는 이번 slice로 넓히지 않았다. 기존 owned immediate bullet-lifetime 경로를 유지한다.

## 4. 회귀 검증

focused regression에서 다음을 고정했다.

1. rank buff가 같은 event의 큰 ATK mutation보다 먼저 activation되어도 first read에서 mutation 후 target을 선택
2. 같은 caster/time/raw selector sibling을 역순으로 query해도 동일 cohort 공유
3. activation identity와 later query time 분리
4. 실제 `컨트롤_미란다미하라` blockers가 빈 tuple로 복구
5. 기존 rapid cover control과 함께 certification 가능
6. 방어력 55,000 near-tie 180초 비교에서 Moris/Fast 순서와 오차 계약 복구

pre-promotion validation run:

- workflow `33983062877`
- job `101351627750`
- focused suites: success
- full Fast discovery: **279/279**
- structural median 약 **180.66 ms**, events `539`
- RHQ 30초 기존 parity도 유지: relative error 약 `+0.0386%`

## 5. public frontier

semantic commit 기준:

- unique ordered memberships: **23**
- certified: **2**
- gaps: **21**

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

fresh blocker families:

- normal state: **34**
- normal delivery: **55**
- skill-state delivery: **62**
- skill damage: **27**
- cadence: **62**
- weapon change: **12**
- control: **4**
- periodic grid: **1**

rank timing guard를 전역 삭제한 것이 아니라, 위 narrow lazy-owned shape만 guard에서 제외했다.

## 6. 작업공간

- branch: `fast-engine-phase2-20260901`
- latest semantic: `cc11c5c08d907001ab6e7841c05da7f3179afa67`
- `master`: 수정/병합하지 않음
- temporary workflow 4개: semantic commit에서 전부 제거
- `.github/workflows`: `ci.yml`, `pages.yml`만 유지

## 7. 다음 단일 체크포인트

**finite reference-stack capture semantics**

우선 Maid Mast / Tove / Arcana 계열 public surface를 다시 감사한다. `scaling == stack_count` / `scaling_ref`를 단순 blocker 제거하지 말고, Moris가 source stack을 어느 시점에 capture하고 이후 provider stack 변화와 독립적인지 또는 live reference인지부터 직접 probe한다.

`레이드_볼륨`의 Scarlet `ammo_charge_pct` 마지막 visible blocker만 먼저 제거하는 작업은 계속 보류한다. Maid Mast reference-stack 의미론 소유 전에는 거짓 인증 위험이 있다.
