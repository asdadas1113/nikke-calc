# Fast Engine — recipient stat-applied charge-speed checkpoint (2026-09-05)

## 1. 목적

Cinderella checkpoint 뒤 public cadence frontier `64`에서 다음 작은 generic ownership을 재분류했다. all-allies reload/max-ammo는 unsafe recipient와 결합돼 있었고, Snow White `charge_time_fixed`는 weapon-change와 결합돼 있어 독립 slice로 부적합했다.

이번 anchor는 `레이드_앨리스브래디`의 Brady `나누고 싶은 맛`이다.

- effect: `buff`
- stat: `charge_speed_pct -20`
- target: `self`
- duration: `50s`
- max stack: `1`
- trigger: `event:stat_applied:split_dmg_pct`
- condition: `not_self_state:머물고 싶은 맛`
- capability blocker: exactly `timing:named_event`

목표는 Brady 이름을 특별취급하는 것이 아니라, recipient에게 특정 stat buff가 실제 적용된 직후 발생하는 좁은 `stat_applied` semantic event와 그 source proof를 generic하게 소유하는 것이다.

## 2. Moris 의미론과 runtime 재사용

Moris `calculator/buff_manager.py`는 일반 buff activation이 성공한 뒤 stat이 `dot_dmg_pct` 또는 `split_dmg_pct`이면 각 실제 ally recipient에게 같은 시각 다음 이벤트를 notify한다.

- `event:stat_applied:dot_dmg_pct`
- `event:stat_applied:split_dmg_pct`

이 이벤트는 broad named-event broadcast가 아니다. 실제 provider target별 recipient-scoped event이며 refresh에서도 다시 발생한다.

Fast는 새 frame loop나 global shot loop를 추가하지 않았다. 기존 `TriggerDispatcher`의 actor-scoped event bucket과 `ActiveEffectStore`를 재사용한다.

ordering은 다음과 같다.

1. provider buff target 해석
2. provider activation / refresh
3. 기존 provider-name event가 있으면 그 event 처리
4. 지원 stat이면 각 concrete ally recipient에게 `event:stat_applied:{stat}` dispatch
5. consumer activation
6. 기존 dynamic charge cadence sync

따라서 stat을 실제로 받지 않은 actor에게 이벤트를 broadcast하지 않는다.

## 3. narrow certification / source proof

structural consumer helper는 다음 조건만 허용한다.

- capability disposition `PLANNED`
- blocker set exactly `{timing:named_event}`
- effect type `buff`
- stat `charge_speed_pct`
- target `SELF`
- value `> -100`
- positive finite-lifetime shape
- max stack absent or `1`
- no max trigger / tick interval / parameters
- exactly one EVENT trigger
- event key가 `event:stat_applied:dot_dmg_pct` 또는 `event:stat_applied:split_dmg_pct`
- condition 없음, 또는 exactly one `NOT_SELF_STATE`

하지만 structural executable만으로 score를 열지 않는다. `stat_applied_dependency_score_safe()`가 모든 가능한 source provider를 별도로 증명해야 한다.

- consumer actor를 실제 target으로 삼을 수 있는 source provider가 최소 하나 존재해야 한다.
- 모든 가능한 provider가 executable buff여야 한다.
- provider target scope가 runtime-safe여야 한다.
- provider 자체가 다른 named-event source proof에 의존하면 닫는다.
- `NOT_SELF_STATE`가 있으면 반대 상태를 만들 수 있는 source stat이 해당 recipient에게 도달 가능한지 검사한다.
- 반대 source가 하나라도 가능하면 condition을 immutable로 간주하지 않고 fail closed한다.

또한 dynamic charge score path도 이제 executable 여부만 보지 않고 named-event source proof를 통과해야 한다. 이는 이번 Brady slice가 드러낸 기존 certification hole을 함께 닫는다.

## 4. Brady public proof / runner-only A/B

public `레이드_앨리스브래디`에서 Brady의 관련 effect는 네 개다.

- `머물고 싶은 맛`: `dot_dmg_pct` stat-applied -> self charge speed -20
- `머물고 싶은 맛 2`: opposing named-buff remove
- `나누고 싶은 맛`: `split_dmg_pct` stat-applied -> self charge speed -20, `not_self_state:머물고 싶은 맛`
- `나누고 싶은 맛 2`: opposing named-buff remove

이 public membership에서는 Brady에게 도달 가능한 `split_dmg_pct` provider가 존재하고 `dot_dmg_pct` provider는 없다. 따라서 split branch의 negative condition은 이 membership에서 immutable true로 증명되며, dot branch는 source-unreachable이다. 두 remove effect는 계속 unsupported다.

runner-only A/B:

- run: `33929600782`
- job: `101205337651`
- result: success

40초 trace에서 Fast와 Moris의 `나누고 싶은 맛` activation sequence가 정확히 일치했다.

- `3.1999999999999935`
- `15.733333333333695`
- `15.933333333333705`
- `28.266666666666342`
- `28.46666666666633`

provider refresh가 일어날 때도 `stat_applied`가 다시 emit되어 sequence가 유지됐다. synthetic하게 반대 `dot_dmg_pct` source를 만들면 split branch source proof는 즉시 false가 되어 fail closed로 돌아갔다.

A/B gate:

- semantic trace: success
- focused regressions: success
- full Fast: `254/254`
- standardized public ranking probe: success

## 5. public blocker / ranking delta

이 helper는 unique-23 public memberships에서 source-certified consumer를 정확히 하나만 연다.

- `레이드_앨리스브래디 / 브래디 / 나누고 싶은 맛 / event:stat_applied:split_dmg_pct`

Brady `머물고 싶은 맛` cadence blocker와 두 remove effect 관련 unsupported semantics는 그대로 남는다.

public accounting:

- source cases: `24`
- unique ordered memberships: `23`
- certified: `2`
- coverage gaps: `21`
- cadence blocker family: `64 -> 63`

이번에는 standardized ranking probe도 실제 재실행했다.

- clean relative error median: `0.0006268322047938701`
- min: `0.000349533271479352`
- max: `0.0009041311381083883`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`
- unsupported family: none

blocker family counts:

- cadence `63`
- skill_state_delivery `45`
- normal_delivery `44`
- skill_damage `27`
- weapon_change `12`
- normal_state `7`
- control `6`
- periodic_grid `1`

## 6. production promotion

production semantic commit:

- `8880049678c9270de8d7b98c456b93fa00a67502` — `fast: certify recipient stat-applied charge speed`

promotion final run:

- run: `33929914438`
- job: `101206236343`
- focused production regressions: `33/33`
- full Fast production regressions: `258/258`
- intended production diff whitelist: success
- production commit/push: success

permanent regression:

- `fast_engine/tests/test_damage_stat_applied_charge_speed.py` — 4 tests
- `fast_engine/tests/test_damage_full_charge_hit_charge_speed.py` — chained public cadence expectation `64 -> 63`

promotion 전 실패들은 production semantic failure가 아니었다. 첫 시도는 workflow/harness parse 문제였고, 다음 시도는 `git diff --name-only`가 untracked 새 테스트를 보지 못한 whitelist 문제였다. untracked까지 포함한 whitelist로 고친 최종 promotion이 통과했다.

## 7. fail-closed 유지

이번 checkpoint는 다음을 지원한다고 주장하지 않는다.

- arbitrary `stat_applied:*` family
- `dot_dmg_pct`/`split_dmg_pct` 외 stat-applied event
- source가 없는 consumer 추측 실행
- source provider 일부가 unsupported인데 나머지만 보고 certification
- 반대 state source가 가능한 mutual-exclusion branch
- Brady의 opposing named-buff remove semantics
- arbitrary finite negative charge-speed families
- all-allies reload/max-ammo unsafe recipient 무시
- broad/cross-class weapon change
- global shot/frame chronology

특히 consumer shape가 executable이라는 사실과 score source가 증명됐다는 사실을 분리한다.

## 8. canonical CI

production semantic promotion 자체는 runner에서 full Fast `258/258`까지 통과했다.

cleanup commit:

- `e467103c992786d8259229840005e1d672284bb6` — docs/cleanup finalizer
- cleanup 뒤 `.github/workflows`는 `ci.yml`, `pages.yml`만 남았다.

cleanup commit은 GitHub Actions token push라 recursive canonical CI가 생성되지 않았다. 따라서 docs-only metadata commit `f55579ffd586eee15fa21b79c754b27d3e2959d5`로 동일 production tree의 canonical CI를 직접 실행했다.

- run: `33931819590`
- job: `101211793772`
- workflow conclusion: `success`
- doclint: success
- Fast — damage: `151/151`
- calculator: `137/137` (1 skip)
- optimizer: `374/374`
- bridge: `31/31` (1 skip)
- site: `385/385`
- golden snapshot: `29/29`

Brady 신규 `test_damage_stat_applied_charge_speed.py`는 canonical `test_damage*.py` discovery에 포함된 상태로 검증됐다.
