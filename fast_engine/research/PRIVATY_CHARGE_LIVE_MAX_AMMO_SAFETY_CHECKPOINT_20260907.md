# Privaty charge live max-ammo safety 체크포인트 — 2026-09-07

## 0. 결론

post-Moran frontier에서 4회씩 반복되던 Privaty `EX 매거진 2 + 3`을 다음 단일 checkpoint로 조사했다.

대상 blocker:

- `cadence:프리바티:EX 매거진 2:reload_speed_pct`
- `cadence:프리바티:EX 매거진 3:max_ammo_pct`

조사 결과 이 둘을 public roster에 바로 열면 안 된다.

네 public membership 모두에 별도의 recipient cadence dependency가 있고, 기존 Fast가 아직 소유하지 않는 cover-reload / clip / neighboring weapon-change family를 통과해야 한다. 따라서 blocker를 제거하지 않고 fail-closed를 유지했다.

대신 Moris oracle을 따라가며 **DynamicChargeCadenceRuntime의 live max-ammo 의미론 두 군데가 Moris와 다르다**는 것을 발견했고, 이를 먼저 수정했다.

semantic production commit:

- `87b061d76b87e9815f0474731fa0222d4115f123` — `Fast: align charge live max-ammo semantics`

이 checkpoint의 성공 조건은 certification 수 증가가 아니라:

1. charge live magazine이 Moris와 같은 값/순서로 변함
2. Privaty public pair는 아직 전부 fail-closed
3. 기존 public frontier와 ranking safety가 변하지 않음

이다.

## 1. Privaty exact shape

네 public roster에서 compiled shape는 동일하다.

### `EX 매거진 2`

- type: `buff`
- stat: `reload_speed_pct`
- value: `+51.16`
- target: `all_allies`
- duration: `10s`
- max stack: `1`
- trigger: `full_burst_start`
- parameters: `favorite:3`

### `EX 매거진 3`

- type: `buff`
- stat: `max_ammo_pct`
- value: `-50.66`
- target: `all_allies`
- duration: `10s`
- max stack: `1`
- trigger: `full_burst_start`
- parameters: `favorite:3`

public membership:

- `스쿼드2`
- `레이드_아니스서머메이든`
- `레이드_라피앨리스`
- `레이드_트리나홍련`

첫 full-burst activation은 조사 harness에서 약 `3.4s`, expiry는 `13.4s`였다.

## 2. Moris oracle — negative live max ammo

Moris의 핵심 동작은 다음이다.

1. `max_ammo_pct` source는 각 source를 base magazine에 개별 적용한 뒤 반올림한다.
2. negative live modifier가 들어와 effective max ammo가 현재 ammo보다 작아지면, **active reload 중이 아닌 한 즉시 현재 ammo를 새 cap으로 clamp**한다.
3. active reload 중에는 중간 clamp하지 않는다.
4. reload 완료 시 그 시점의 live max ammo로 refill한다.
5. expiry로 cap이 다시 커져도 현재 ammo를 위로 자동 refill하지 않는다.
6. effective magazine은 최소 1이다.

관찰 예:

- `스쿼드2` Snow White : Heavy Arms: `12 -> 11` 즉시 clamp
- `레이드_아니스서머메이든` Aid / Maiden: `12 -> 11` 즉시 clamp
- `레이드_라피앨리스` Little Mermaid `267 -> 215`, Crown `697 -> 566`, Rapi : Red Hood `697 -> 566`, Privaty `39 -> 30` 즉시 clamp
- Alice는 activation 당시 current ammo가 새 cap보다 작아 clamp가 필요 없었다.

## 3. Moris oracle — reload lifetime

reload speed는 reload action 전체에서 매 순간 재계산되는 값이 아니다.

- reload start에서 `reload_start_delay`와 reload action duration을 현재 reload speed로 계산한다.
- 이미 시작된 reload의 finish time은 이후 buff expiry로 다시 늘어나지 않는다.
- reload completion 시점의 `post_reload_delay`는 completion 당시 state를 본다.
- refill magazine은 completion 당시 live max ammo를 본다.

따라서 `EX 매거진 2`와 `3`은 같은 10초 transaction이라도 단순한 하나의 scalar multiplier가 아니다. reload start snapshot과 live refill cap을 분리해서 보아야 한다.

## 4. 발견된 Fast divergence

rapid runtime은 이미 다음을 보유하고 있었다.

- static-folded max-ammo source와 live source 분리
- source-by-source percentage quantization
- live cap 하락 시 current ammo clamp

반면 charge runtime은 조사 시점에:

- live percentage를 합산한 뒤 한 번 반올림
- live cap이 내려가도 현재 ammo를 clamp하지 않음

이었다.

Privaty를 그대로 certification하면 Snow/Aid/Maiden 같은 charge actor에서 comparison-critical cadence가 달라질 수 있어 false-supported가 된다.

## 5. production repair

`DynamicChargeCadenceRuntime._full_ammo()`는 이제:

1. permanent unconditional self source를 static-folded source로 분리한다.
2. static `max_ammo_pct`도 source별로 base magazine에 적용해 반올림한다.
3. active store에서는 static-folded source를 제외해 double count를 막는다.
4. live `max_ammo_pct`를 source별로 반올림해 더한다.
5. live flat modifier를 더한다.
6. 최종 cap은 최소 1로 clamp한다.

`sync(now)`는:

- live cap이 내려갔고
- actor가 active `reloading` phase가 아니며
- current ammo가 새 cap보다 크면

즉시 current ammo를 cap으로 clamp하고 sparse plan을 invalidate한다.

active reload 중에는 중간 clamp하지 않고 기존 reload completion path가 live cap을 읽는다.

## 6. staged failure에서 잡힌 double-count 위험

첫 repair 시도는 active store의 max-ammo source를 모두 다시 source-quantize했다.

그 결과 Snow Heavy의 cap이 Moris `11`이 아니라 Fast `3`이 됐다.

원인은 permanent self max-ammo source가 이미 static cadence base에 반영되어 있는데 active store에서 다시 더한 double count였다.

기대값을 완화하지 않고 rapid runtime과 같은 static/live split으로 수정했고, Snow first-FB `12 -> 11` parity가 통과했다.

## 7. 왜 Privaty pair는 아직 public certification하지 않는가

### `스쿼드2`

- Tswei: auto지만 existing rapid score safety 실패
- Nayuta: auto지만 existing rapid score safety 실패
- Snow Heavy: non-clip charge / cover, upper reload speed `80.85%`로 자체는 safe

Privaty all-allies effect를 열려면 Tswei/Nayuta의 별도 weapon/cadence dependency까지 먼저 소유해야 한다.

### `레이드_아니스서머메이든`

- Maiden : Ice Rose: charge + `cover_during_delay`
- conservative positive reload-speed upper bound `130.13%`
- existing charge safety가 의도적으로 reject

Moris의 `reload_speed >= 100%` cover-during-delay branch가 아직 Fast에 없다.

### `레이드_라피앨리스`

- Alice: charge + `cover_during_delay`
- upper bound `125.2%`
- same >=100% special branch 때문에 fail-closed

### `레이드_트리나홍련`

- Trina: charge RL + `is_clip=True`
- dynamic charge clip reload는 아직 certification 대상이 아니다.

따라서 네 roster에서 EX Magazine 2/3 blocker를 제거하지 않는 것이 현재 올바른 결과다.

## 8. regression

신규 test:

- `fast_engine/tests/test_dynamic_charge_max_ammo_semantics.py`

5개 계약:

1. 두 live +25% source / base magazine 2에서 source별 반올림으로 `4`
2. charge live cap 하락 시 non-reloading current ammo 즉시 clamp
3. reload finish는 expiry 이후 live cap을 사용
4. Privaty 네 public pair 모두 blocker 유지
5. `스쿼드2` Snow Heavy first-FB magazine `12 -> 11` Moris parity

focused validation:

- 신규 `5/5`
- dynamic reload `12/12`
- dynamic weapon-change `4/4`
- performance contract `2/2`

post-repair full Fast discovery:

- `350/350` success
- structural median `141.31ms`, events `539`
- RAPI parity unchanged:
  - reference `236373847.0`
  - Fast `236465053.42473748`
  - relative error `0.0003858566668650809`

## 9. public frontier

repair 뒤 frontier는 의도적으로 그대로다.

- source cases `24`
- unique memberships `23`
- certified `6`
- gaps `17`

certified:

- `스쿼드4`
- `레이드_레드후드퀀시`
- `레이드_아스카루드밀라`
- `레이드_델타`
- `레이드_볼륨`
- `컨트롤_미란다미하라`

blocker families:

- cadence `53`
- control `4`
- normal delivery `46`
- normal state `16`
- periodic grid `1`
- skill damage `25`
- skill-state delivery `48`
- weapon change `7`

Privaty EX 2/3는 각각 4회 그대로 남는다.

## 10. checkpoint 해석

이 작업은 coverage expansion 실패가 아니다.

raw pressure만 보고 4개 roster에서 두 blocker를 지웠다면, 실제로는:

- static/live max-ammo double counting 위험
- charge current-ammo clamp 누락
- >=100% cover reload branch
- clip reload
- neighboring weapon-change/cadence dependencies

를 숨긴 채 supported로 표시했을 가능성이 있다.

따라서 이 checkpoint는 **false-supported safety closure를 한 단계 더 닫은 prerequisite restoration**으로 기록한다.

## 11. 다음 checkpoint 선정 기준

다음에는 raw exact count만 보지 않는다.

Privaty / Little Mermaid / Crown처럼 이미 확인된 상위 dependency에 막힌 family는 뒤로 미루고, 현재 public frontier에서 독립적으로 ownership graph를 닫을 수 있는 반복 blocker를 우선한다.

후보 중 우선 확인 대상은 `weapon_change:나유타:기억 연소`다. 3개 public membership에 반복되며, finite weapon-change lifecycle이 기존 Moran primitive와 좁게 연결되는지 먼저 shape audit한다. shape가 넓으면 Alice/Anis-Star 등 다음 dependency-adjusted 후보로 넘어간다.
