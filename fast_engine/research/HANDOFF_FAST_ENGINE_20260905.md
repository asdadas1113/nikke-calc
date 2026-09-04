# Fast Engine 작업 인계 — 2026-09-05

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`
2. `fast_engine/research/TOVE_AMMO_PCT_NAMED_EVENT_CHECKPOINT_20260905.md`
3. `fast_engine/research/ADA_CHARGE_HOLD_CONTROL_CHECKPOINT_20260905.md`
4. `fast_engine/research/ADA_ONE_SHOT_CHARGE_SPEED_CHECKPOINT_20260905.md`
5. `fast_engine/research/PATTERNLESS_ENCOUNTER_EVENT_CHECKPOINT_20260905.md`
6. `fast_engine/research/COVERAGE_FRONTIER_CHECKPOINT_20260904.md`
7. `fast_engine/research/CROWN_SELF_STACK_HEAL_CHECKPOINT_20260904.md`
8. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`

현재 최신 production semantic commit:

- `47e8c47278bbd9125b42a8f08bde632638796026` — percent-ammo instant named-event emission / source certification

직전 주요 production commits:

- `73145b1862ce474bd78a5674916cfd7ec6a05f1e` — pure charge `own_full_burst` hold ownership
- `f70871e36ddf28a2474e7e25d6d7254cf9fe26cd` — Ada one-shot charge-speed lifetime
- `4c78a27f024074a9e19391efc3d4ed6125c2d667` — patternless unreachable encounter-event blocker 제거
- `68d8dea58e4b05a630fc1d6545dcb905a7c7cfa8` — finite self-state-end + enemy named-stack damage/remove
- `6a4c8346062eb3284ae34558d93675184b4ab154` — Crown self-stack heal-received bridge
- `46af96866b9462ec22455b9c9f5121cfa3b35bdd` — last-bullet damage delivery
- `0f522925b2cac86ab74329a9ce4d02347f739abe` — Moris outer-tick timing alignment

---

## 1. 현재 phase / public accounting

현재는 **coverage expansion** 단계다.

Fast-certified real public memberships:

- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

표준 public accounting:

- source cases: `24`
- unique ordered memberships: `23`
- certified: `2`
- coverage gaps: `21`

latest standardized public ranking은 certified universe가 2개일 때의 기존 결과를 유지한다.

- clean relative error median: `+0.0626832%`
- min: `+0.0349533%`
- max: `+0.0904131%`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`

이번 Tove slice 뒤에도 certified count가 `2`라 ranking probe는 재실행하지 않았다.

optimizer production integration은 아직 하지 않는다.

---

## 2. 최신 완료 — percent-ammo instant named event

토브 `급조 탄환 -> 임시 개조 2`에서 작은 generic gap을 닫았다.

실제 shape:

- provider `급조 탄환`: `instant / ammo_charge_pct`, self, reducible `hit_count:10`
- consumer `임시 개조 2`: `buff / crit_dmg +5.24`, all allies, 5s, `event:급조 탄환`

Moris의 `handle_ammo_charge_pct`는 refill 성공 뒤 `event:{effect.name}`을 같은 caster로 notify한다. 반면 `ammo_charge_flat` handler에는 이 notify가 없다.

따라서 Fast도 정확히 다음만 지원한다.

- 성공한 `ammo_charge_pct` instant의 named-event emission
- same-actor, executable, non-negative pct provider를 named-event source로 runtime/score에서 증명
- consumer는 direct-damage-runtime-supported buff로 제한

`ammo_charge_flat` named provider는 계속 fail closed다. flat까지 넓히면 Moris 의미론과 달라진다.

production:

- `47e8c47278bbd9125b42a8f08bde632638796026`

permanent regression:

- `fast_engine/tests/test_ammo_pct_named_event.py`
- `fast_engine/tests/test_named_buff_event_runtime.py` Tove expectation 갱신

runner-only A/B:

- run `33912561440`
- job `101152127477`
- focused `16/16`
- full Fast `248/248`

post-promotion validation:

- HEAD `d21c68517f83dee638d8ca566291534e1c23712f`
- run `33912764211`
- job `101152802424`
- focused `16/16`
- full Fast `248/248`
- public `23 unique / 2 certified / 21 gaps`

제거된 public blockers (`레이드_소다`, `스쿼드3`):

- `normal_delivery:토브:임시 개조 2:crit_dmg`
- `skill_state_delivery:토브:임시 개조 2:crit_dmg`

다음 Tove cadence blockers는 의도적으로 남아 있다.

- `cadence:토브:급조 탄환:ammo_charge_pct`
- `cadence:토브:임시 개조:max_ammo_flat`
- `cadence:토브:개조 성공 2:attack_speed_pct`

즉 named-event delivery와 provider cadence certification을 섞지 않았다.

상세:

- `fast_engine/research/TOVE_AMMO_PCT_NAMED_EVENT_CHECKPOINT_20260905.md`

---

## 3. 미하라 control 진단 — no patch

`컨트롤_미란다미하라`와 `레이드_미하라에이다`의 `미하라 : 본딩 체인` weapon/control 자체는 동일하다.

team-dependent safety 차이는 D : 킬러 와이프 `타겟 섬멸 ATK`에서 나온다.

- stat: `atk_caster_based_pct`
- value: `12.19`
- duration: `10s`
- target: `self`
- condition: `target_state:타겟 섬멸`
- trigger: `body_hit_count:1` -> `squad_body_hit`

Moris `notify_team_hit()`은 스쿼드 어느 아군이 본체를 명중해도 consumer를 확인하고, activation caster를 실제 attacker로 넘긴다. 따라서 target `self`는 D가 아니라 그 공격자를 뜻한다.

기본 `enemy.has_parts=False`에서는 비코어 본체 명중마다 이 chronology가 발생한다.

결론:

- 미하라 control blocker를 단순 완화하면 오답이다.
- executable global `squad_body_hit` consumer는 기존 rapid score fail-closed를 유지한다.
- `레이드_미하라에이다`의 `control:미하라 : 본딩 체인`은 정상적인 coverage gap이다.

---

## 4. 직전 완료 — Ada charge ownership

Ada 이름 특례 없이 pure charge `own_full_burst` hold를 좁게 generic certification했다.

production:

- `73145b1862ce474bd78a5674916cfd7ec6a05f1e`

지원 shape:

- charge weapon
- non-clip
- control의 유일한 key가 `hold`
- `hold.policy == own_full_burst`
- optional non-negative `lead`

mixed control은 계속 fail closed다.

Ada 두 public team에서 Ada 자체 blocker는 모두 제거됐지만 다른 blocker 때문에 certified count는 증가하지 않았다.

상세:

- `fast_engine/research/ADA_CHARGE_HOLD_CONTROL_CHECKPOINT_20260905.md`

---

## 5. 기타 최근 완료

### Ada one-shot charge-speed lifetime

- production `f70871e36ddf28a2474e7e25d6d7254cf9fe26cd`
- self `charge_speed_pct`
- exactly `burst_cast`
- `duration_bullets:1`
- existing physical-shot / post-shot bullet-consume runtime 재사용

### patternless encounter events

- production `4c78a27f024074a9e19391efc3d4ed6125c2d667`
- static patternless enemy에서 unreachable인 `enemy_death`, `event:part_destroy`만 score blocker에서 제외
- runtime을 broad-enable하지 않음
- Crown external heal 등 다른 named events는 fail closed 유지

---

## 6. 현재 frontier / 계속 보류하는 축

가까운 public gap을 blocker 수만 보고 broad-enable하지 않는다.

특히 다음은 이미 보류 근거가 있다.

- Little Mermaid `거품 난사` — team-global `squad_ammo_consume:500`; Fast/Moris crossing chronology mismatch
- Crown `로얄 에타이어 4` — arbitrary/external `heal_received`
- Mokdan `정정당당 승부다!` — broad weapon change
- Nayuta `기억 연소` — cross-class `SMG -> RL`
- unsafe recipient를 무시한 reload/max-ammo
- HP-derived state 상수화
- generic `bonus_damage` family
- executable global `squad_body_hit`
- arbitrary multi-bullet cadence lifetime
- mixed charge controls

현재 closest public membership `레이드_델타`는 Little Mermaid `거품 난사` 하나만 남았지만 위 이유로 억지 certification하지 않는다.

---

## 7. 다음 단일 checkpoint

다음 작업은 **남은 repeated delivery/cadence blocker를 다시 shape 단위로 분류해 작은 generic slice를 선정하는 것**이다.

이미 no-patch/hold가 확정된 축은 후보에서 제외한다.

- Mihara / `squad_body_hit`
- Little Mermaid / `squad_ammo_consume`
- Crown external heal
- broad/cross-class weapon change

진행 순서:

1. 현재 unique-23 blocker frontier 재스캔
2. 반복 effect를 stat 이름이 아니라 trigger / target / condition / recipient-safety shape로 묶기
3. 기존 runtime이 이미 대부분 소유하고 있고 새로운 HP/global-shot chronology가 필요 없는 후보 우선
4. real Moris semantic probe
5. runner-only A/B
6. focused regression
7. public blocker delta
8. certified count가 실제 증가할 때만 ranking validation 재실행

목표는 blocker 숫자를 줄이는 것이 아니라 comparison-critical 의미론을 증명할 수 있는 작은 generic ownership을 계속 늘리는 것이다.

---

## 8. 고정 원칙

- Fast는 broad scorer이지 Moris 2.0이 아니다.
- comparison-critical unsupported는 fail closed.
- character-name hack 금지.
- fitted coefficient 금지.
- global 1/60 combat loop 금지.
- state-relevant하지 않은 global per-shot/per-pellet scheduling 금지.
- Fast parity를 위해 Moris `calculator/` semantics를 변경하지 않는다.
- static enemy scope 유지.
- engine은 candidate generation을 결정하지 않는다.
- unsupported coverage를 numeric score로 위장하지 않는다.

---

## 9. CI / cleanup 계약

Tove production commit은 이미 runner-only A/B와 post-promotion validation에서 검증됐다.

최종 handoff/checkpoint 정리 commit에서는 이번 조사에 사용한 temporary workflow와 Tove patch helper를 제거하고 canonical `ci.yml`을 다시 트리거한다.

최종 `.github/workflows`에는 다음만 남겨야 한다.

- `ci.yml`
- `pages.yml`

최종 canonical CI에서 새 permanent regression이 실제 discovery되는지 확인한다.

`master`는 그대로 둔다.
