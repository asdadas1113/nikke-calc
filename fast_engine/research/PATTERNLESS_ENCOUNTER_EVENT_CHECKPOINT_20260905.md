# Fast Engine patternless encounter-event checkpoint — 2026-09-05

## 1. 목적

표준 public ranking 시나리오에서 실제로 발생할 수 없는 encounter event가 단순히 dispatcher에서 executable하다는 이유로 score blocker에 남는 문제를 좁게 정리했다.

이번 변경은 runtime에 새 event chronology를 추가하지 않는다. **patternless static score 인증에서만**, 현재 공통 적 계약으로 도달 불가능함이 증명된 event consumer를 blocker에서 제외한다.

고정 원칙:

- character-name hack 없음
- broad named-event enable 없음
- runtime dispatcher 의미 변경 없음
- Moris `calculator/` 변경 없음
- 실제 encounter producer가 있는 시나리오로 일반화하지 않음

## 2. 대상 effect

### Volume `프리스타일`

- trigger: `enemy_death`
- public team: `레이드_볼륨`
- 기존 blockers:
  - `normal_delivery:볼륨:프리스타일:atk_pct`
  - `skill_state_delivery:볼륨:프리스타일:atk_pct`

### Raven `일점 공격`

- trigger: `event:part_destroy`
- public team: `레이드_이브레이븐`
- 기존 blocker:
  - `skill_state_delivery:레이븐:일점 공격:dot_dmg_pct`

## 3. Moris reachability 확인

표준 public ranking 계약은 `calculator.timeline.DEFAULT_ENEMY`를 그대로 사용한다.

해당 적은:

- `has_parts=False`
- part-break pattern 설정 없음
- 고정 180초 target이며 enemy-death chronology를 생성하지 않음

Moris 180초 실측:

### `레이드_볼륨`

- Moris score: `3,035,228,975`
- `enemy_death` notify: `0`
- `part_destroy` notify: `0`
- `프리스타일` affected buff activation: `0`

### `레이드_이브레이븐`

- Moris score: `2,840,975,141`
- `enemy_death` notify: `0`
- `part_destroy` notify: `0`
- `일점 공격` affected buff activation: `0`

Moris에는 `event:part_destroy` producer 자체는 존재한다. 따라서 이 event를 전역 NOP으로 취급하지 않고 **현재 patternless static score 계약에서만** unreachable로 분류한다.

## 4. production change

production commit:

- `4c78a27f024074a9e19391efc3d4ed6125c2d667` — `fast: ignore unreachable patternless encounter events`

변경은 `fast_engine/engine/score.py`의 `_PATTERNLESS_UNREACHABLE_EVENT_KEYS`에 다음 두 key를 추가하는 것뿐이다.

- `enemy_death`
- `event:part_destroy`

기존 `received_hit` patternless-unreachable 처리와 같은 score-certification 경계에 둔다.

중요:

- `TriggerDispatcher.is_executable_effect()`는 그대로다.
- 해당 effect를 generic NOP으로 rewrite하지 않는다.
- encounter-aware runtime이 생기면 그 runtime의 score 계약은 별도로 검증해야 한다.

## 5. blocker 변화

정확히 다음 3개 blocker가 제거됐다.

- Volume `프리스타일` normal delivery
- Volume `프리스타일` skill-state delivery
- Raven `일점 공격` skill-state delivery

Crown `event:heal_received` 같은 다른 named-event는 계속 fail closed임을 focused regression으로 확인했다.

public accounting은 그대로다.

- source cases: `24`
- unique ordered memberships: `23`
- certified: `2`
- gaps: `21`

post-change blocker-family counts:

- `cadence`: `68`
- `skill_state_delivery`: `50`
- `normal_delivery`: `49`
- `skill_damage`: `27`
- `weapon_change`: `12`
- `control`: `8`
- `normal_state`: `7`

unsupported families: `0`

## 6. 검증

production gate:

- focused regression: `3 passed`
- Fast full pytest: `234 passed, 27 subtests passed`
- standardized public ranking probe: success

public certified pair 결과:

- clean relative error median: `+0.0626832%`
- min: `+0.0349533%`
- max: `+0.0904131%`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`

영구 regression은 canonical CI의 Fast damage discovery에 포함되도록 `test_damage_patternless_encounter_events.py`의 `unittest.TestCase` 형태로 유지한다.

## 7. 다음 frontier

이번 slice는 blocker hygiene를 정리했지만 certified membership 수를 늘리지는 않았다.

계속 보류:

- Little Mermaid team-global `squad_ammo_consume`
- Nayuta 등 cross-class weapon change
- broad HP chronology
- arbitrary external heal chronology

다음 후보는 이미 소유한 shot/buff lifetime 의미를 재사용할 수 있는 **`duration_bullets:1` 계열**을 우선 검토한다. 대표 public shape는 Ada `특수 개조` / `특수 개조 2`이며, 먼저 Moris의 한 발 lifetime과 charge-shot 경계를 실측한 뒤 generic 지원 가능 여부를 판단한다.
