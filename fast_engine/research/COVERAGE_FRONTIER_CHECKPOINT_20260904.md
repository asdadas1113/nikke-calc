# Fast Engine coverage frontier checkpoint — 2026-09-04

## 1. 목적

certified pair의 static ranking hard case가 닫힌 뒤, 표준 public universe의 21 coverage gap을 다시 mechanic 기준으로 분류하고 첫 coverage 확장 대상을 고른 기록이다.

고정 조건:

- source public cases: 24
- exact ordered-membership dedupe: 23
- 기존 certified memberships: 2
- 기존 coverage gaps: 21
- candidate generation은 우회
- unsupported comparison-critical mechanic은 계속 fail closed
- character-name hack / fitted coefficient / global 1/60 loop 없음

## 2. frontier 재분류

상위 conceptual blocker pressure는 다음과 같았다.

- Crown `로얄 에타이어 4` atk_dmg_pct: 7 unique teams
- Little Mermaid `거품 난사` sequential damage: 6
- Mokdan `정정당당 승부다!` weapon change: 5
- Privaty `EX 매거진 2` reload speed: 4
- Privaty `EX 매거진 3` max ammo: 4
- Privaty `LD 어설트 2/3` bonus damage: 4
- Mast `파이레츠 스피릿 2` reload speed: 4

stat 이름만 묶으면 atk_dmg_pct/reload/max-ammo 등이 더 넓어 보이지만, 동일 stat이라도 trigger/condition/recipient safety가 다르면 하나의 mechanic으로 취급하지 않았다.

## 3. 보류 — Crown heal_received

Crown `로얄 에타이어 4`의 실제 미지원 핵심은 `event:heal_received` chronology다.

HP/heal event chronology를 새로 열지 않고 단지 atk_dmg_pct라는 이유로 지원하면 comparison-critical state를 잘못 인증할 수 있으므로 기존 보류를 유지한다.

## 4. 보류 — squad_ammo_consume

Little Mermaid `거품 난사`는 다음까지 확인했다.

- damage shape: `sequential_damage:10`
- value: 85%
- target `enemies_random`은 Fast에서 static ENEMY로 이미 정상 compile
- dynamic scaling parameter 없음
- 실제 blocker는 `squad_ammo_consume:500`

같은 캐릭터의 `버블 오더 4` (`squad_ammo_consume:400`)는 Moris-NOP이므로 실질 comparison-critical consumer는 `거품 난사`다.

그러나 real `스쿼드1` 180초 shot stream 비교에서:

- Moris squad ammo consume total: 34,587
- Fast physical shot total: 34,476
- total count difference: 약 0.32%

500-shot threshold는 대부분 수십~수백 ms 차이였지만 일부 reload/cadence 구간에서 Fast crossing이 약 +0.6~0.7초 늦어졌다가 이후 다시 회복했다.

따라서 team-global ammo crossing은 현재 individual cadence 근사 오차를 증폭한다. 이 상태에서 `squad_ammo_consume`를 certified delivery로 여는 것은 fail-closed 원칙에 맞지 않아 보류했다.

## 5. 보류 — bonus_damage를 하나의 family로 취급

public `bonus_damage` blocker를 전수 비교한 결과 하나의 generic mechanic이 아니었다.

남은 주요 shape:

- Privaty: `last_bullet`
- Isabel: conditional pending B3 ordering
- Cinderella: same-target + stack-count scaling
- Asuka: state-end + enemy-stack scaling

따라서 `bonus_damage` 전체를 broad-enable하지 않았다.

## 6. cadence reload/max-ammo 진단

Fast에는 live reload/max-ammo runtime 자체가 이미 존재한다.

public blocker의 상당수는 수학/기능 부재가 아니라 buff recipient 중 하나가 다른 이유로 cadence-safe하지 않아서 발생했다.

대표 원인:

- Mokdan / Nayuta / Modernia weapon change
- Alice control
- 일부 charge/control/count-event actor

따라서 reload/max-ammo를 broad-enable하는 것도 이번 첫 mechanic으로 선택하지 않았다.

## 7. 채택 — post-shot `last_bullet` damage delivery

Privaty `LD 어설트 2/3`를 조사하면서 가장 작은 generic gap을 확인했다.

Fast에는 이미:

- static last-bullet boundary scheduler
- dynamic rapid magazine-final-shot boundary
- post-shot `last_bullet` dispatch
- `last_bullet_fire`와 `last_bullet`의 분리

가 구현되어 있었다.

빠진 것은 `SimpleDamageScoreSink`가 `last_bullet` event를 safe delivery key로 인정하는 한 줄뿐이었다.

### Moris parity probe

실제 Privaty, burst 없음, 35초:

- Moris LD 어설트 2 activations: 6
- Fast explicit static-boundary activations: 6
- LD 어설트 3: 양쪽 0
- 각 LD2 damage relative error: 약 -0.00006991%

첫 경계:

- Moris 4.933333333333s
- Fast continuous boundary 4.916666666667s
- damage Moris 380,633
- Fast 380,632.733909

후반의 timestamp drift는 기존 continuous-cadence approximation이며 damage-delivery 의미론 자체와는 분리했다.

### named-state gating probe

Privaty `burst_cast`로 enemy named state `타겟 지정`을 생성한 뒤:

- t=3.1: state active, LD3 fires once
- t=13.1: 10s duration expired, state inactive, LD3 does not fire again

즉 `target_state:타겟 지정` 조건도 기존 runtime state semantics와 결합해 정상 동작했다.

## 8. permanent change

Runtime:

- `46af96866b9462ec22455b9c9f5121cfa3b35bdd` — `fix: support last-bullet damage delivery`
- 실제 `fast_engine/engine/damage_runtime.py` diff는 `_SAFE_EVENT_KEYS`에 `"last_bullet"` 1줄 추가뿐이다.

Regression:

- `4a3d6f1378f482d41d6bcc8676150509a91d2474` — `test: cover last-bullet damage delivery`

추가 regression은 실제 Privaty LD2/LD3가 damage sink에서 지원되는지, named enemy state가 활성일 때만 LD3가 발동하는지 고정한다.

기존 dynamic last-bullet regression과 함께 magazine final physical shot 이후 정확히 한 번 dispatch되는 계약을 유지한다.

## 9. focused validation

다음 8개 last-bullet 관련 테스트가 모두 통과했다.

- `fast_engine.tests.test_damage_last_bullet` 4 tests
- `fast_engine.tests.test_dynamic_last_bullet_boundary` 4 tests

public blocker scan 결과:

- source 24
- unique memberships 23
- certified 2
- gaps 21
- Privaty `LD 어설트 2/3` blocker count: 0

즉 네 public team에서 LD2/LD3 skill-damage blockers가 제거됐지만, 해당 팀들은 다른 cadence/weapon/control blockers가 남아 있어 certified membership 수는 아직 증가하지 않았다.

영향 public teams:

- `스쿼드2`
- `레이드_라피앨리스`
- `레이드_아니스서머메이든`
- `레이드_트리나홍련`

## 10. 다음 재개 지점

다음 mechanic은 단순 stat 빈도로 고르지 않는다.

이미 보류 근거가 있는 다음 축은 그대로 건너뛴다.

- Crown heal chronology
- Little Mermaid squad-ammo chronology
- broad weapon-change
- reload/max-ammo recipient safety를 무시한 broad enable

다음에는 남은 repeated damage-delivery blockers를 trigger/target/condition shape로 다시 묶어, **같은 미지원 root cause를 공유하면서 HP chronology나 weapon replacement를 새로 요구하지 않는 작은 generic slice**를 찾는다.

새 mechanic마다 순서는 동일하게 유지한다.

1. real effect shape probe
2. Moris semantic/parity probe
3. 최소 generic implementation
4. focused regression
5. standardized public blocker scan
6. coverage가 실제 증가하면 ranking validation 재실행

optimizer production integration은 아직 하지 않는다.
## 11. 후속 채택 — finite state-end enemy-stack damage

`레이드_델타` Asuka `섬멸`을 좁은 generic slice로 채택했다. Moris/Fast 모두 첫 `섬멸 태세` 종료 약 `12.35s`에서 `안티 AT 필드` 30 stack을 읽어 damage를 계산한 뒤 같은 timestamp에 stack을 0으로 제거한다.

정식 commit은 `68d8dea58e4b05a630fc1d6545dcb905a7c7cfa8`. 지원 범위는 unique finite SELF state-end producer + same-actor finite harmful enemy `received_dmg_pct` named stack + exact stack-count `bonus_damage`/same-event removal로 제한하며 broad named-event/enemy-stack support는 계속 fail closed다.

`섬멸` 절대 damage 오차는 `+6.97%`, 같은 Asuka의 기존 비-섬멸 damage 오차는 `+8.29%`여서 global `bonus_damage` 수식은 수정하지 않았다. focused 12/12, DEF55 near-tie, release validation `33830517337`, canonical CI `33830517342` golden 29/29가 통과했다.

public은 source24 / unique23 / certified2 / gaps21 그대로이며 `레이드_델타`에는 Little Mermaid `거품 난사`만 남았다. 다음 탐색에서도 squad-ammo chronology, Nayuta cross-class weapon change, HP chronology는 보류한다.
