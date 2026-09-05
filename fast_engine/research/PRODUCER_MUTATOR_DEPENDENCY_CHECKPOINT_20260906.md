# Producer/Mutator Dependency Ownership Checkpoint — 2026-09-06

## 1. 목적

이번 체크포인트는 기존 scored-state remover fail-closed guard를 넓게 해제하지 않고,
Moris와 Fast의 provider/remover lifetime이 정확히 일치하는 public reachable pair만 좁게 소유하는 작업이다.

기준 safety commit은 다음과 같다.

- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — scored-state remover dependency fail-closed

이 guard는 유지한다. 이번 변경은 증명된 exact pair shape에만 예외를 추가한다.

## 2. Public `remove_named_buff` 전수 감사

현재 public corpus를 다시 빌드해 24 source / 23 unique ordered memberships를 감사했다.

- unique memberships: `23`
- `remove_named_buff` rows: `72`

대표 score-affecting 후보는 다음과 같았다.

- Little Mermaid `터진 거품 3` → enemy hit-count/state interaction
- Snow White : Heavy Arms `세븐스 드워프 V+VI 제거` → finite provider + on-attack removal
- Arcana : Fortune Mate `쌓여가는 사진첩 2` → `추억 남기기`
- Arcana : Fortune Mate `쌓여가는 사진첩 3` → `추억 남기기 3`
- Mast : Romantic Maid `파이레츠 스피릿 3` → multi-stack/conditional `취기`
- Anis : Star `스타 폴 4` → roster-static conditional `나만의 별`
- Grave `과열 I 제거` → hit-count provider + reload removal

marker-only 또는 이미 owned state operation인 remover는 기존대로 별도 blocker를 만들지 않는다.

## 3. 첫 public anchor 선정

처음에는 Arcana의 두 full-burst-end remover가 같은 family처럼 보였다.
Moris/compiled dependency를 분해한 결과 둘은 다르다.

### 3.1 `추억 남기기 3` pair — owned

Provider:

- owner: `아르카나 : 포츈 메이트`
- name: `추억 남기기 3`
- stat: `atk_dmg_pct +29.99`
- target: self
- duration: permanent (`-1`)
- max stack: `1`
- trigger: `burst_cast`

Remover:

- name: `쌓여가는 사진첩 3`
- stat: `remove_named_buff`
- target: self
- `target_effect: 추억 남기기 3`
- trigger: `full_burst_end`
- condition 없음

이 provider name을 관찰하는 state condition, `state_end` consumer, 다른 mutator, live scaling reference가 public squad에 없다.

### 3.2 `추억 남기기` pair — 계속 fail-closed

Provider:

- name: `추억 남기기`
- stat: `crit_rate +20.09`
- target: self
- permanent / max stack 1
- trigger: `burst_cast`

하지만 이 state를 Arcana의 다른 효과들이 직접 참조한다.

확인된 condition consumers:

- `청춘의 기록`
- `기억과 추억`
- `기억과 추억 2`
- `행복한 기억`
- `소중한 추억`

따라서 `쌓여가는 사진첩 2`를 지원하려면 remover 하나가 아니라 Arcana의 gauge/ammo/pellet/ATK state machine을 함께 소유해야 한다.
이번 체크포인트에서는 열지 않는다.

## 4. Moris lifetime / ordering

public `스쿼드3`의 Arcana를 사용해 Moris를 직접 추적했다.

30 s trace의 Arcana B2 cast:

- `3.1999999999999935`
- `15.733333333333695`
- `28.266666666666342`

full-burst end:

- `13.400000000000245`
- `25.93333333333314`

Moris에서 `추억 남기기 3`은 각 `burst_cast` timestamp에 즉시 활성화되고,
각 `full_burst_end` timestamp에 정확히 expire/removal된다.

이전 full-burst conditional passive log와 달리 여기에는 `DT=1/60` log delay가 없다.
remover notify 자체가 full-burst-end edge에서 실행된다.

Moris timeline ordering은 다음과 같다.

1. full-burst phase를 idle로 변경
2. `state["full_burst"] = False`
3. buff cache invalidate
4. roster order로 `full_burst_end` notify
5. Arcana remover가 같은 timestamp에서 named row 제거

Fast도 BurstMachine phase transition 후 `full_burst_end` signal을 dispatch하므로 같은 edge에 remover를 적용할 수 있다.

## 5. Moris global-name removal과 Fast target-scoped removal

Moris `remove_named_buff`는 active row에서 `effect.name == target_effect`인 row를 이름 기준으로 전역 제거한다.
Fast `ActiveEffectStore.remove_named_state()`는 target/name 범위에서 제거한다.

따라서 generic ownership 조건에 다음을 추가했다.

- provider name이 compiled squad 전체에서 정확히 하나일 것
- provider/remover가 같은 actor일 것
- 둘 다 self cohort일 것

이 조건에서 Moris global-name removal과 Fast self-target removal의 결과가 동일하다.
다중 provider 이름은 계속 fail-closed다.

## 6. 구현

semantic commit:

- `804cc1eff5ea4c2eac61e68771f8d17c174cb930` — `Fast: own full-burst-end named self removal`

### `fast_engine/engine/dispatcher.py`

새 generic predicate:

- `_full_burst_end_self_direct_remove_dependency_supported()`

현재 owned shape는 의도적으로 매우 좁다.

Remover:

- `instant`
- `remove_named_buff`
- self target
- no value/duration/stack/max-trigger/tick
- parameters exactly `target_effect`
- no conditions
- exactly one event trigger: `full_burst_end`

Provider:

- globally unique same name
- same actor / self target
- `buff`
- stat exactly `atk_dmg_pct`
- permanent
- max stack 1
- no parameters/conditions/max-trigger/tick
- exactly one event trigger: `burst_cast`
- existing direct-damage runtime support 필요

Dependency guard:

- `event:state_end:<name>` consumer 없음
- named state condition consumer 없음
- other `target_effect` mutator 없음
- live `scaling_ref` consumer 없음

Runtime에서는 exact owned remover만 executable로 인정하고,
`full_burst_end` dispatch 시 `remove_named_state(actor, name, now)`를 실행한다.

### `fast_engine/engine/score.py`

기존 `_unsupported_remove_named_buff_changes_scored_state()` fail-closed guard를 유지한다.
위 exact generic predicate가 true인 경우에만 blocker를 제거한다.

## 7. Regression tests

추가:

- `fast_engine/tests/test_damage_named_remove_dependency.py`

검증 항목:

1. real Arcana `쌓여가는 사진첩 3 → 추억 남기기 3` pair는 owned
2. `쌓여가는 사진첩 2 → 추억 남기기` state-machine neighbor는 fail-closed
3. Fast direct dispatcher에서 burst-cast activation → full-burst-end removal → next burst reactivation
4. Moris expire timestamp가 full-burst-end와 exact match
5. enemy-target neighbor fail-closed
6. conditioned remover fail-closed
7. on-attack remover fail-closed
8. finite provider fail-closed
9. duplicate provider fail-closed
10. named-state consumer 추가 시 fail-closed

기존 safety/full-burst/real-squad focused regressions도 함께 통과했다.

## 8. Promotion 결과

promotion run:

- run `33991961043`
- job `101375669685`

결과:

- Fast complete discovery: **292/292**
- structural 180 s median: **143.92 ms**
- samples: `[142.99, 147.06, 143.92]`
- events: `539`
- RHQ 30 s Moris/reference: `236373847.0`
- RHQ 30 s Fast: `236465053.42473748`
- relative error: `0.0003858566668650809` (~`+0.0386%`)

public frontier:

- source cases: `24`
- unique memberships: `23`
- certified: **2**
- gaps: **21**

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

blocker families:

- normal delivery `47`
- normal state `33`
- skill damage `27`
- skill-state delivery `49`
- weapon change `12`
- cadence `59`
- control `4`
- periodic grid `1`

직전 checkpoint 대비 정확한 변화:

- normal state `34 → 33`
- 나머지 blocker family unchanged
- certified `2 → 2`

감사상 새 generic predicate가 소유한 public remover는 정확히 하나다.

- `스쿼드3 / 아르카나 : 포츈 메이트 / 쌓여가는 사진첩 3 / 추억 남기기 3`

## 9. 이번 단계에서 열지 않은 것

다음은 계속 fail-closed다.

- Arcana `쌓여가는 사진첩 2 → 추억 남기기`
- Arcana의 다른 `쌓여가는 사진첩` removers
- Maid Mast `취기` multi-stack/conditional removal
- Snow White : Heavy Arms finite/on-attack removal
- Little Mermaid enemy hit-count removal
- Grave hit-count/reload removal
- duplicate-name providers
- finite expiry/refresh remover races
- state-end/named-state/live-reference consumers

## 10. 다음 단일 체크포인트

다음 후보는 **roster-static mutually-exclusive named-state producer/remover ownership**이다.

public anchor 후보:

- Anis : Star `나만의 별` provider / `스타 폴 4` remover

이 family는 `has_burst1_ally` / `no_burst1_ally`처럼 roster-static condition으로 provider/remover가 상호 배타적일 가능성이 있다.
다만 다음 작업에서도 먼저 Moris trace와 public dependency audit를 다시 수행하고,
상호 배타성과 same-timestamp ordering이 실제로 증명되는 경우에만 narrow generic ownership을 추가한다.

raw coverage expansion, optimizer production integration, global frame loop는 계속 보류한다.
