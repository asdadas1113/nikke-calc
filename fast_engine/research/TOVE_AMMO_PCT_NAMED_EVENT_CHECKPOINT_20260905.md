# Fast Engine — Tove percent-ammo named-event checkpoint (2026-09-05)

## 1. 목적

표준 public frontier에서 반복되는 delivery blocker 중, 기존 Fast runtime이 거의 전부 소유하고 있으면서 Moris와의 의미론 차이가 한 곳으로 좁혀지는 generic slice를 찾았다.

대상 실데이터는 토브의 다음 연쇄다.

- `급조 탄환`: `instant / ammo_charge_pct`, self, `hit_count:10`
- `임시 개조 2`: `buff / crit_dmg +5.24`, all allies, 5s, `event:급조 탄환`

목표는 토브 이름을 특별취급하는 것이 아니라 **성공한 percent-ammo instant가 자신의 이름으로 named event를 방출하는 Moris 의미론**을 Fast에 좁게 추가하는 것이다.

## 2. Moris 의미론

`calculator/timeline.py`의 `handle_ammo_charge_pct`는 다음 순서를 사용한다.

1. 대상 장탄을 percent 값으로 충전한다.
2. 최대 장탄을 넘지 않게 cap한다.
3. 필요한 reload-cancel 처리를 한다.
4. 효과에 이름이 있으면 `event:{effect.name}`을 같은 caster로 notify한다.

중요한 대조군은 `ammo_charge_flat`이다. Moris의 flat handler에는 이 named-event notify가 없다.

따라서 이번 지원 범위는 의도적으로 다음처럼 비대칭이다.

- `ammo_charge_pct` named provider: 좁은 조건에서 지원
- `ammo_charge_flat` named provider: 계속 fail closed

flat까지 일반화하면 Moris와 다른 의미가 된다.

## 3. 기존 Fast gap

Fast는 이미 다음을 갖고 있었다.

- reducible `hit_count` 기반 dynamic ammo refill
- percent refill의 Python `round` / full-ammo cap
- direct damage-facing `crit_dmg` buff runtime
- `event:{name}` consumer parsing / dispatch
- named-event source certification

빠진 것은 두 곳이었다.

1. `ammo_charge_pct` instant 성공 뒤 `event:{name}` emission
2. named-event source proof가 provider를 buff로만 인정하던 점

score 쪽에는 이 누락을 방어하기 위해 `_ammo_charge_named_event_safe()`가 named consumer가 존재하는 ammo refill을 통째로 fail closed하고 있었다.

## 4. 구현 범위

production commit:

- `47e8c47278bbd9125b42a8f08bde632638796026` — `fix: emit percent ammo refill named events`

### Dispatcher

성공한 `ammo_charge_pct` instant에 한해:

- 효과 이름이 존재하고
- 실제 named-event consumer가 필요한 이름일 때
- `event:{effect.name}`을 provider actor에 dispatch한다.

`ammo_charge_flat`은 emission하지 않는다.

runtime named-source proof는 instant provider를 다음 조건에서만 인정한다.

- consumer와 같은 actor
- stat exactly `ammo_charge_pct`
- value가 존재하고 non-negative
- `battle_start` source가 아님
- target runtime-supported
- 가능한 ally target이 존재
- provider 자체가 Dispatcher executable

기존 buff-provider proof와 external `heal_received` 특수 proof는 유지한다.

### Score certification

`_ammo_charge_named_event_safe()`는 named consumers가 없으면 기존과 같다.

consumer가 있으면:

- pct provider만 고려
- 모든 consumer가 same-actor buff
- 각 consumer가 direct-damage runtime-supported

일 때만 provider named-event dependency를 허용한다.

named-event consumer의 source proof에서도 같은 pct-only instant provider shape를 인정한다.

provider cadence certification과 source certification은 분리한다. 즉 named-event delivery를 정확히 증명해도 provider의 cadence가 다른 이유로 unsafe하면 cadence blocker는 그대로 남는다.

## 5. regression

영구 regression:

- `fast_engine/tests/test_ammo_pct_named_event.py`
- `fast_engine/tests/test_named_buff_event_runtime.py`의 실제 Tove expectation 갱신

검증 내용:

1. synthetic pct refill이 named event를 방출하고 consumer를 활성화한다.
2. synthetic flat refill은 계속 fail closed이며 event를 방출하지 않는다.
3. 실제 토브에서 10회 `hit_count` 뒤 `급조 탄환`이 1회 발동하고 `임시 개조 2`가 전 아군에게 적용된다.
4. 실제 public Tove delivery blocker만 제거되고 별도 cadence blocker는 남는다.

## 6. runner-only A/B

최종 isolated A/B:

- workflow run: `33912561440`
- job: `101152127477`

결과:

- focused regression: `16/16`
- full Fast regression: `248/248`
- `레이드_소다`, `스쿼드3`에서 다음 blocker 제거:
  - `normal_delivery:토브:임시 개조 2:crit_dmg`
  - `skill_state_delivery:토브:임시 개조 2:crit_dmg`

## 7. production 재검증

post-promotion validation:

- source HEAD: `d21c68517f83dee638d8ca566291534e1c23712f`
- workflow run: `33912764211`
- job: `101152802424`

결과:

- focused: `16/16`
- full Fast: `248/248`
- standardized public accounting:
  - unique memberships: `23`
  - certified: `2`
  - gaps: `21`

certified memberships는 여전히:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

Tove가 있는 두 public team에는 다음 별도 cadence blocker가 그대로 남는다.

- `cadence:토브:급조 탄환:ammo_charge_pct`
- `cadence:토브:임시 개조:max_ammo_flat`
- `cadence:토브:개조 성공 2:attack_speed_pct`

따라서 이번 slice로 certified universe가 증가하지 않았고 standardized ranking은 재실행하지 않았다. 이것은 ranking 변화가 아니라 coverage blocker 분해의 진전이다.

## 8. fail-closed 유지

이번 변경으로 다음을 넓히지 않았다.

- `ammo_charge_flat` named-event emission
- cross-actor instant named provider
- arbitrary instant stat named-event emission
- Tove의 dynamic max-ammo stack
- Tove의 attack-speed cadence
- external `heal_received`
- `squad_body_hit`
- `squad_ammo_consume`

특히 `레이드_미하라에이다`의 미하라 control은 D : 킬러 와이프 `타겟 섬멸 ATK`가 executable global `squad_body_hit` chronology에 의존하므로 no-patch/fail-closed 상태를 유지한다.
