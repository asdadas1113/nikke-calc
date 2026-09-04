# Fast Engine — finite periodic self-crit checkpoint (2026-09-05)

## 1. 목적

public coverage frontier를 다시 스캔한 결과, 남은 blocker 중 단순 score proof 누락은 없었다. 다음 작은 generic slice로 기존 Fast periodic scheduler를 그대로 재사용할 수 있는 **고정 주기 finite self `crit_rate` 상태**를 선택했다.

실데이터 anchor는 스노우 화이트 `세븐스 드워프 : V&VI 2`다.

- effect: `buff`
- stat: `crit_rate +26.1`
- target: `self`
- duration: `10s`
- max stack: `1`
- timing: `every:15s`
- condition: `during_full_burst`

목표는 스노우 화이트 이름을 특별취급하는 것이 아니라, 이 좁은 periodic shape만 generic하게 runtime/score ownership하는 것이다.

## 2. Moris 의미론

`calculator/buff_manager.py`의 `every:Ns` 처리는 battle start 시 즉시 발동하지 않는다. 첫 deadline은 interval 뒤에 생기며 deadline에 도달할 때 condition을 검사하고, 조건이 참이면 효과를 활성화한 뒤 다음 deadline을 같은 grid에서 예약한다.

표준 `레이드_헬름아쿠아스노우`, 70초 expected simulation에서 `세븐스 드워프 : V&VI 2`는 다음 outer-tick 관측 시각에 활성화됐다.

- `30.016666666666243`
- `45.016666666665394`
- `60.01666666666454`

15초 nominal deadline에서는 full burst 조건이 거짓이라 발동하지 않는다.

Moris는 periodic interval을 `skill_cooldown_pct`와 `effect_interval`로 바꿀 수 있다. Fast score에는 이미 이를 포함한 `_PERIODIC_GRID_INVALIDATORS` (`effect_interval`, `skill_cooldown_pct`, `skill_cooldown_reduce_pct`, `force_skill_use`)가 존재한다. 이번 slice도 그 fail-closed 계약을 그대로 통과해야 한다.

## 3. Fast 구현

production commit:

- `fee2fe343cf75861185dd780d9191bbf6f48da8f` — `fast: certify finite periodic self crit state`

### Dispatcher

`_periodic_finite_self_crit_shape_supported()`를 추가했다. 지원 범위는 정확히 다음으로 제한한다.

- capability `PLANNED`
- blocker set exactly `category:hit_formula`, `stat:crit_rate`, `timing:periodic`, `condition:simple_runtime`
- `buff`
- stat exactly `crit_rate`
- beneficial, non-negative value
- target exactly `SELF`
- finite positive duration
- `max_stack == 1`
- no `max_trigger`, `tick_interval`, parameters
- condition exactly one `DURING_FULL_BURST`
- trigger exactly one positive fixed `PERIODIC`

새 scheduler나 frame loop는 만들지 않았다. 기존 periodic deadline scheduler, condition runtime, `ActiveEffectStore`를 그대로 사용한다.

### Score

`_is_score_safe_fixed_periodic()`가 위 narrow shape를 인정하도록 확장했다. periodic-grid invalidator가 팀에 있으면 기존 `periodic_grid:*` blocker가 계속 생기므로 동적으로 변하는 interval을 고정 grid로 잘못 인증하지 않는다.

## 4. runner-only A/B

최종 A/B:

- workflow run: `33922544009`
- job: `101183863415`

결과:

- 새 focused regression `3/3`
- 기존 periodic runtime regression `8/8`
- Fast/Moris successful activation time 3개가 9 decimal places까지 일치
- public scope helper match 정확히 1개: `레이드_헬름아쿠아스노우 / 스노우 화이트 / 세븐스 드워프 : V&VI 2 / crit_rate`
- full Fast regression `251/251`

첫 A/B 실패는 존재하지 않는 임시 회귀 모듈명을 호출한 harness 오류였고 candidate semantic test 자체는 이미 통과했다. 호출을 제거한 뒤 전체 gate가 초록으로 닫혔다.

## 5. production promotion

- run: `33922753827`
- job: `101184510974`
- focused regression: success
- public scope gate: success
- full Fast regression: success
- production commit/push: success

permanent regression:

- `fast_engine/tests/test_damage_periodic_self_crit.py`

파일명을 `test_damage*.py` 계약에 맞춰 canonical Fast damage discovery에 직접 포함시켰다.

## 6. public blocker delta

`레이드_헬름아쿠아스노우`에서 다음 두 blocker만 제거된다.

- `normal_delivery:스노우 화이트:세븐스 드워프 : V&VI 2:crit_rate`
- `skill_state_delivery:스노우 화이트:세븐스 드워프 : V&VI 2:crit_rate`

다음은 그대로 남긴다.

- Helm Aqua `이지스 캐논 견제 사격 2:received_dmg_pct` periodic enemy state
- Snow White `세븐스 드워프 : I` weapon change
- Snow White `세븐스 드워프 : I 2:pierce_enabled`

표준 public accounting은 여전히 `24 source / 23 unique / 2 certified / 21 gaps`다. certified universe가 늘지 않았으므로 standardized ranking probe는 재실행하지 않았다.

## 7. fail-closed 유지

이번 checkpoint는 다음을 지원한다고 주장하지 않는다.

- periodic enemy/same-target stacking
- arbitrary periodic direct-damage stats/conditions
- periodic interval mutation
- gauge-driven periodic effects
- `on_attack` chronology
- weapon change
- multi-target dynamic target selection

특히 인접한 Helm Aqua periodic enemy `received_dmg_pct`는 target/stack/condition 의미론을 별도로 검증해야 하므로 이번 slice에 포함하지 않았다.
