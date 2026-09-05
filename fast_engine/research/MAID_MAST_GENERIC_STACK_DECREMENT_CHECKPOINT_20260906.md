# Maid Mast / Anchor generic harmful-stack decrement 체크포인트 — 2026-09-06

## 0. 결론

이번 체크포인트에서는 `마스트 : 로망틱 메이드`의 `파이레츠 스피릿 3:remove_named_buff`를 일반적으로 지원하지 않았다.

대신 public roster를 Moris로 추적해, `앵커 : 이노센트 메이드`가 함께 있는 3개 조합에서는 세 번째 full burst부터 Anchor의 범용 harmful-stack 감소가 `취기`를 `3 → 2`로 내리기 때문에 Maid Mast의 `self_stack_at_least:취기:3` full-burst-end branch 자체가 도달 불가능함을 증명했다.

Fast는 이 exact generic decrement slice를 실제 runtime 의미론으로 소유하고, 그 결과에 한해서 Maid Mast remover blocker를 제거한다.

Anchor가 없는 2개 public Maid Mast 조합에서는 `취기` 3스택이 full-burst end까지 유지되고 `숙취`와 `파이레츠 스피릿 3`이 실제로 발동하므로 계속 fail-closed다.

## 1. public Maid Mast surface

canonical frontier에서 Maid Mast가 포함된 source membership은 5개다.

Anchor 포함:

- `스쿼드4`
- `레이드_앨리스브래디`
- `레이드_볼륨`

Anchor 없음:

- `레이드_루주`
- `레이드_브리드디젤`

Maid Mast state family의 핵심 compiled shape:

### `취기`

- type: buff
- stat: `accuracy_pct -20`
- polarity: harmful
- target: self
- duration: permanent (`-1`)
- max stack: `3`
- trigger: `burst_enter:1`

Fast의 damage term resolver는 `accuracy_pct`를 실제 core-hit probability에 사용하므로 `취기`는 marker-only state가 아니다. stack 값이 틀리면 실제 score가 달라질 수 있다.

### finite reference consumers

`취기` stack을 참조하는 기존 owned consumer:

- `파이레츠 스피릿`
- `파이레츠 스피릿 2`
- `파이레츠 로망 3`

기존 finite-reference capture checkpoint에서 activation-time stack capture 자체는 이미 소유했다.

### stack-3 full-burst-end consumers

- `숙취` — self stun 10초
- `파이레츠 스피릿 3` — `remove_named_buff`, target `취기`

둘 다 `full_burst_end` + `self_stack_at_least:취기:3` 조건이다.

## 2. Moris generic stack mutation semantics

`calculator/buff_manager.py`를 직접 추적했다.

Moris에서 target-less `debuff_stack_remove`는:

1. selected target cohort의 active effect를 순회한다.
2. polarity가 harmful인 buff만 본다.
3. `max_stack > 1`인 stackable buff만 본다.
4. 지정 수치만큼 stack을 감소시킨다.
5. generic path에서는 live stack을 1 아래로 내리지 않는다.

즉 named removal과 다르다. generic decrement는 state 자체를 제거하지 않고 minimum 1 stack을 유지한다.

## 3. Anchor가 만드는 실제 `취기` 3 → 2

Anchor effect:

`앵커 : 이노센트 메이드 / 불가사리(모양) 오므라이스 3`

compiled shape:

- instant `debuff_stack_remove`
- target: all allies
- value: `1`
- parameters: none
- conditions: none
- trigger: `full_burst_start_count:3`
  - compiled `AT_LEAST full_burst_start threshold 3`

Moris owner-order trace에서:

### `스쿼드4`

- B1 #1: `취기` 1
- B1 #2: `취기` 2
- B1 #3: `취기` 3
- third full-burst start: roster notify가 진행되다가 Anchor owner 차례에서 정확히 `3 → 2`
- ensuing full-burst end: stack-3 condition false
- 다음 B1에서 `2 → 3`
- 다음 full-burst start에서 Anchor가 다시 `3 → 2`

따라서 세 번째 cycle 이후 `취기`는 `2 → 3 → 2`를 반복하며 stack-3 full-burst-end branch에 도달하지 않는다.

`레이드_볼륨`도 동일했다.

`레이드_앨리스브래디`에는 아니스 : 스타의 `burst_stage_override:reenter1` effect가 존재하지만, 그 effect는 `has_burst1_ally` 조건이고 해당 roster에서는 이전 checkpoint의 `_roster_static_burst1_condition_unreachable()` 증명에 의해 정적으로 unreachable이다.

## 4. Anchor 없는 public path

`레이드_루주`, `레이드_브리드디젤`에서는 Anchor decrement가 없다.

Moris trace에서:

- `취기`가 B1 entry마다 `1 → 2 → 3`
- 세 번째 full burst가 끝날 때까지 3 stack 유지
- full-burst end에서 `숙취`가 실제 발동
- 같은 full-burst-end transaction에서 `파이레츠 스피릿 3`이 `취기`를 실제 제거
- 이후 B1에서 다시 fresh stack 1부터 시작

`calculator/timeline.py`에서 stun은 실제로:

- stunned actor의 일반 사격을 중지하고
- burst candidate 선택에서도 제외한다.

따라서 이 두 path를 remover만 지원해서 열면 cadence/burst planning이 틀린다. 이번 checkpoint에서는 계속 fail-closed다.

## 5. patch 전 Fast divergence

patch 전 Fast trace:

- `취기`: runtime executable, 실제 `1 → 2 → 3` materialization
- `파이레츠 스피릿` 계열: 기존 finite-reference semantics 사용 가능
- Anchor `불가사리(모양) 오므라이스 3`: runtime executable false
- `숙취`: false
- `파이레츠 스피릿 3`: false

결과적으로 Anchor public roster에서도 Fast는 세 번째 full-burst start 후 `취기=3`을 그대로 유지했다.

Moris는 같은 시점에 `3 → 2`이므로 실제 accuracy score state가 어긋나는 false-supported gap이었다.

## 6. production ownership

semantic production commit:

- `608fe036ed836a35e25736ea9d967bff106af972` — `Fast: own generic harmful stack decrement`

### `effects.py`

`ActiveEffectStore.decrement_harmful_stackable()` 추가.

owned primitive는 Moris처럼:

- active target만 처리
- harmful buff만 처리
- max stack > 1만 처리
- amount만큼 감소
- minimum 1 stack
- live reference/state generation 갱신

### `dispatcher.py`

`_generic_allies_harmful_stack_decrement_provider()`를 추가했다.

runtime ownership은 generic stat 이름만 보고 열지 않는다. 다음 exact compile-time proof가 모두 필요하다.

mutator:

- instant `debuff_stack_remove`
- all-allies runtime-supported target
- value exactly 1
- no parameters / no conditions
- exactly one `AT_LEAST full_burst_start threshold 3` trigger
- target cohort가 squad 전체와 일치

provider surface:

- overlapping harmful multi-stack provider가 정확히 하나
- permanent self `accuracy_pct` harmful buff
- negative value
- max stack exactly 3
- exactly `burst_enter:1`
- no extra parameter/condition/tick/max-trigger
- provider name globally unique
- direct-damage buff runtime shape 자체도 supported

public Anchor + Maid Mast 3조합의 전수 감사에서 이 target cohort에 들어오는 harmful multi-stack provider는 `취기` 하나뿐이었다.

### same-timestamp ordering

새 global frame loop는 추가하지 않았다.

기존 `BurstRuntime`의 owner-order signal broadcast를 그대로 사용하므로, Moris처럼 같은 full-burst-start timestamp 안에서 roster owner 순서로 Anchor decrement가 실행된다.

### `score.py`

`_full_burst_end_stack_condition_unreachable_after_owned_decrement()` 추가.

다음이 증명될 때만 stack-3 full-burst-end remover를 unreachable로 본다.

- exact stack-3 provider
- exact owned generic decrement 하나
- competing provider/mutator 없음
- reachable burst re-entry 없음
- roster-static false re-entry는 기존 proven reachability helper로 제외 가능

또 `_unsupported_generic_harmful_stack_remove_changes_scored_state()`를 추가했다.

앞으로 target-less generic harmful-stack mutator가 scored multi-stack state와 겹치는데 exact owned slice가 아니면 새 `normal_state:*:debuff_stack_remove` blocker로 fail-closed한다.

즉 이번 수정은 semantics restoration과 동시에 같은 계열의 future false-supported gap도 봉합한다.

## 7. 회귀 테스트

신규:

- `fast_engine/tests/test_damage_maid_mast_stack_mutation.py`

고정한 내용:

1. public Anchor 3조합에서 harmful stack provider가 정확히 `취기` 하나인지
2. Fast가 세 번째 full-burst start 후 Moris와 동일하게 `취기=2`가 되는지
3. Anchor path에서 stack-3 remover가 unreachable인지
4. Anchor 없는 2조합은 remover blocker가 유지되는지
5. additional harmful multi-stack provider가 생기면 generic ownership이 즉시 fail-closed인지
6. reachable burst re-entry가 생기면 unreachable proof를 철회하는지

기존 finite-reference 테스트의 stale assertion도 현재 ownership에 맞게 갱신했다.

- follow-up test commit: `cb00449d74ef5580444a11657029fefc8c617174`

## 8. promotion 결과

focused semantic promotion:

- run `33998899663`
- job `101394128608`
- focused regressions success
- production semantic commit `608fe036ed836a35e25736ea9d967bff106af972`

public/full promotion:

- run `33999094106`
- job `101394640976`
- canonical frontier exact assertion success
- Fast complete discovery **303/303**
- structural 180s median `124.84 ms`
- samples `[124.78, 166.3, 124.84]`
- events `539`
- RHQ parity unchanged:
  - Moris/reference `236373847.0`
  - Fast `236465053.42473748`
  - relative error `0.0003858566668650809` (~`+0.0386%`)

## 9. public frontier

이번 semantic/test follow-up 기준:

- source cases: `24`
- unique ordered memberships: `23`
- certified: **2**
- gaps: **21**

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

blocker families:

- normal delivery `47`
- normal state `27`
- skill damage `27`
- skill-state delivery `49`
- weapon change `12`
- cadence `59`
- control `4`
- periodic grid `1`

직전 checkpoint 대비:

- normal state `30 → 27`
- 나머지 unchanged
- certified `2 → 2`

사라진 blocker는 정확히 Anchor가 함께 있는 3 membership의:

`normal_state:마스트 : 로망틱 메이드:파이레츠 스피릿 3:remove_named_buff`

뿐이다.

## 10. 다음 단일 체크포인트

**Maid Mast reachable stack-3 hangover/removal lifecycle**

대상은 Anchor 없는 실제 reachable path다.

다음에 반드시 증명할 것:

1. `숙취` self stun의 exact 10초 lifecycle
2. full-burst end 같은 timestamp에서 `숙취`와 `파이레츠 스피릿 3`의 Moris effect ordering
3. stun 동안 normal-shot suppression
4. stun 동안 burst candidate exclusion
5. `취기` 제거 후에도 이미 활성화된 stun이 독립적으로 남는지
6. 다음 burst cycle의 B1/B2 selection에 미치는 영향
7. generic stun family를 열지 않고 exact reachable Maid Mast slice만 소유할 수 있는지

이 의미론이 소유되기 전에는 `레이드_루주`, `레이드_브리드디젤`의 Maid Mast remover blocker를 유지한다.
