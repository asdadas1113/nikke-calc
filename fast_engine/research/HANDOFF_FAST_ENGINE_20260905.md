# Fast Engine 작업 인계 — 2026-09-05

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`
2. `fast_engine/research/PATTERNLESS_ENCOUNTER_EVENT_CHECKPOINT_20260905.md`
3. `fast_engine/research/HANDOFF_FAST_ENGINE_20260904.md`
4. `fast_engine/research/CROWN_SELF_STACK_HEAL_CHECKPOINT_20260904.md`
5. `fast_engine/research/COVERAGE_FRONTIER_CHECKPOINT_20260904.md`
6. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`

현재 production HEAD 계열 핵심 commits:

- `4c78a27f024074a9e19391efc3d4ed6125c2d667` — patternless static score에서 unreachable encounter event blocker 제거
- `68d8dea58e4b05a630fc1d6545dcb905a7c7cfa8` — finite self-state-end + enemy named-stack damage/remove support
- `6a4c8346062eb3284ae34558d93675184b4ab154` — Crown self-stack heal-received bridge
- `46af96866b9462ec22455b9c9f5121cfa3b35bdd` — last-bullet damage delivery
- `0f522925b2cac86ab74329a9ce4d02347f739abe` — Moris outer-tick timing alignment
- `27b389ceec3f5a5ecf2b6c28b0091aa36092ebb3` / `5818329270962ef9ec46c8e259f9d79dd787d726` — public ranking exact-membership dedupe contract

---

## 1. 현재 phase

현재는 **coverage expansion** 단계다.

Fast-certified real public memberships:

- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

표준 public accounting:

- source cases: `24`
- unique ordered memberships: `23`
- certified: `2`
- coverage gaps: `21`

최근 standardized public ranking:

- clean relative error median: `+0.0626832%`
- min: `+0.0349533%`
- max: `+0.0904131%`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`

optimizer production integration은 아직 하지 않는다.

---

## 2. 최근 완료 — Asuka `섬멸`

`레이드_델타`의 `아스카 : WILLE` `섬멸`을 character-specific hack 없이 좁은 generic state-end stack semantics로 열었다.

- production: `68d8dea58e4b05a630fc1d6545dcb905a7c7cfa8`
- 첫 state-end 약 `12.35s`
- enemy `안티 AT 필드` 30 stack을 읽어 damage 후 같은 timestamp에 제거
- Moris `섬멸`: `1,303,500`
- Fast: `1,394,345.58` (`+6.97%`)
- 같은 Asuka 기존 비-섬멸 damage 오차가 `+8.29%`라 mechanic-specific formula regression 근거 없음
- `레이드_델타`는 Little Mermaid `거품 난사` blocker 하나만 남음

Nayuta periodic named-stack chain은 이미 지원된다. 실제 남은 `기억 연소`는 `SMG -> RL` cross-class actor migration이 필요해 보류했다.

---

## 3. 최근 완료 — patternless encounter event score certification

표준 static enemy 계약에서 발생하지 않는 두 encounter event를 score blocker에서만 제외했다.

- `enemy_death`
- `event:part_destroy`

production:

- `4c78a27f024074a9e19391efc3d4ed6125c2d667`

Moris 180초 실측:

- `레이드_볼륨`: encounter event notify `0`, `프리스타일` activation `0`
- `레이드_이브레이븐`: encounter event notify `0`, `일점 공격` activation `0`

정확히 제거된 blockers:

- Volume `프리스타일` normal delivery
- Volume `프리스타일` skill-state delivery
- Raven `일점 공격` skill-state delivery

runtime dispatcher는 넓히지 않았다. Crown `heal_received` guard도 그대로 남는다.

production gate:

- focused `3 passed`
- Fast pytest `234 passed, 27 subtests passed`
- standardized public ranking success

세부 근거는 `PATTERNLESS_ENCOUNTER_EVENT_CHECKPOINT_20260905.md` 참조.

---

## 4. 최신 blocker frontier

post-patternless unique-23 family counts:

- `cadence`: `68`
- `skill_state_delivery`: `50`
- `normal_delivery`: `49`
- `skill_damage`: `27`
- `weapon_change`: `12`
- `control`: `8`
- `normal_state`: `7`

unsupported families: `0`

반복도가 높은 큰 축:

- Little Mermaid `거품 난사` — 6 teams, `squad_ammo_consume:500`; 기존 실측 chronology mismatch 때문에 계속 보류
- Mokdan `정정당당 승부다!` — 5 teams, weapon change
- Crown `로얄 에타이어 4` — external heal 가능 4 teams만 계속 blocked
- Privaty reload/max-ammo — 4 teams; recipient safety 문제와 묶여 있어 broad enable 금지
- Nayuta `기억 연소` — 3 teams, cross-class `SMG -> RL`

---

## 5. 계속 보류하는 축

다음은 근거 없이 broad-enable하지 않는다.

- arbitrary/external `heal_received` chronology
- Little Mermaid team-global `squad_ammo_consume`
- cross-class weapon change
- broad weapon-change
- HP-derived state의 상수화
- unsafe recipient를 무시한 reload/max-ammo enable
- generic `bonus_damage` family enable

Little Mermaid team-global ammo는 기존 real 180초 probe에서 Moris 34,587 vs Fast 34,476 physical shots였고 일부 500-shot crossing이 약 +0.6~0.7초 늦었다.

---

## 6. 다음 단일 checkpoint

다음 우선 후보는 **one-shot / `duration_bullets:1` state lifetime**이다.

대표 public shape:

- Ada `특수 개조` — self `charge_speed_pct`, burst_cast, `duration_bullets:1`
- Ada `특수 개조 2` — self `charge_dmg_pct`, burst_cast, `duration_bullets:1`

이 후보가 좋은 이유:

- Fast는 charge shot boundary 자체를 이미 소유한다.
- duration-bullet 관련 infrastructure가 일부 이미 존재한다.
- HP/team-global ammo/cross-class weapon transition을 새로 요구하지 않는다.
- 두 public teams에서 반복된다.

다음 순서:

1. actual Ada compiled effect / base weapon / control shape 확인
2. Moris burst 후 정확히 어느 shot에 `특수 개조`/`특수 개조 2`가 적용되고 언제 제거되는지 실측
3. Fast existing bullet-lifetime support와 비교
4. runner-only generic A/B
5. positive + fail-closed regression
6. full Fast / near-tie / public frontier
7. certified membership이 증가하면 full ranking validation

단, Ada control 자체가 별도 blocker라 이 slice만으로 certified count가 증가하지 않을 가능성이 높다. 그래도 generic semantic이 좁고 재사용 가능하면 채택할 수 있다.

---

## 7. 고정 원칙

- Fast는 broad scorer이지 Moris 2.0이 아니다.
- unsupported comparison-critical mechanic은 fail closed.
- character-name hack 금지.
- fitted coefficient 금지.
- global 1/60 combat loop 금지.
- state-relevant하지 않은 global per-shot/per-pellet scheduling 금지.
- Fast parity를 위해 Moris `calculator/` semantics를 변경하지 않는다.
- static enemy scope 유지.
- engine은 candidate generation을 결정하지 않는다.
- unsupported coverage를 numeric score로 위장하지 않는다.

---

## 8. cleanup 계약

patternless encounter 조사용 temporary workflow/helper는 checkpoint에서 모두 제거한다.

영구 regression은 canonical CI가 실제 발견하도록 `fast_engine/tests/test_damage_patternless_encounter_events.py`의 `unittest.TestCase` 형태로 유지한다.

`master`는 그대로 둔다.
