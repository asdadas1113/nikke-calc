# Fast Engine — full-charge-hit self charge-speed checkpoint (2026-09-05)

## 1. 목적

unique-23 public frontier를 다시 shape 단위로 분류한 뒤, 새 global shot chronology 없이 기존 dynamic charge runtime이 이미 소유한 물리 경계를 재사용할 수 있는 다음 작은 generic slice를 선택했다.

실데이터 anchor는 신데렐라 `무결한 유리 2`다.

- effect: `buff`
- stat: `charge_speed_pct +100`
- target: `self`
- duration: permanent
- max stack: `1`
- trigger: raw `full_charge_hit`
- condition: none
- capability blocker: exactly `timing:weapon_hit`

목표는 신데렐라 이름을 특별취급하는 것이 아니라, 이 좁은 post-shot permanent self charge-speed shape만 generic하게 runtime/score ownership하는 것이다.

## 2. 기존 Fast runtime 재사용

새 per-shot scheduler나 1/60 combat loop를 추가하지 않았다.

기존 `MultiSignalChargeCadenceRuntime`은 executable raw `full_charge_hit` consumer가 있는 charge actor의 물리 shot boundary를 이미 소유한다. `BurstRuntime` ordering은 다음과 같다.

1. 물리 charge shot 처리 및 score
2. raw `full_charge_hit` signal dispatch
3. effect activation
4. `weapons.sync()`로 live charge-speed signature 변화 반영

따라서 triggering shot에는 새 charge speed가 소급 적용되지 않고, 그 shot 이후의 charge cadence부터 바뀐다.

## 3. narrow certification shape

`TriggerDispatcher._full_charge_hit_permanent_self_charge_speed_shape_supported()`가 다음 조건을 모두 만족할 때만 PLANNED effect를 executable로 승격한다.

- capability disposition `PLANNED`
- blocker set exactly `{timing:weapon_hit}`
- effect type exactly `buff`
- stat exactly `charge_speed_pct`
- target exactly `SELF`
- non-negative numeric value
- permanent duration (`None` or `-1`)
- max stack absent or `1`
- no max trigger
- no tick interval
- no parameters
- no conditions
- exactly one EVENT trigger
- event key exactly `full_charge_hit`

finite duration, multi-stack, negative value, 다른 weapon-hit event, Brady의 named `stat_applied` 계열은 그대로 fail closed다.

## 4. runner-only A/B

A/B:

- run: `33924314982`
- job: `101189364921`
- result: success

Moris와 Fast의 `무결한 유리 2` activation sequence가 20초 구간에서 직접 일치했다.

첫 구간:

- `1.0000000000000013`
- `1.3333333333333335`
- `1.6666666666666656`
- `1.9999999999999978`
- `2.33333333333333`
- `2.666666666666662`

Fast raw full-charge shot 시각과 Fast buff activation 시각도 동일했다.

의미론:

- 첫 shot은 base 1.0초 charge를 사용한다.
- 그 shot의 `full_charge_hit` 뒤 +100% charge speed가 활성화된다.
- 이후 shot 간격은 약 `1/3`초가 된다.
- triggering shot 자체에는 새 상태가 소급되지 않는다.

A/B gate:

- semantic trace: success
- public scope/fail-closed gate: success
- full Fast regression: `251/251`

## 5. public blocker delta

baseline cadence blocker family는 `66`이었다.

이번 helper는 public unique memberships에서 정확히 두 effect instance만 매칭한다.

- `스쿼드5 / 신데렐라 / 무결한 유리 2 / charge_speed_pct`
- `레이드_루주 / 신데렐라 / 무결한 유리 2 / charge_speed_pct`

따라서 cadence blocker family는 `66 -> 64`로 감소했다.

표준 accounting은 그대로다.

- source cases: `24`
- unique ordered memberships: `23`
- certified: `2`
- coverage gaps: `21`

certified universe가 늘지 않았으므로 standardized ranking probe는 재실행하지 않았다.

## 6. production promotion

production semantic commit:

- `721cd9a8720766c14a814eb8973ca5cd685d7c73` — `fast: certify full-charge-hit self charge speed`

promotion:

- run: `33924481342`
- job: `101189880430`
- focused new regression: `3/3`
- existing one-shot charge-speed regression: `6/6`
- public scope gate: success
- full Fast regression: `254/254`
- production commit/push: success

permanent regression:

- `fast_engine/tests/test_damage_full_charge_hit_charge_speed.py`

첫 promotion attempt의 실패는 존재하지 않는 회귀 모듈 `test_dynamic_charge_score`를 호출한 harness 오류였다. 새 regression `3/3`과 기존 one-shot `6/6`은 그 run에서도 이미 통과했으며, 잘못된 호출만 제거한 뒤 최종 promotion이 성공했다.

## 7. fail-closed 유지

이번 checkpoint는 다음을 지원한다고 주장하지 않는다.

- arbitrary `full_charge_hit` effects
- finite-lifetime full-charge-hit charge speed
- multi-stack full-charge-hit charge speed
- negative charge-speed states
- Brady `event:stat_applied:*` source semantics
- broad weapon-hit trigger family
- cross-class weapon change
- global shot chronology

다음 checkpoint는 updated frontier를 다시 보고 선정한다. blocker 숫자가 적다는 이유만으로 보류 축을 broad-enable하지 않는다.

## 8. canonical CI

docs/cleanup finalizer HEAD:

- `1dd06b721049c6402e0579448307ec103774d302`

이 HEAD에서 temporary workflow가 제거됐고 `.github/workflows`에는 `ci.yml`, `pages.yml`만 남았다.

clean workflow tree와 동일 production code를 user-authored metadata commit `849b56b5a554bc28951f5f36df3bbb160128dd9f`에서 canonical CI로 검증했다.

- run: `33924775444`
- job: `101190834995`
- workflow conclusion: `success`
- doclint: success
- `Fast — damage`: `147/147` — 기존 144개 + 이번 신규 3개가 canonical `test_damage*.py` discovery에 포함됨
- calculator: `137/137` (1 skip)
- optimizer: `374/374`
- bridge: `31/31` (1 skip)
- site: `385/385`
- golden snapshot: `29/29`

이 문서 commit은 위 성공 결과를 기록하기 위한 docs-only 변경이다. 따라서 이 최종 문서 HEAD에서도 동일 canonical CI를 다시 통과시켜 checkpoint를 닫는다.
