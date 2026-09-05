# Fast Engine — periodic enemy received-damage checkpoint (2026-09-05)

## 1. 목적

Brady checkpoint 이후 cadence `63` unique-23 frontier를 다시 비교했다. 다음 후보로 Ada `effect_interval`, Neon : Vision Eye `초화력`, Helm : Aquamarine `이지스 캐논 견제 사격 2`를 Moris 의미론과 기존 Fast runtime 재사용 가능성 기준으로 비교했다.

- Ada `effect_interval`은 Moris가 이미 예약된 periodic deadline을 실시간 재스케일하는 동적 grid mutation이라 독립 slice가 아니었다.
- Neon `초화력`은 `화력 게이지 == 100`을 요구해 gauge chronology가 선행된다.
- Helm : Aquamarine의 enemy `received_dmg_pct`는 기존 fixed periodic scheduler, enemy state store, damage resolver를 그대로 재사용할 수 있었다.

따라서 이번 anchor는 `레이드_헬름아쿠아스노우`의 `이지스 캐논 견제 사격 2`다.

실제 shape:

- effect type: `buff`
- stat: `received_dmg_pct +5.64`
- polarity: `harmful`
- target: enemy singleton (`same_target` -> Fast `ENEMY`)
- duration: `5s`
- max stack: `5`
- trigger: fixed periodic `every:4s`
- condition: `target_code:전격`
- parameters: none
- capability blockers exactly:
  - `category:hit_formula`
  - `stat:received_dmg_pct`
  - `timing:periodic`
  - `condition:enemy`
  - `target:enemy_singleton`

## 2. runtime 재사용

새 periodic scheduler나 1/60 loop를 추가하지 않았다.

Fast의 기존 `BurstRuntime._schedule_initial_periodics()`는 nominal interval을 `moris_observed_tick()`로 outer-tick 시각에 맞춰 예약하고, 이후 `PERIODIC_TICK -> TriggerDispatcher.dispatch_periodic() -> ActiveEffectStore` 경로를 사용한다.

`received_dmg_pct` 자체는 이미 enemy damage term에 반영되는 stat이다. 따라서 필요한 것은 broad timing 지원이 아니라 이 fixed-grid enemy-stack shape를 좁게 executable/score-safe로 인정하는 것이다.

`_periodic_finite_enemy_received_damage_shape_supported()`는 다음을 모두 요구한다.

- capability disposition `PLANNED`
- blocker set이 위 5개와 정확히 동일
- `buff / harmful / received_dmg_pct`
- enemy singleton runtime target
- non-negative numeric value
- positive finite duration
- integer `max_stack >= 1`
- no max-trigger / tick-interval / parameters
- exactly one `TARGET_CODE` condition with a concrete code
- exactly one positive fixed `PERIODIC` trigger

이 helper만 `TriggerDispatcher.is_executable_effect()`와 `_is_score_safe_fixed_periodic()`에 추가했다. broad `damage_policy` periodic timing은 열지 않았다.

## 3. Moris/Fast semantic A/B

runner-only A/B:

- run `33932690769`
- job `101214374980`
- result `success`

전격 enemy, 25초 구간에서 Fast와 Moris의 activation 시각이 6개 모두 정확히 일치했다.

- `4.016666666666658`
- `8.016666666666644`
- `12.000000000000176`
- `16.000000000000373`
- `20.000000000000146`
- `24.016666666666584`

스택과 누적값도 일치했다.

- stack: `1 -> 2 -> 3 -> 4 -> 5 -> 5`
- `received_dmg_pct`: `5.64 -> 11.28 -> 16.92 -> 22.56 -> 28.2 -> 28.2`

동일 squad에서 enemy code를 `작열`로 바꾸면 Fast와 Moris 모두 activation `0회`였다. 즉 target-code condition도 static enemy profile로 정확히 닫힌다.

## 4. regression / fail-closed

새 permanent regression:

- `fast_engine/tests/test_damage_periodic_enemy_received.py` — 4 tests

검증 범위:

1. real Helm shape와 blocker delta
2. Moris/Fast activation + stack/value trace exact match
3. target-code mismatch에서 양쪽 모두 0회
4. condition 제거, fractional max stack, beneficial polarity 등 neighboring shape fail closed

기존 `test_damage_periodic_self_crit.py`도 과거의 “Helm enemy stack은 미지원” expectation만 갱신했고, Ada `effect_interval`을 새로운 neighboring fail-closed anchor로 유지했다.

의도적으로 계속 닫는 축:

- arbitrary periodic enemy buffs/debuffs
- broad periodic timing in `damage_policy`
- dynamic periodic-grid mutation (`effect_interval`, `skill_cooldown_pct`, `skill_cooldown_reduce_pct`, `force_skill_use`)
- non-static enemy condition chronology
- missing/unsupported target-code condition
- non-enemy target variants
- beneficial `received_dmg_pct` variant
- non-integer stack shape

## 5. public blocker / ranking delta

A/B 후 `레이드_헬름아쿠아스노우`의 Helm blocker 2개가 제거됐다.

제거:

- `normal_delivery:헬름 : 아쿠아마린:이지스 캐논 견제 사격 2:received_dmg_pct`
- `skill_state_delivery:헬름 : 아쿠아마린:이지스 캐논 견제 사격 2:received_dmg_pct`

남음:

- `weapon_change:스노우 화이트:세븐스 드워프 : I`
- `normal_delivery:스노우 화이트:세븐스 드워프 : I 2:pierce_enabled`
- `periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval`

public accounting은 그대로다.

- source cases `24`
- unique memberships `23`
- certified `2`
- coverage gaps `21`

blocker family delta:

- cadence `63` 유지
- skill_state_delivery `45 -> 44`
- normal_delivery `44 -> 43`
- skill_damage `27`
- weapon_change `12`
- normal_state `7`
- control `6`
- periodic_grid `1`

standardized ranking probe도 실제 재실행했다.

- clean relative error median `0.0006268322047938701`
- min `0.000349533271479352`
- max `0.0009041311381083883`
- pairwise accuracy `1.0`
- top-N recall `1.0`
- unsupported family none

## 6. production promotion

production semantic commit:

- `4a6cbe388cd0ef32ec07e5b825078fe457619181` — `fast: certify periodic enemy received damage`

A/B final gate:

- run `33932690769` / job `101214374980`
- focused `21/21`
- full Fast `262/262`
- standardized public ranking probe success

promotion:

- run `33932866252` / job `101214901667`
- exact candidate apply success
- focused production regressions success
- full Fast `262/262`
- production diff whitelist success
- production commit/push success

## 7. 다음 checkpoint

이번 비교에서 Ada `effect_interval`은 단순 blocker 완화 대상이 아니라 실제 dynamic periodic deadline rescheduling 문제임이 확인됐다. Neon gauge branch도 gauge chronology가 선행된다. 둘 다 다음 slice로 즉시 broad-enable하지 않는다.

clean canonical CI까지 닫은 뒤 unique-23 frontier를 다시 보고 다음 작은 generic ownership을 고른다. 가까운 blocker 수만으로 Little Mermaid/Crown/Mihara/weapon-change 보류 축을 우회하지 않는다.

## 8. canonical CI

production promotion에서 full Fast `262/262`까지 검증했다.

cleanup 뒤 `.github/workflows`를 `ci.yml`, `pages.yml`만 남긴 clean HEAD에서 canonical CI를 다시 실행하고 최종 run/job/count를 이 절에 기록한다.
