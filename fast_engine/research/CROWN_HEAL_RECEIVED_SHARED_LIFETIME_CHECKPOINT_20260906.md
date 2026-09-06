# Crown heal-received shared lifetime 체크포인트 — 2026-09-06

## 0. 결론

public `레이드_아스카루드밀라`에서 Crown `로얄 에타이어 4`의 `heal_received` 의존성과 normal/skill 공용 7초 `atk_dmg_pct` lifetime을 Moris oracle 기준으로 고정하고, Fast가 정확한 reachable-provider graph만 소유하도록 확장했다.

semantic production commit:

- `be702b01f8230e985fc7301ebc9decc43a6d3e40` — `Fast: own Crown heal-received lifetime and zero-core guard`

기존 target blocker:

- `normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct`
- `skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct`

결과적으로 `레이드_아스카루드밀라`는 다섯 번째 public certified membership이 됐다.

이번 checkpoint는 generic external heal, generic lowest-HP target, generic lifesteal, generic core-hit count를 연 것이 아니다. compile-time에서 Crown에게 실제로 도달 가능한 heal provider만 남기고, 남은 provider가 이미 소유된 self stack-heal chain일 때만 `heal_received` consumer를 연다.

## 1. Moris oracle — `로얄 에타이어 4`

`로얄 에타이어 4` relevant shape:

- effect type: buff
- target: all allies
- stat: `atk_dmg_pct`
- value: `20.99`
- duration: `7s`
- trigger: `heal_received`

Crown 자신의 기존 `릴렉스 → 로얄 에타이어 → 로얄 에타이어 3` stack/heal chain은 이미 Fast가 소유한 provider다.

문제는 `레이드_아스카루드밀라`에 나가의 외부 heal이 하나 더 존재한다는 점이었다.

나가 `우정의 서포트 2`:

- instant `heal_hp_pct`
- target `allies_lowest_hp:2`
- `hit_count` modulo cadence

Moris `BuffManager._resolve_target`을 직접 trace하면 patternless full-HP 상태에서 매번 대상은 정확히:

- `리틀 머메이드`
- `나가`

두 명이다. 전원 HP 비율이 100% tie인 동안 Moris의 immutable squad-order tie break가 유지되며, Crown은 index 2라 first two에 포함되지 않는다.

따라서 이 roster에서 나가 heal은 Crown의 `heal_received`를 절대로 발생시키지 않는다.

장기 Moris trace에서도 Crown `로얄 에타이어 4` activation은 Crown 자신의 self-heal chain에서만 관측됐다. 대표 activation은 약:

- `17.6667s`
- `32.8667s`
- `48.0667s`

이다.

초기 진단에서 instant log가 나가 한 명만 표시한 적이 있었지만, 이는 dynamic target resolve 전에 기록되는 log fallback 한계였다. 실제 resolver trace는 항상 `(리틀 머메이드, 나가)` 두 명을 반환했다.

## 2. narrow reachable-provider proof

`TriggerDispatcher`에 full-HP rank tie를 보수적으로 증명하는 whitelist-shaped proof를 추가했다.

명시적으로 tie-safe로 인정하는 stat만 허용한다.

- `heal_hp_pct`
- `lifesteal_pct`
- `heal_received_pct`
- `outgoing_heal_pct`
- `heal_given_pct`
- `cover_hp_pct`
- `cover_heal_pct`
- `shield_from_max_hp_pct`

stat 이름에 `hp`, `heal`, `life`가 들어가면서 이 whitelist 밖이면 proof를 즉시 철회한다. 따라서:

- current HP 감소
- max-HP mutation
- derived HP 계열
- unknown future HP mechanic

은 자동으로 fail closed다.

`_lowest_hp_heal_owner_unreachable()`는 정확히 다음 shape에서만 provider edge 하나를 제거한다.

- PLANNED disposition
- instant `heal_hp_pct`
- `LOWEST_HP:N`
- positive finite N
- owner index가 first N 밖
- positive heal value
- duration/max stack/max trigger/tick 없음
- parameters/conditions 없음
- 단일 MODULO `hit_count` trigger
- positive integral threshold
- squad full-HP tie stability proof 성공

그 뒤에도 `heal_received_dependency_score_safe()`는 **reachable provider 전부가 기존 owned self stack-heal chain**이어야 true다.

따라서 generic 외부 heal/lifesteal은 여전히 열리지 않는다.

## 3. normal / skill shared lifetime

별도 damage primitive는 필요하지 않았다.

기존 Fast timed effect store는 동일 timed buff 재활성화 시 generation을 갱신하고 새 `now + duration` expiry를 사용한다. `DamageTermResolver`는 동일한 active `atk_dmg_pct` state를 normal attack과 skill damage 양쪽에서 읽는다.

synthetic contract에서 `로얄 에타이어 4`를:

- `t=1.0` activation
- `t=2.0` refresh

하면:

- `t=8.5`: `atk_dmg_pct = 20.99`
- `t=9.0`: expired, `atk_dmg_pct = 0`

이며 normal / skill expected damage 모두 base 대비 정확히:

- `1.2099x`

를 사용한다.

즉 recipient와 lifetime은 두 damage path가 따로 복제하지 않고 하나의 timed all-allies damage state를 공유한다.

## 4. hidden zero-core runtime guard 수정

Crown blocker가 제거된 뒤 `레이드_아스카루드밀라` 전체 `score_static_squad()`를 실행하자, 루드밀라 : 윈터 오너의 dynamic weapon + `core_hit_count` runtime guard가 새로 드러났다.

이것은 Crown 의미론과 별개의 hidden false-supported gate였다.

`core_px=0` 또는 core uptime이 0이면 core hit 확률은 weapon/accuracy와 무관하게 구조적으로 정확히 0이다. 그런데 기존 코드는 zero-core 판정을 하기 전에 dynamic actor guard부터 검사했다.

수정 후:

- explicit `core_px <= 0` → core-hit family 조기 종료
- `core_uptime <= 0` → 조기 종료
- `core_px is None`이어도 effective core rate가 0이면 조기 종료
- nonzero core는 기존 dynamic/accuracy fail-closed guard를 그대로 통과

한다.

따라서 live-core support는 넓어지지 않았다.

## 5. fail-closed 경계

신규 regression은 다음을 명시적으로 막는다.

- `allies_lowest_hp:2 → :3`처럼 count가 Crown까지 넓어짐
- current/max HP 등 HP-rank mutation 하나라도 존재
- provider가 `all_allies` external heal로 바뀜
- generic external heal/lifesteal
- nonzero core profile에서 dynamic `core_hit_count`

또한 다른 public Crown roster의 `로얄 에타이어 4`는 provider graph가 이 exact proof에 들어오지 않으면 그대로 blocker를 유지한다.

현재 Crown blocker가 남는 public membership은:

- `스쿼드1`
- `스쿼드5`
- `레이드_일레그`

이다. 이 셋은 `레이드_아스카루드밀라`와 같은 unreachable-lowest-HP proof로 제거할 수 없는 reachable provider/dependency가 있으므로 의도적으로 fail closed다.

## 6. regression

신규 contract:

- `fast_engine/tests/test_damage_crown_royal_attire_lifecycle.py`

핵심 8개 계약:

1. public Asuka/Ludmilla blocker zero + Naga unreachable provider proof
2. Moris `LOWEST_HP:2` actual target parity
3. wider target count fail closed
4. HP-rank mutation 시 proof 철회
5. external all-allies heal fail closed
6. timed all-ally buff refresh / normal-skill shared state
7. Fast/Moris Royal Attire activation timing parity
8. nonzero-core dynamic core-count fail closed

관련 기존 heal/shield/dynamic-ammo/frontier regression까지 합친 focused staged gate:

- `30/30` success

staged full Fast discovery:

- `338/338` success
- RAPI parity unchanged

처음 full discovery에서 발생한 6개 failure는 모두 이전 frontier/Crown fail-closed 상태를 고정한 stale assertion이었다. certified count `4 → 5` 및 Naga provider의 새 unreachable proof만 반영했고, unrelated mechanic-specific assertion은 완화하지 않았다.

## 7. production audit

production audit run:

- run `34024061683`
- job `101461785941`
- result: success

fresh frontier:

- source cases `24`
- unique memberships `23`
- certified **5**
- gaps **18**

certified:

- `레이드_레드후드퀀시`
- `레이드_아스카루드밀라`
- `레이드_델타`
- `레이드_볼륨`
- `컨트롤_미란다미하라`

blocker families:

- normal delivery `46`
- normal state `16`
- skill damage `25`
- skill-state delivery `48`
- weapon change `12`
- cadence `57`
- control `4`
- periodic grid `1`

Little Mermaid checkpoint 대비:

- certified `4 → 5`
- gaps `19 → 18`
- normal delivery `47 → 46`
- skill-state delivery `49 → 48`
- 나머지 unchanged

`레이드_아스카루드밀라` 180초 Fast production audit:

- squad total `2294472196.185189`
- char totals:
  - `658209394.1617091`
  - `220508183.67980948`
  - `119520446.93174963`
  - `857021238.9742464`
  - `439212932.4376743`
- events processed `4736`
- unsupported `()`

이 score는 semantic oracle이 아니라 end-to-end runtime completeness diagnostic이다.

## 8. canonical gate

pre-cleanup canonical CI:

- run `34024177621`
- job `101462096683`
- result: success
- Fast damage `229/229`
- Fast complete discovery `338/338`
- structural performance median `189.93ms`, events `539`
- full discovery structural median `188.93ms`, events `539`
- RAPI parity: reference `236373847.0`, Fast `236465053.42473748`, relative error `0.0003858566668650809`
- calculator `137/137` (`1` skip)
- optimizer `374/374`
- bridge `31/31` (`1` skip)
- site `385/385`
- golden `29/29`
- doclint characters `199`, implementation keys `309`, exceptions `18`

performance threshold는 변경하지 않았다.

## 9. post-Crown frontier pressure

fresh pressure audit에서 가장 많이 반복되는 **단일 exact blocker**는:

- `weapon_change:목단:정정당당 승부다!` — 5 public memberships

이다.

Snow White : Heavy Arms는 actor 전체로 28 blockers가 남지만 여러 cadence/delivery/removal/sequential-damage family의 합계라 하나의 primitive로 보면 안 된다.

다음 single checkpoint는 **목단 `정정당당 승부다!` weapon-change lifecycle**로 잡는다.

재개 시에는 다섯 public membership을 전부 수집한 뒤 Moris에서 weapon-change 자체뿐 아니라 그 상태를 보는 normal 5-hit additional damage / self-state / cadence dependency가 있다면 한 graph로 끝까지 추적한다. generic weapon-change를 넓게 열지 않는다.
