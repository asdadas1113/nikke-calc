# Ada charge-hold control checkpoint — 2026-09-05

## 1. 범위

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

`master`는 수정하거나 병합하지 않는다.

이번 slice의 목적은 Ada 이름을 특별취급하는 것이 아니라 Fast dynamic charge runtime이 다음 좁은 player-control shape의 physical shot ownership을 정확히 소유하도록 하는 것이다.

- charge weapon
- non-clip
- control key exactly `hold`
- `hold.policy == own_full_burst`
- optional non-negative `lead`

production commit:

- `73145b1862ce474bd78a5674916cfd7ec6a05f1e` — `fast: certify own-full-burst charge hold`

## 2. 실제 Ada public shape

두 non-`지그_*` public Ada team에서 compiled weapon control은 동일하다.

```python
{"hold": {"policy": "own_full_burst", "lead": 0.5}}
```

관련 teams:

- `레이드_미하라에이다`
- `레이드_헬름아쿠아스노우`

Ada RL에는 `cover_during_delay=True`도 존재한다.

초기 probe에서는 이 flag를 helper에서 보수적으로 거부했지만, 실제 team safety를 분해해 확인한 결과 두 team 모두 Ada에 가능한 positive reload-speed upper bound가 `29.69%`였다. Moris의 `cover_during_delay` 특수 분기는 reload speed가 100% 이상일 때만 의미가 달라지므로 현재 public shape에서는 도달 불가능하다.

따라서 production helper는 `cover_during_delay`를 blanket reject하지 않는다. reachability 판단은 기존 `_charge_actor_score_safe()`가 담당한다.

## 3. Moris semantics

Moris `own_full_burst` hold는 cover가 아니다.

- 본인이 해당 burst cycle에 cast했을 때만 활성
- full burst 종료 시각 `anchor`를 기준으로 release를 `anchor - lead`로 정한다.
- charge가 release보다 먼저 완성되면 발사하지 않고 완성된 charge를 유지한다.
- 그동안 bullet-count lifetime state가 소모되지 않는다.
- release에서 physical charge shot이 한 발 나가고 그 shot 후 bullet lifetime이 소모된다.

Ada의 의도상 이 동작으로 burst 중 one-shot buff를 보존하고 마지막 physical shot에도 같은 state를 실을 수 있다.

## 4. Fast 구현

### `fast_engine/engine/weapon.py`

`is_supported_charge_hold_control()`을 추가했다.

허용:

- charge
- non-clip
- exactly `hold`
- policy `own_full_burst`
- `lead >= 0`

계속 fail closed:

- `tap_fire + hold`
- cover/reload와 혼합
- explicit control sequence
- clip charge weapon
- 다른 hold policy

`_ChargeActorState`에는 `charge_latched`를 추가했다.

base dynamic charge runtime에 다음 sparse hook을 추가했다.

- `_charge_shot_release_time(actor, ready_time)`
- `_latch_charge_until_release(state, ready_time)`

기본 runtime은 release가 ready time과 같으므로 기존 cadence가 변하지 않는다. supported hold actor만 subclass가 later release를 제공한다.

full charge에 도달했는데 release가 미래라면:

1. shot을 발사하지 않는다.
2. `charge_latched=True`로 둔다.
3. `phase_end`를 release의 Moris observed outer-tick boundary로 옮긴다.
4. release까지 새 per-frame/per-shot event를 만들지 않는다.

latched 상태에서는 live charge-speed signature가 바뀌어도 이미 완성된 charge의 release boundary를 재계산하지 않는다.

### `fast_engine/engine/dynamic_weapon.py`

`_charge_hold_release`를 actor별 sparse state로 추가했다.

기존 rapid `begin_full_burst()` anchor hook을 그대로 재사용해:

- 이번 cycle에 cast한 supported charge actor만 선택
- `full_burst_end - lead`를 observed release로 변환
- 기존 future plan invalidate
- 새 release boundary만 replan

한다.

### `fast_engine/engine/score.py`

기존 `_charge_actor_score_safe()`의 모든 control 거부를 좁혔다.

- supported pure charge hold만 control을 허용
- 나머지 charge control은 그대로 fail closed
- supported hold actor를 dynamic charge score owner set에 포함
- `cover_during_delay` 등 다른 위험은 기존 score-safety 조건으로 계속 검사

## 5. outer-tick / live-state regression

synthetic regression:

- base charge: 1.0s
- full burst start: 0.2s
- full burst end: 3.0s
- lead: 0.5s
- nominal release: 2.5s

Moris outer tick에서 실제 observed release는 약 `2.5166667s`다.

검증한 순서:

1. 1.0s full-charge deadline에서 shot을 발사하지 않고 latch
2. ammo는 그대로 유지
3. 1.2s에 live charge-speed effect를 활성화
4. latched release는 움직이지 않음
5. observed release에서 exactly one physical shot
6. ammo가 한 발만 감소

actor가 그 cycle에서 cast하지 않은 경우에는 같은 control이 있어도 hold가 걸리지 않는다.

## 6. Ada `특수 개조 2`와의 관계

직전 checkpoint에서 Ada `특수 개조`의 one-shot `charge_speed_pct` lifetime은 이미 지원됐다.

`특수 개조 2`는:

- self `charge_dmg_pct=+1500`
- `burst_cast`
- `duration_bullets:1`

이다.

조사 결과 direct-damage bullet lifetime semantics 자체는 기존 Fast runtime이 이미 지원하고 있었다. blocker가 남던 이유는 delivery semantics가 아니라 Ada physical shot ownership이 control 때문에 uncertified였기 때문이다.

이번 charge-hold ownership을 열자 별도 direct-damage 특례 없이 기존 support가 그대로 활성화되어 다음 blocker도 함께 사라졌다.

- `normal_delivery:에이다:특수 개조 2:charge_dmg_pct`
- `skill_state_delivery:에이다:특수 개조 2:charge_dmg_pct`

## 7. 검증 결과

runner-only v3 gate:

- focused: `27 tests` passed
- full Fast: `56 modules / 245 tests` passed

standardized public probe:

- source cases: `24`
- unique ordered memberships: `23`
- certified: `2`
- coverage gaps: `21`
- clean relative error median: `0.0006268322047938701`
- min: `0.000349533271479352`
- max: `0.0009041311381083883`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`
- unsupported families: `0`

Fast test-side 180s static score benchmark:

- median approximately `100.13ms`

## 8. blocker delta

직전 production frontier 대비:

- cadence: `66 -> 66`
- skill_state_delivery: `50 -> 48`
- normal_delivery: `49 -> 47`
- skill_damage: `27 -> 27`
- weapon_change: `12 -> 12`
- control: `8 -> 6`
- normal_state: `7 -> 7`

두 public Ada team에서 Ada 이름을 포함한 blocker는 0이 됐다.

`레이드_미하라에이다`에는 여전히 다른 actor의 blocker가 남는다. 대표적으로:

- `control:미하라 : 본딩 체인`
- Grave ammo/reload/max-ammo cadence
- `D : 킬러 와이프` direct state/delivery

`레이드_헬름아쿠아스노우`에는 Helm Aqua / Snow White 관련 blocker가 남는다.

따라서 certified membership은 `2` 그대로다.

## 9. 해석

이번 변경은 Ada를 위해 control을 예외처리한 것이 아니다.

Fast가 확정된 full-burst anchor 하나와 charge-completion boundary 하나만으로 표현 가능한 pure hold를 sparse state machine에 편입한 것이다. global 60 Hz loop도, 모든 charge shot의 blanket materialization도 추가하지 않았다.

또한 `특수 개조 2`의 blocker 제거는 별도 broad direct-damage enable이 아니라 기존 certified bullet-lifetime support가 정확한 physical shot owner를 얻은 결과다.

현재 standardized certified 2팀의 score/ranking은 움직이지 않았으므로 관측된 ranking regression 근거는 없다.

## 10. 다음 checkpoint

다음은 `레이드_미하라에이다`의 `control:미하라 : 본딩 체인` safety diagnosis다.

`컨트롤_미란다미하라`는 이미 certified인데 Ada team에서는 같은 캐릭터가 control blocker를 만든다. 두 membership의 compiled control과 team-dependent invalidator를 항목별로 비교해, generic proof gap인지 실제 unsupported interaction인지 먼저 확정한다.

production patch는 그 진단 결과가 generic하고 comparison-safe할 때만 고려한다.
