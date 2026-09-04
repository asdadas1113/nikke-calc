# Fast Engine 작업 인계 — 2026-09-05

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`
2. `fast_engine/research/ADA_CHARGE_HOLD_CONTROL_CHECKPOINT_20260905.md`
3. `fast_engine/research/ADA_ONE_SHOT_CHARGE_SPEED_CHECKPOINT_20260905.md`
4. `fast_engine/research/PATTERNLESS_ENCOUNTER_EVENT_CHECKPOINT_20260905.md`
5. `fast_engine/research/COVERAGE_FRONTIER_CHECKPOINT_20260904.md`
6. `fast_engine/research/CROWN_SELF_STACK_HEAL_CHECKPOINT_20260904.md`
7. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`

현재 최신 production semantic commit:

- `73145b1862ce474bd78a5674916cfd7ec6a05f1e` — `fast: certify own-full-burst charge hold`

직전 주요 commits:

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

latest standardized public ranking:

- clean relative error median: `+0.0626832%`
- min: `+0.0349533%`
- max: `+0.0904131%`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`

optimizer production integration은 아직 하지 않는다.

---

## 2. 최신 완료 — pure charge `own_full_burst` hold ownership

Ada 이름을 특별취급하지 않고 다음 control shape를 좁게 generic certification 했다.

- charge weapon
- non-clip
- `control`의 유일한 key가 `hold`
- `hold.policy == own_full_burst`
- optional non-negative `lead`
- mixed `tap_fire` / cover / reload / explicit sequence는 계속 fail closed

production:

- `73145b1862ce474bd78a5674916cfd7ec6a05f1e`

Fast는 global 1/60 loop를 추가하지 않았다. full charge에 도달하면 shot을 즉시 발사하는 대신 sparse latch 상태로 두고, 해당 actor가 그 burst cycle에 cast했을 때 확정된 `full_burst_end - lead` release boundary로만 이동한다.

중요 semantics:

- full charge 완료 전에는 기존 dynamic charge cadence 그대로다.
- full charge 완료 후 hold 중에는 `charge_latched=True`다.
- hold 중 charge-speed 상태가 바뀌어도 이미 완성된 charge의 release 시각을 다시 계산하지 않는다.
- nominal release 2.500s는 Moris outer-tick 의미에 따라 observed boundary 약 2.516667s에서 발사된다.
- actor가 해당 cycle에 burst cast하지 않았으면 hold가 걸리지 않는다.

Ada 실제 RL은 `cover_during_delay=True`지만 두 public Ada team에서 positive reload-speed upper bound가 `29.69%`라 Moris의 >=100% 특수 branch가 도달 불가능하다. 따라서 `cover_during_delay` 자체를 helper에서 blanket reject하지 않고 기존 `_charge_actor_score_safe()`가 reachability를 판단하게 했다.

이 ownership이 열리면서 이미 존재하던 direct-damage `duration_bullets:1` runtime support가 Ada `특수 개조 2`에도 그대로 적용됐다. 별도의 Ada direct-damage 특례는 추가하지 않았다.

permanent regression:

- `fast_engine/tests/test_damage_charge_hold_control.py`
- `fast_engine/tests/test_damage_charge_speed_bullet_lifetime.py`의 public Ada frontier expectation 갱신

runner-only production gate:

- focused: `27 tests` 통과
- full Fast: `56 modules / 245 tests` 통과
- standardized public ranking 통과

public family delta:

- cadence: `66` 유지
- skill_state_delivery: `50 -> 48`
- normal_delivery: `49 -> 47`
- skill_damage: `27` 유지
- weapon_change: `12` 유지
- control: `8 -> 6`
- normal_state: `7` 유지

두 non-`지그_*` Ada public team에서 Ada 이름이 들어간 blocker는 모두 사라졌다.

제거:

- `control:에이다`
- `normal_delivery:에이다:특수 개조 2:charge_dmg_pct`
- `skill_state_delivery:에이다:특수 개조 2:charge_dmg_pct`
- `cadence:에이다:특수 개조:charge_speed_pct`는 직전 checkpoint에서 이미 제거됨

다만 두 team 모두 다른 캐릭터 blocker가 남아 있어 certified count는 `2` 그대로다.

상세 근거:

- `fast_engine/research/ADA_CHARGE_HOLD_CONTROL_CHECKPOINT_20260905.md`

---

## 3. 직전 완료 — Ada one-shot charge-speed lifetime

Ada `특수 개조`의 다음 shape를 좁게 generic certification 했다.

- self `charge_speed_pct`
- trigger exactly `burst_cast`
- `duration_bullets:1`
- one stack
- no conditions
- capability blocker exactly `field:duration_bullets`

production:

- `f70871e36ddf28a2474e7e25d6d7254cf9fe26cd`

Fast는 기존 dynamic charge runtime의 physical-shot 경계를 재사용한다. consuming charge shot은 상태를 적용한 cadence로 처리되고, shot score/hit 계열 뒤 post-shot bullet consume에서 상태가 제거된다.

상세 근거:

- `fast_engine/research/ADA_ONE_SHOT_CHARGE_SPEED_CHECKPOINT_20260905.md`

---

## 4. 직전 완료 — patternless encounter events

표준 static enemy에서 발생하지 않는 다음 encounter event는 score blocker에서만 unreachable로 취급한다.

- `enemy_death`
- `event:part_destroy`

production:

- `4c78a27f024074a9e19391efc3d4ed6125c2d667`

제거된 blocker는 Volume 2개, Raven 1개뿐이며 runtime dispatcher를 broad-enable하지 않았다. Crown external `heal_received` 등 named-event blocker는 계속 fail closed다.

---

## 5. 최신 blocker frontier

post-charge-hold unique-23 family counts:

- `cadence`: `66`
- `skill_state_delivery`: `48`
- `normal_delivery`: `47`
- `skill_damage`: `27`
- `weapon_change`: `12`
- `normal_state`: `7`
- `control`: `6`

unsupported families: `0`

반복도가 높은 큰 축은 여전히 다음과 같다.

- Little Mermaid `거품 난사` — team-global `squad_ammo_consume:500`; chronology mismatch 때문에 보류
- Mokdan `정정당당 승부다!` — weapon change
- Crown `로얄 에타이어 4` — external heal 가능 팀은 계속 blocked
- Privaty reload/max-ammo — recipient safety 문제와 결합
- Nayuta `기억 연소` — cross-class `SMG -> RL`

Ada 자체는 두 public team에서 blocker frontier를 더 이상 차지하지 않는다.

---

## 6. 계속 보류하는 축

근거 없이 broad-enable하지 않는다.

- arbitrary/external `heal_received` chronology
- Little Mermaid team-global `squad_ammo_consume`
- cross-class / broad weapon change
- HP-derived state 상수화
- unsafe recipient를 무시한 reload/max-ammo
- generic `bonus_damage` family
- arbitrary multi-bullet cadence lifetime
- mixed charge controls를 pure hold support로 간주하는 것

---

## 7. 다음 단일 checkpoint

다음은 production patch를 전제하지 않는 **`미하라 : 본딩 체인` control safety diagnosis**다.

이유:

- `컨트롤_미란다미하라`는 현재 certified membership인데,
- `레이드_미하라에이다`에서는 같은 캐릭터가 `control:미하라 : 본딩 체인` blocker를 만든다.

따라서 character control 자체가 아니라 team-dependent score-safety invalidator일 가능성이 있다. 다음 checkpoint에서는 그 차이를 정확히 분리한다.

진행 순서:

1. 두 membership의 compiled `미하라 : 본딩 체인` weapon/control shape가 실제로 같은지 확인
2. `_rapid_actor_score_safe()` / 관련 dynamic owner gate에서 어느 조건이 team별로 달라지는지 항목별 진단
3. 미하라를 target할 수 있는 cadence/state effects와 executable weapon events를 비교
4. certified team에서만 안전한 이유가 이미 generic proof로 표현돼 있는지 확인
5. 좁은 generic relaxation이 증명되면 runner-only A/B, 아니면 no-patch로 종료

목표는 blocker 숫자를 억지로 줄이는 것이 아니라 **동일 control의 team-dependent certification 원인**을 확정하는 것이다.

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

`73145b1`은 temporary promotion workflow의 `GITHUB_TOKEN` push로 만들어져 해당 SHA 자체의 branch-push canonical CI가 자동 생성되지 않는다.

따라서 이 handoff/checkpoint 갱신과 모든 temporary workflow 제거를 같은 follow-up commit으로 묶어 canonical `ci.yml`을 트리거한다. 이 follow-up commit은 production engine/test tree를 그대로 포함하므로 canonical CI가 새 permanent regression을 실제 discovery하는 최종 gate다.

최종 cleanup 후 `.github/workflows`에는 다음만 남겨야 한다.

- `ci.yml`
- `pages.yml`

`master`는 그대로 둔다.
