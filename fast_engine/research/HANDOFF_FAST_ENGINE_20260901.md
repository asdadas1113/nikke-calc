# Fast Engine 작업 인계 — 2026-09-01

## 0. 새 채팅에서 가장 먼저 할 일

이 문서를 읽은 뒤 **`fast-engine-phase2-20260901` 브랜치에서만** 이어서 작업한다.
`master`는 병합/수정하지 않는다.

저장소: `asdadas1113/nikke-calc`

마지막으로 확인한 `master` SHA:

`fb2fd9157aa14499daf6b9f185beb685d4393f90`

이번 인계 직전 spawn lifecycle 구현 코드 기준점:

`f2c9c9caa3ade8c1932dafc4e2340aba4481879c`

이 문서 자체가 그 뒤에 추가되므로 실제 작업 시작 시에는 branch tip을 다시 확인한다.

---

## 1. Fast Engine의 목적과 우선순위

Fast Engine은 Moris 전투를 프레임 단위로 그대로 복제하는 엔진이 아니다.
최적화 후보를 싸게 거르기 위한 비교 엔진이며 우선순위는 다음과 같다.

1. throughput
2. Moris Top-N recall in Fast Top-K
3. catastrophic false-negative avoidance
4. stable ordering
5. absolute accuracy

핵심 설계 제약:

- 전역 60fps 루프 금지
- 전역 per-bullet 이벤트 금지
- event-driven / compressed threshold-boundary scheduling 유지
- `calculator/` Moris 구현이 의미론적 기준이다
- Fast에 맞추기 위해 Moris를 수정하지 않는다
- 비교에 중요한 미지원 상태가 있으면 fail closed 한다
- `blocked` / `unsupported`는 coverage gap이지 numeric false negative가 아니다
- 미지원 메커니즘이 있는 Fast subtotal을 인증된 점수로 취급하지 않는다

후보군 분석 시 반드시 다음 층을 분리한다.

`source universe → candidate generation → Fast coverage → Fast ranking → Moris shortlist`

Fast parity/root-cause를 볼 때는 optimizer 후보생성을 우회하고 고정 스쿼드·공통 시나리오로 측정한다.

---

## 2. 현재 가장 강한 parity 기준점

고정 실스쿼드:

- 미란다
- 브리드 : 사일런트 트랙
- 헬름
- 루주
- 미하라 : 본딩 체인

공통 조건:

- duration 180s
- first_burst_time 3s
- rng expected
- enemy DEF 31784
- element/core/parts/windows 없음
- optimizer candidate generation 우회
- snapshot별 condition/build override 배제
- manual control은 Moris/Fast 양쪽에서 동일하게 제거

최근 측정:

- Moris 총딜 ≈ 2.4320B
- Fast 총딜 ≈ 2.4101B
- 총 상대오차 **-0.90%**
- `blockers=[]`
- `unsupported=[]`
- 해당 stateful 경로 속도 약 **11.7×**

캐릭터별 상대오차:

- 미란다 -1.25%
- 브리드 -1.46%
- 미하라 -1.65%
- 헬름 +1.97%
- 루주 -5.31%

해석:

- 이 한 케이스에서는 실제 스킬 체인까지 포함해 Fast가 Moris에 매우 근접한다.
- 그러나 **일반적 parity를 선언한 것은 아니다.** 공개 corpus는 아직 coverage gap이 많다.

---

## 3. 이미 해결된 주요 메커니즘

### 3.1 Full Burst 종료 lifecycle ordering

과거 Fast는 `FULL_BURST_END` signal을 반환하기 전에 `burst_casted` 상태를 초기화했다.
그 결과 `full_burst_end + burst_casted` 조건이 항상 false가 되는 구조적 버그가 있었다.

수정:

- 같은 시간의 `BURST_END_FINALIZE` 경계를 추가
- `full_burst_end` 효과를 cast flag가 살아 있는 상태에서 dispatch
- 그 뒤 finalize에서 cast flag 초기화

미하라 `바디 컨텍 2` 재충전 및 관련 체인이 이 수정으로 정상화됐다.

### 3.2 미하라 상태/DoT/gauge 체인

지원된 핵심 의미론:

- lifecycle/burst gauge charge/consume
- stack-count scaling damage
- named stacked DoT
- DoT scaling-ref capture
- debuff stack add/remove
- named-state removal
- permanent DoT timer를 한 의미 있는 tick씩 스케줄

미하라 체인 physical count는 Moris와 거의 동일 수준까지 맞춰졌고 이후 평타/cadence 보정까지 거쳐 위의 -0.90% 실스쿼드 parity에 도달했다.

### 3.3 헬름 10발 bullet lifetime

`이지스 캐논 3` 계열의 `duration_bullets: 10` 의미를 지원한다.

인증된 의미:

- 발동 후 실제 recipient shot 10발에 적용
- 10번째 발은 버프 적용 상태로 피해 계산
- 해당 발 이후 post-shot expiry
- 재발동하면 다시 10발 lifetime으로 갱신

다만 recipient cadence가 전투 중 바뀔 수 있으면 정확한 10번째 발 시각을 static plan으로 확정할 수 없으므로 fail closed를 유지한다.

---

## 4. 공개 24팀 audit 상태

표준 audit은 `context.snapshot.SQUADS`에서 **팀 멤버십만** 가져오고,
공통 public defaults/config/enemy를 재구성한다.
optimizer 후보생성은 우회한다.

관련 기존 보고서:

`fast_engine/research/PUBLIC_RANKING_AUDIT_20260901.md`

spawn lifecycle 구현 직전 가장 최근 재실행 결과:

- **0 / 24 certified**

이 결과는 위의 실스쿼드 -0.90%와 모순되지 않는다.
공개 24팀에는 아직 Fast가 의도적으로 차단하는 HP/heal/cadence/control/state 메커니즘이 다수 포함되어 있다.

따라서 24팀 coverage가 낮다고 fail-closed gate를 느슨하게 만들지 않는다.

---

## 5. 공개 팀에서 직접 확인한 주요 blocker

### 5.1 헬름 10발 버프 + live cadence — 정당한 차단

공개 예시 팀:

- 리틀 머메이드
- 크라운
- 라피 : 레드 후드
- 미하라 : 본딩 체인
- 헬름

이 팀에서 헬름 `이지스 캐논 3`이 다시 막히는 이유는 실제 recipient cadence가 바뀌기 때문이다.

확인된 효과:

- 리틀 머메이드 `세이렌 송 2`
  - `ammo_charge_pct`
  - target `all_allies`
  - `burst_cast`
- 크라운 `원 포 올 2`
  - `reload_speed_pct`
  - target `all_allies`
  - duration 15s
  - `full_burst_start`

둘 다 헬름 자신의 10번째 발 시각을 실제로 바꿀 수 있다.
따라서 이 공개 팀의 bullet-lifetime 차단은 과차단이라고 볼 수 없다.

참고:
현재 generic helper에는 다른 actor의 self-only cadence까지 보수적으로 볼 가능성이 남아 있지만,
**이 공개 헬름 사례의 원인은 그것이 아니다.** 별도의 깨끗한 반례가 나오기 전에는 수정하지 않는다.

### 5.2 크라운 `로얄 에타이어 4 : atk_dmg_pct` — HP/heal 모델 필요

효과:

- buff
- `atk_dmg_pct +20.99%`
- duration 7s
- target `all_allies`
- trigger `event:heal_received`
- condition 없음

Fast에서 막히는 직접 원인은 `heal_received` event producer 부재다.

Moris는 실제 회복이 적용될 때 `event:heal_received`를 발생시킨다.
공개 예시 팀에는 실제 도달 가능한 회복원이 있다.

- 크라운 `로얄 에타이어 3`: `heal_hp_pct`
- 헬름 `진두지휘 2`: `full_charge_hit → all_allies heal_hp_pct 0.59%`
- 헬름 `이지스 캐논 2`: `burst_cast → all_allies lifesteal_pct 54.45% / 10s`

따라서 이 blocker를 단순 whitelist 또는 patternless-unreachable로 제거하면 안 된다.
정확히 지원하려면 HP/heal/lifesteal → heal_received event production을 구현해야 한다.
현재는 범위가 큰 후속 작업으로 보류한다.

---

## 6. 이번 마지막 체크포인트: static enemy/target spawn lifecycle

Little Mermaid `거품`을 조사한 결과:

- source `스킬2`
- buff
- stat `received_dmg_pct`
- value **5.05**
- duration **-1**
- target `enemy`
- condition 없음
- trigger `event:enemy_spawn`

기존 blocker:

- `normal_delivery:리틀 머메이드:거품:received_dmg_pct`
- `skill_state_delivery:리틀 머메이드:거품:received_dmg_pct`

원인은 계산식이나 target이 아니라 Fast가 `event:enemy_spawn`을 생산하지 않았기 때문이다.

Moris `BuffManager.battle_start()`의 순서:

1. roster 전체 `battle_start`
2. roster 순서대로 각 actor에 대해
   - `event:enemy_spawn`
   - `event:target_spawn`

Fast에 이번 체크포인트에서 같은 정적 lifecycle을 추가했다.

구현:

- `fast_engine/engine/damage_policy.py`
  - direct damage-state timing에서 **정확히** `event:enemy_spawn`, `event:target_spawn`만 허용
  - `event:*` 전체를 열지 않음
- `fast_engine/engine/burst_runtime.py`
  - 모든 `battle_start` dispatch 이후
  - actor 순서대로 `enemy_spawn → target_spawn` pair를 t=0에 dispatch
- `fast_engine/tests/test_damage_spawn_lifecycle.py`
  - Little Mermaid `거품`이 runtime-supported가 되는지
  - 해당 blocker 2개가 사라지는지
  - t=0 spawn에서 정확히 1회 activation 되는지
  - enemy `received_dmg_pct == 5.05`인지 회귀 테스트

이 구현은 Little Mermaid 전용 특례가 아니라 현재 Fast의 **정적 단일 적 시작 lifecycle 계약**이다.

새 채팅 시작 시 이 체크포인트의 최신 CI 결과를 먼저 확인한다.

---

## 7. 다음 작업 권장 순서

### 다음 단일 체크포인트

spawn lifecycle clean HEAD가 전체 CI green인지 확인한 뒤,
**표준 public 24-team audit를 한 번만 재실행**한다.

목적은 ranking 결론을 내는 것이 아니라:

1. Little Mermaid `거품` blocker가 실제 corpus에서 제거됐는지
2. certified 팀 수가 변했는지
3. 다음 최빈 blocker가 무엇인지

만 확인하는 것이다.

그 다음에는 가장 빈도가 높으면서 **작은 독립 메커니즘**부터 처리한다.

`heal_received`처럼 HP/heal 모델 전체가 필요한 항목은 작은 blocker보다 먼저 억지로 구현하지 않는다.

### 아직 하지 말 것

- 24팀이 모두 막힌다는 이유로 fail-closed를 완화하지 말 것
- optimizer 후보생성/랭킹 문제로 결론을 점프하지 말 것
- snapshot의 개별 build/condition을 공통 audit에 섞지 말 것
- Moris `calculator/`를 Fast parity를 위해 수정하지 말 것
- 한 실스쿼드 -0.90%를 전체 캐릭터 parity로 일반화하지 말 것

---

## 8. 새 채팅에 전달할 최소 프롬프트

다음처럼 요청하면 된다.

> GitHub `asdadas1113/nikke-calc`의 `fast-engine-phase2-20260901` 브랜치에서 `fast_engine/research/HANDOFF_FAST_ENGINE_20260901.md`를 먼저 읽고 Fast Engine 작업을 이어서 진행해줘. master는 수정/병합하지 말고, handoff에 적힌 다음 단일 체크포인트부터 진행해줘.
