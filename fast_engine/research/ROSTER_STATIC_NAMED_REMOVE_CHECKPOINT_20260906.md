# Roster-static named-removal checkpoint — 2026-09-06

## 1. 목적

직전 producer/mutator checkpoint는 실제 실행되는 `remove_named_buff`의 첫 score-bearing pair를 소유했다.
이번 checkpoint는 반대 방향을 검증했다.

> remover 자체가 미지원이어도, compiled roster에서 그 조건이 전투 내내 거짓임을 증명할 수 있다면 score blocker로 남겨야 하는가?

첫 public anchor는 `아니스 : 스타`의 다음 pair였다.

- provider: `나만의 별`
- remover: `스타 폴 4`

결론은 **runtime remover 지원을 추가하지 않고, 정확히 증명 가능한 roster-static false condition에서만 score blocker를 제거**하는 것이다.

## 2. public 전수 감사

canonical public frontier 정의를 그대로 사용했다.

- `지그_*` source 제외
- 5인 squad만
- `test_*` fixture member 제외
- source cases: `24`
- unique memberships: `23`

roster형 조건이 붙은 `remove_named_buff`를 전수 추출하면 10 rows였다.

- 라피 : 레드 후드 `전투 보조 해제 -> 전투 보조`: 4
- 아니스 : 스타 `스타 폴 2 -> 모두의 별`: 3
- 아니스 : 스타 `스타 폴 4 -> 나만의 별`: 3

라피 쪽은 현재 score blocker가 아니므로 이번 변경 대상이 아니다.

아니스 : 스타가 등장하는 unique public membership은 정확히 세 개다.

1. `스쿼드5`
   - 아니스 : 스타 / 아르카나 / 이사벨 / 신데렐라 / 크라운
2. `레이드_앨리스브래디`
   - 아니스 : 스타 / 앵커 : 이노센트 메이드 / 마스트 : 로망틱 메이드 / 앨리스 / 브래디
3. `레이드_일레그`
   - 아니스 : 스타 / 크라운 / 일레그 : 붐 앤 쇼크 / 헬름 / 루드밀라 : 윈터 오너

세 roster 모두 아니스 자신을 제외한 B1 ally가 없고, 다른 actor의 `burst_stage_override:*` effect도 없다.

## 3. 왜 단순한 roster 검사만으로는 부족한가

Fast `ConditionEvaluator`의 `has_burst1_ally` / `no_burst1_ally`는 compiled `member.burst_stage`를 직접 보지 않는다.

실제 판정은 `BurstMachine.stage_for(actor)`를 사용한다.

`stage_for()`는 runtime `stage_override`가 있으면 그것을 우선하므로, 일반적으로 B1 존재 여부는 무조건 정적이라고 할 수 없다.

따라서 이번 proof는 다음을 모두 요구한다.

1. condition rule이 정확히 하나
2. mode가 `has_burst1_ally` 또는 `no_burst1_ally`
3. 조건 owner 외의 actor에게 `burst_stage_override:*` effect가 하나도 없음
4. 그때만 compiled roster의 burst stage로 조건의 참/거짓을 계산

다른 actor에 stage override 가능성이 하나라도 있으면 즉시 fail-closed한다.

`reenter` 자체를 owner 외 stage 변경으로 오인해 일반화하지도 않았다. 이번 helper는 오직 실제 `burst_stage_override:*` stat 존재 여부를 보수적으로 검사한다.

## 4. 아니스 : 스타 exact shapes

### `나만의 별`

- effect type: `buff`
- stat: `atk_pct`
- value: `40.01`
- target: self
- duration: `-1`
- max stack: `1`
- condition: `no_burst1_ally`
- triggers:
  - `battle_start`
  - `full_burst_end`

### `스타 폴 4`

- effect type: `instant`
- stat: `remove_named_buff`
- target: self
- `target_effect = 나만의 별`
- condition: `has_burst1_ally`
- triggers:
  - `battle_start`
  - `full_burst_end`

두 effect의 조건은 동일한 B1 상태에 대해 정확히 상보적이다.

`나만의 별`에는 state consumer도 존재한다.

- `스타더스트` — `atk_caster_based_pct`, `self_state:나만의 별`
- `스타 아니스` — `atk_dmg_pct`, `self_state:나만의 별`

따라서 `스타 폴 4`가 실제 reachable한 roster라면 단순 no-op remover로 일반 지원해서는 안 된다. 이번 slice는 **remover가 false임을 증명하는 경우만** 다룬다.

## 5. Moris trace

### public 세 roster

세 public roster 모두 `나만의 별`만 활성화되고 `모두의 별`은 활성화되지 않았다.

`레이드_앨리스브래디` 30 s 예시:

- `나만의 별` activate: `0.0`
- full-burst end: `13.400000000000245`
- 같은 timestamp `나만의 별` activate/refresh
- full-burst end: `25.93333333333314`
- 같은 timestamp `나만의 별` activate/refresh

`나만의 별` expire/removal event는 없다.

`스쿼드5`에서도 `0.0`, `8.399999999999997`, `20.8000000000001`, `28.333333333333005`에 활성화되며 후자의 세 시각은 각각 full-burst end와 정확히 같다.

즉 public no-B1 roster에서 `스타 폴 4`는 provider를 제거하지 않는다.

### B1 control

대조 roster:

- 아니스 : 스타
- 리틀 머메이드
- 이사벨
- 신데렐라
- 크라운

여기서는 리틀 머메이드가 고정 B1이고 다른 actor의 stage override effect는 없다.

조건은 정확히 반전됐다.

- `나만의 별 / 스타 폴 2`의 `no_burst1_ally` = false
- `모두의 별 / 스타 폴 4`의 `has_burst1_ally` = true

Moris에서는 `나만의 별`이 한 번도 생기지 않고 `모두의 별`만 활성화됐다.
`모두의 별`의 `burst_stage_override:reenter1`에 따라 실제 reenter:1 burst도 관찰됐다.

따라서 두 branch의 mutual exclusion은 Moris trace에서도 확인된다.

## 6. production 구현

semantic commit:

- `969b75c4ade19c8e2eea1951f38c5d76df4ced62`
- `Fast: prove roster-static named removal unreachable`

`fast_engine/engine/score.py`에
`_roster_static_burst1_condition_unreachable()`를 추가했다.

이 helper는 위의 정적 proof가 성립하고 현재 compiled roster에서 condition이 false일 때만 true를 반환한다.

`_unsupported_remove_named_buff_changes_scored_state()`는 이 경우 remover dependency blocker를 만들지 않는다.

중요하게도 다음은 변경하지 않았다.

- `TriggerDispatcher` runtime executable surface
- `remove_named_buff` runtime semantics
- BurstMachine
- global frame loop
- named-state consumer semantics

즉 **미지원 remover를 실행 가능하게 만든 것이 아니라, 실행 불가능함이 증명된 compiled roster에서만 score dependency를 제거했다.**

## 7. regression tests

신규:

- `fast_engine/tests/test_damage_roster_static_named_remove.py`

5개 계약을 고정했다.

1. public 아니스 3 membership에서 `스타 폴 4`가 unreachable이고 해당 normal-state blocker만 사라짐
2. 같은 roster의 상보 `스타 폴 2:no_burst1_ally`는 reachable
3. B1 control roster에서는 두 branch 판정이 정확히 반전
4. 다른 actor에 `burst_stage_override:*` 가능성을 주입하면 static proof가 즉시 fail-closed
5. Moris public/control trace에서 `나만의 별` / `모두의 별`의 상호배타성이 실제로 성립

focused regression은 semantic promotion 전에 통과했다.

## 8. public frontier 결과

직전:

- normal state `33`

이번:

- normal state `30`

제거된 blocker는 정확히 다음 3개 membership의 동일 의미 blocker다.

- `스쿼드5`
- `레이드_앨리스브래디`
- `레이드_일레그`

각각:

`normal_state:아니스 : 스타:스타 폴 4:remove_named_buff`

다른 family는 모두 unchanged다.

- normal delivery `47`
- normal state `30`
- skill damage `27`
- skill-state delivery `49`
- weapon change `12`
- cadence `59`
- control `4`
- periodic grid `1`

certified도 그대로다.

- source cases `24`
- unique memberships `23`
- certified `2`
- gaps `21`

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

아니스 membership들은 다른 blocker가 남아 있어 premature certification이 발생하지 않았다.

## 9. promotion gate

promotion run:

- run `33996858664`
- job `101388805370`

결과:

- public frontier exact assertion: success
- Fast complete discovery: **297/297**
- 180 s structural median: `159.57 ms`
- samples: `[158.71, 162.0, 159.57]`
- events: `539`
- RHQ Moris/reference: `236373847.0`
- RHQ Fast: `236465053.42473748`
- relative error: `0.0003858566668650809` (~`+0.0386%`)

## 10. 안전 경계

계속 fail-closed:

- 실제 reachable인 conditional named remover
- 다른 actor의 burst-stage override가 존재하는 B1 condition
- 복수 condition 조합
- finite expiry/refresh와 remover race
- duplicate provider ambiguity
- multi-stack / hit-count / on-attack remover
- Arcana `추억 남기기` state-machine family
- Maid Mast `취기` / `파이레츠 스피릿 3` conditional multi-stack family

## 11. 다음 단일 체크포인트

**Maid Mast conditional multi-stack named-removal semantics**

public anchor:

- `마스트 : 로망틱 메이드`
- `파이레츠 스피릿 3:remove_named_buff`
- target state family: `취기`

다음에는 먼저 다음을 직접 감사한다.

1. `취기` provider의 실제 stack producer와 max-stack lifecycle
2. remover condition이 언제 reachable한가
3. removal timestamp가 shot / reload / full-burst edge와 겹칠 때 Moris ordering
4. `취기`가 accuracy/cadence/score planning에 주는 영향
5. named-state consumer와 multi-provider ambiguity
6. finite/reference interactions

이 family는 단순 remover executable 여부만으로 열지 않는다. score planning까지 포함해 exact semantics가 증명된 범위만 소유한다.

raw coverage expansion, optimizer production integration, global frame loop는 계속 보류한다.
