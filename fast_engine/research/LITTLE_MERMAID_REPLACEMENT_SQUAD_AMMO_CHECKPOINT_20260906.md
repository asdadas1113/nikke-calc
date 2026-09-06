# Little Mermaid replacement / squad-ammo lifecycle 체크포인트 — 2026-09-06

## 0. 결론

public `레이드_델타`의 마지막 두 blocker를 Moris oracle로 끝까지 추적한 뒤, Fast가 두 의존성을 별개의 좁은 ownership proof로 소유하도록 확장했다.

대상 blocker:

1. `normal_state:리틀 머메이드:터진 거품 3:remove_named_buff`
2. `skill_damage:리틀 머메이드:거품 난사:sequential_damage:10`

semantic production commit:

- `ab3243ac3a83b3b0e7526b3a5f3b2d51e0c7c019` — `Fast: own Little Mermaid replacement and squad-ammo lifecycle`

결과적으로 `레이드_델타`는 네 번째 public certified membership이 됐다.

이번 checkpoint는 generic stun, generic named removal, generic `squad_ammo_consume`, generic sequential damage를 연 것이 아니다. 정확한 producer → replacement/control/remover graph와 전원 rapid cadence ownership을 동시에 증명할 때만 blocker를 제거한다.

## 1. Moris oracle — `거품` replacement lifecycle

Little Mermaid의 relevant actor-effect order는 다음이다.

1. `거품`: enemy `received_dmg_pct +5.05%`, harmful, permanent, `event:enemy_spawn`
2. `터진 거품`: enemy `received_dmg_pct +5.05%`, harmful, permanent, `target_state:거품`, `hit_count:50`
3. `터진 거품 2`: enemy stun, 3초, 같은 condition / hit gate
4. `터진 거품 3`: `remove_named_buff(target_effect=거품)`, 같은 condition / hit gate

`레이드_델타` Moris trace에서 Little Mermaid의 50번째 hit는 정확히 `2.05s`에 관찰됐다. 같은 timestamp에서 actor effect order대로 replacement가 먼저 생기고 stun이 적용된 뒤 원본 `거품`이 제거된다.

이 remover를 무시하면 원본 `거품 +5.05%`와 replacement `터진 거품 +5.05%`가 동시에 남아 comparison-critical damage가 과대 계산된다. 따라서 remover 단독을 permissive하게 여는 방식은 false-supported다.

Fast는 `certified_enemy_received_damage_replacements()`라는 compile-time graph proof를 만들고, 해당 proof가 반환한 exact remover만 runtime에서 실행한다. stun 자체를 generic executable state로 승격하지 않는다.

## 2. replacement fail-closed 경계

첫 owned graph는 다음을 모두 요구한다.

- source는 harmful permanent enemy `received_dmg_pct`
- source trigger는 정확히 `event:enemy_spawn`
- replacement는 같은 actor의 동일 값/동일 polarity permanent enemy `received_dmg_pct`
- replacement / finite enemy stun / remover가 actor effect order에서 연속
- 셋 모두 정확히 같은 reducible `hit_count:N`
- 셋 모두 source name을 보는 단일 `TARGET_STATE` gate
- remover는 exact `remove_named_buff(target_effect=<source>)`
- external named-state observer/mutator 없음
- external `target_stunned` consumer 없음
- 관련 named state의 `state_end` consumer 없음

값, target name, order, gate, 외부 observer 중 하나라도 달라지면 proof가 사라지고 기존 blocker가 복귀한다.

## 3. Moris oracle — `거품 난사` global ammo counter

`거품 난사` shape:

- damage stat: `sequential_damage:10`
- value: `85.0`
- trigger: `squad_ammo_consume:500`
- fixed 10-hit sequential damage

`레이드_델타` Moris trace의 global physical-ammo crossings:

- 500발: `4.133333333333324s`
- 1000발: `6.033333333333317s`
- 1500발: `7.93333333333331s`

각 crossing에서 `거품 난사`는 정확히 10 hit로 실행된다.

중요한 same-frame order는 다음이다.

1. threshold-crossing shot의 ammo 감소
2. `squad_ammo_consume` notify
3. `거품 난사` skill damage
4. 그 crossing normal shot의 damage
5. post-shot `hit_count` 등

따라서 일반 weapon boundary와 같은 post-shot dispatch로 처리하면 늦다. Fast는 이 exact family에만 `PRE_SHOT_BOUNDARY`를 두어 global crossing에서만 scheduler event를 만든다.

## 4. sparse global-ammo ownership

첫 `squad_ammo_consume` slice는 전투의 모든 shot을 scheduler에 올리지 않는다.

`레이드_델타`는 다섯 명 전원이:

- `auto` / `auto_warmup`
- non-clip
- 기존 `_rapid_actor_score_safe=True`
- 기존 dynamic rapid score runtime 소속

이다.

Fast는 각 rapid state의 복사본을 전진시켜 **다음 global modulo crossing 하나**만 예측하고 그 시각에 `PRE_SHOT_BOUNDARY` 하나를 예약한다. crossing 이후 다시 다음 crossing만 계획한다.

첫 slice는 다음에서 즉시 fail closed다.

- squad actor 중 하나라도 certified rapid runtime 밖
- clip/charge/unsupported fire mode 혼합
- weapon control 존재
- `max_ammo_infinite` 가능성
- non-NOP `squad_ammo_consume` consumer가 둘 이상
- fixed positive `sequential_damage:N`이 아님
- 단일 unconditional modulo `squad_ammo_consume:M`이 아님
- trigger-count reducer가 개입

따라서 public `레이드_일레그`의 별도 `squad_ammo_consume:100` gauge/damage/removal family는 계속 fail closed다.

## 5. rapid 60Hz observation drift 발견과 수정

첫 staged implementation에서 Little Mermaid 50번째 hit가 Fast `2.041666...s`, Moris `2.05s`로 어긋났다.

원인은 단순 float 오차가 아니었다.

Moris auto weapon은:

- `next_fire_time += 1/fire_rate`로 **명목 deadline**을 누적
- 실제 shot은 outer 60Hz tick 중 처음 `t >= next_fire_time`인 tick에서 관찰
- 다음 deadline은 실제 관찰 shot time이 아니라 이전 nominal deadline을 기준으로 누적

한다.

초기 Fast staged path는 `observed shot time + interval`을 다음 시각으로 사용해 24/s SMG에서 반 프레임 drift가 누적됐다.

수정은 global 60Hz loop를 추가하지 않았다. squad-ammo exact cadence가 필요한 rapid state에만 `fire_deadline`을 보존하고, 의미 있는 물리 shot/crossing 시각을 기존 `moris_observed_tick()`으로 sparse하게 관찰한다. 이후 50번째 hit가 Moris와 정확히 `2.05s`로 일치했다.

## 6. pre-shot stale-token 실패와 수정

첫 staged global crossing test는 crossing이 0회였다.

원인은 `PRE_SHOT_BOUNDARY` 자체가 아니라 공통 phase-30 scoring에서 event 처리 전에 `=t` normal shot까지 먼저 소비해 crossing token이 stale이 된 것이었다.

수정 후 score ordering은:

- ordinary phase-30 event: 기존처럼 `=t` shot 선소비
- `PRE_SHOT_BOUNDARY`: `t` 직전까지만 score consume → ammo/global signal/skill 처리 → crossing normal shot score

으로 분리됐다.

이 두 staged failure는 모두 harness 기대값을 완화하지 않고 runtime ordering/cadence 의미론을 고쳐 해결했다.

## 7. regression

신규 contract:

- `fast_engine/tests/test_damage_little_mermaid_lifecycle.py`

6개 계약:

1. public Delta blocker zero + exact owned IDs
2. Moris/Fast 50th-hit replacement/removal parity
3. 500/1000/1500 global crossing parity + skill-before-normal ordering
4. sequential damage exact 10-hit spec
5. neighboring replacement shapes fail closed
6. wider squad-ammo family stays closed

focused gate:

- `26/26` success

전체 Fast discovery에서 처음에는 4개의 이전 frontier expectation만 stale했다. 세 테스트의 certified count `3→4`와, Asuka state-end 테스트의 “Little Mermaid blocker가 남아 있어야 함” 기대를 독립 Little Mermaid proof와 공존하도록 갱신했다. mechanic-specific assertion은 유지했다.

staged final:

- Fast discovery `330/330`
- performance median `132.59ms`, events `539`
- RAPI parity unchanged: reference `236373847.0`, Fast `236465053.42473748`, relative error `0.0003858566668650809`

## 8. public frontier

canonical filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외
- exact ordered membership dedupe

결과:

- source cases `24`
- unique memberships `23`
- certified **4**
- gaps **19**

certified:

- `레이드_레드후드퀀시`
- `레이드_델타`
- `레이드_볼륨`
- `컨트롤_미란다미하라`

blocker families:

- normal delivery `47`
- normal state `16`
- skill damage `25`
- skill-state delivery `49`
- weapon change `12`
- cadence `57`
- control `4`
- periodic grid `1`

Volume checkpoint 대비:

- certified `3 → 4`
- gaps `20 → 19`
- normal state `22 → 16`
- skill damage `27 → 25`
- 나머지 unchanged

## 9. canonical gate

pre-cleanup canonical CI:

- run `34020420109`
- job `101451859865`
- result: success
- Fast damage `221/221`
- Fast complete discovery `330/330`
- structural performance median `167.08ms`, events `539`
- RAPI parity unchanged
- calculator `137/137` (`1` skip)
- optimizer `374/374`
- bridge `31/31` (`1` skip)
- site `385/385`
- golden `29/29`
- doclint: characters `199`, implementation keys `309`, exceptions `18`

performance threshold는 변경하지 않았다.

## 10. 다음 checkpoint

다음 단일 checkpoint는 **Crown `로얄 에타이어 4` normal/skill shared recipient/lifetime semantics**다.

Little Mermaid 작업을 더 넓히지 않고, 먼저 Crown에서 같은 recipient/lifetime state를 normal attack과 skill damage가 어떻게 공유하는지 Moris trace로 고정한다.
