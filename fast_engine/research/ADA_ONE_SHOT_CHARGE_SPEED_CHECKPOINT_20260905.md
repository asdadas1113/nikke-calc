# Ada one-shot charge-speed lifetime checkpoint — 2026-09-05

## 1. 범위

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

`master`는 수정하거나 병합하지 않는다.

이번 slice의 목적은 Ada 이름을 특별취급하는 것이 아니라, Fast가 이미 소유하는 charge-shot boundary와 bullet-lifetime infrastructure를 이용해 다음 좁은 generic shape를 score-safe로 인증하는 것이다.

- self buff
- stat `charge_speed_pct`
- trigger exactly one `burst_cast` event
- `duration_bullets: 1`
- one stack
- ordinary permanent/no-time lifetime
- no conditions
- capability blocker가 정확히 `field:duration_bullets`

production commit:

- `f70871e36ddf28a2474e7e25d6d7254cf9fe26cd` — `fast: certify one-shot charge-speed lifetime`

## 2. 실제 Ada public shape

확인된 Ada effect:

- `특수 개조`: self `charge_speed_pct=-300`, `burst_cast`, `duration_bullets:1`
- `특수 개조 2`: self `charge_dmg_pct=+1500`, `burst_cast`, `duration_bullets:1`

이번 production slice는 첫 번째 `charge_speed_pct`만 연다. `특수 개조 2`의 direct-damage delivery는 별도 blocker로 유지한다.

관련 non-`지그_*` public teams:

- `레이드_미하라에이다`
- `레이드_헬름아쿠아스노우`

두 팀 모두 Ada 자체의 별도 `control:에이다` blocker가 존재한다. 따라서 이 slice만으로 certified membership 수가 늘어날 것으로 기대하지 않는다.

## 3. Moris/Fast shot-order 근거

Moris 의미는 다음 순서다.

1. burst cast에서 one-shot state 활성
2. 다음 physical charge shot의 charge cadence에 상태 적용
3. 해당 shot의 damage / hit 계열 처리가 끝난 뒤 bullet lifetime 1 소모
4. 상태 제거

Fast dynamic charge runtime은 이미 score shot을 먼저 처리하고 그 뒤 내부 bullet-consume signal을 발생시키는 구조다. 새 runtime loop나 dispatcher event family는 추가하지 않았다.

Moris outer-tick 정렬도 유지한다. synthetic regression에서 base charge 1.0초, `charge_speed_pct=-300`이면 계산 deadline은 4.0초지만 상태는 정확히 4.0초에는 아직 살아 있고, 다음 observed outer tick에서 physical shot이 처리된 뒤 4.05초 시점에는 제거되어야 한다.

## 4. 구현 범위

`fast_engine/engine/dispatcher.py`:

- `_charge_speed_bullet_lifetime_shape_supported()` 추가
- `CapabilityDisposition.PLANNED`
- blockers exactly `{field:duration_bullets}`
- buff / `charge_speed_pct` / self
- duration `None` 또는 `-1`
- no conditions
- parameters exactly `{duration_bullets}`
- max stack 1
- `duration_bullets == 1`
- trigger exactly one EVENT `burst_cast`

이 shape만 `is_executable_effect()`에서 허용한다.

`fast_engine/engine/score.py`:

- dynamic charge score의 기존 무조건적인 bullet-lifetime 거부를 없애고 `_valid_dynamic_bullet_lifetime()` + dispatcher certification을 함께 요구한다.

새 regression:

- `fast_engine/tests/test_damage_charge_speed_bullet_lifetime.py`

## 5. fail-closed regression

다음은 계속 막는다.

- `full_charge` 등 weapon-bound trigger
- non-integer `duration_bullets` (`1.5`)
- multi-bullet lifetime (`2`)
- non-self target
- 다른 stat의 broad `duration_bullets` enable

특히 초기 A/B는 정수 N발을 허용할 가능성까지 확인했지만 production 후보에서는 `duration_bullets == 1`로 다시 좁혔다.

## 6. 검증 결과

focused production regression:

- 19 tests passed

full Fast regression:

- 55 test modules
- 240 tests passed

standardized public probe:

- source cases: 24
- unique ordered memberships: 23
- certified: 2
- coverage gaps: 21
- clean relative error median: `0.0006268322047938701`
- min: `0.000349533271479352`
- max: `0.0009041311381083883`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`

blocker family delta:

- cadence `68 -> 66`
- skill_state_delivery `50` unchanged
- normal_delivery `49` unchanged
- skill_damage `27` unchanged
- weapon_change `12` unchanged
- control `8` unchanged
- normal_state `7` unchanged

public Ada blocker delta:

`레이드_미하라에이다`와 `레이드_헬름아쿠아스노우`에서 정확히 다음 blocker가 제거됐다.

- `cadence:에이다:특수 개조:charge_speed_pct`

다음은 그대로 남는다.

- `control:에이다`
- `normal_delivery:에이다:특수 개조 2:charge_dmg_pct`
- `skill_state_delivery:에이다:특수 개조 2:charge_dmg_pct`

`지그_리코리코`에서는 Ada 관련 blocker가 0이 된다. `지그_*`는 표준 public coverage accounting에는 포함하지 않는다.

## 7. 해석

이번 변경은 coverage 숫자를 늘리기 위한 broad enable이 아니다. Fast가 이미 소유한 physical charge-shot boundary에서 one-shot cadence state의 적용/소모 순서를 명시적으로 인증한 것이다.

production gate에서 기존 certified 2팀의 score/ranking은 움직이지 않았다. 따라서 현재 관측 범위에서 ranking regression 근거는 없다.

## 8. 다음 checkpoint

다음 우선 후보는 같은 Ada burst에서 함께 생기는 `특수 개조 2`다.

- self `charge_dmg_pct`
- `burst_cast`
- `duration_bullets:1`

먼저 기존 Helm direct-damage bullet-lifetime support와 실제 Ada compiled shape를 비교하고, 같은 physical shot에서 damage term 적용 후 lifetime이 제거되는지 Moris/Fast를 대조한다.

단, `control:에이다`는 별도 문제이므로 `특수 개조 2`까지 열어도 두 public Ada 팀이 즉시 certified가 된다고 가정하지 않는다.
