# Fast Engine 작업 인계 — 2026-09-05

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`
2. `fast_engine/research/ADA_ONE_SHOT_CHARGE_SPEED_CHECKPOINT_20260905.md`
3. `fast_engine/research/PATTERNLESS_ENCOUNTER_EVENT_CHECKPOINT_20260905.md`
4. `fast_engine/research/COVERAGE_FRONTIER_CHECKPOINT_20260904.md`
5. `fast_engine/research/CROWN_SELF_STACK_HEAL_CHECKPOINT_20260904.md`
6. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`

현재 최신 production semantic commit:

- `f70871e36ddf28a2474e7e25d6d7254cf9fe26cd` — `fast: certify one-shot charge-speed lifetime`

직전 주요 commits:

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

## 2. 최신 완료 — Ada one-shot charge-speed lifetime

Ada `특수 개조`의 다음 shape를 좁게 generic certification 했다.

- self `charge_speed_pct`
- trigger exactly `burst_cast`
- `duration_bullets:1`
- one stack
- no conditions
- capability blocker exactly `field:duration_bullets`

production:

- `f70871e36ddf28a2474e7e25d6d7254cf9fe26cd`

Fast는 기존 dynamic charge runtime의 physical-shot 경계를 재사용한다. 새 전역 per-shot loop는 없다. consuming charge shot은 상태를 적용한 cadence로 처리되고, shot score/hit 계열 뒤 post-shot bullet consume에서 상태가 제거된다.

outer-tick regression:

- synthetic base charge 1.0s + `charge_speed_pct=-300`
- 4.0s에는 state 유지
- 다음 observed shot 이후 4.05s에는 state 제거

production fail-closed:

- weapon-bound trigger
- `duration_bullets:1.5`
- `duration_bullets:2`
- non-self target

검증:

- focused: `19 tests` 통과
- full Fast: `55 modules / 240 tests` 통과
- standardized public ranking 통과

blocker 변화:

- cadence `68 -> 66`
- 나머지 family count 불변

두 non-`지그_*` Ada public team에서 정확히 `cadence:에이다:특수 개조:charge_speed_pct`만 제거됐다.

`레이드_미하라에이다` / `레이드_헬름아쿠아스노우`에는 여전히 다음이 남는다.

- `control:에이다`
- `normal_delivery:에이다:특수 개조 2:charge_dmg_pct`
- `skill_state_delivery:에이다:특수 개조 2:charge_dmg_pct`

따라서 certified count는 2 그대로다.

상세 근거:

- `fast_engine/research/ADA_ONE_SHOT_CHARGE_SPEED_CHECKPOINT_20260905.md`

---

## 3. 직전 완료 — patternless encounter events

표준 static enemy에서 발생하지 않는 다음 encounter event는 score blocker에서만 unreachable로 취급한다.

- `enemy_death`
- `event:part_destroy`

production:

- `4c78a27f024074a9e19391efc3d4ed6125c2d667`

제거된 blocker는 Volume 2개, Raven 1개뿐이며 runtime dispatcher를 broad-enable하지 않았다. Crown external `heal_received` 등 named-event blocker는 계속 fail closed다.

---

## 4. 최신 blocker frontier

post-Ada unique-23 family counts:

- `cadence`: `66`
- `skill_state_delivery`: `50`
- `normal_delivery`: `49`
- `skill_damage`: `27`
- `weapon_change`: `12`
- `control`: `8`
- `normal_state`: `7`

unsupported families: `0`

반복도가 높은 큰 축은 여전히 다음과 같다.

- Little Mermaid `거품 난사` — team-global `squad_ammo_consume:500`; chronology mismatch 때문에 보류
- Mokdan `정정당당 승부다!` — weapon change
- Crown `로얄 에타이어 4` — external heal 가능 팀은 계속 blocked
- Privaty reload/max-ammo — recipient safety 문제와 결합
- Nayuta `기억 연소` — cross-class `SMG -> RL`

---

## 5. 계속 보류하는 축

근거 없이 broad-enable하지 않는다.

- arbitrary/external `heal_received` chronology
- Little Mermaid team-global `squad_ammo_consume`
- cross-class / broad weapon change
- HP-derived state 상수화
- unsafe recipient를 무시한 reload/max-ammo
- generic `bonus_damage` family
- arbitrary multi-bullet cadence lifetime

---

## 6. 다음 단일 checkpoint

다음 우선 후보는 **Ada `특수 개조 2` one-shot direct-damage lifetime**이다.

actual public shape:

- self `charge_dmg_pct=+1500`
- `burst_cast`
- `duration_bullets:1`

진행 순서:

1. actual compiled effect와 capability blocker 재확인
2. 기존 Helm charge direct-damage bullet-lifetime support와 비교
3. Moris에서 burst 후 consuming physical charge shot의 damage term 적용/제거 순서 실측
4. Fast score delivery가 동일 shot에서 적용 후 post-shot consume 되는지 확인
5. runner-only narrow generic A/B
6. positive + fail-closed regression
7. full Fast regression + standardized public ranking

Ada `control`은 별도 blocker이므로 이 slice만으로 certified count 증가를 목표로 하지 않는다.

---

## 7. 고정 원칙

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

## 8. CI / cleanup 계약

`f70871e`는 temporary production workflow의 `GITHUB_TOKEN` push로 만들어져 해당 SHA 자체의 branch-push canonical CI가 자동 생성되지 않았다.

따라서 이 handoff/checkpoint 갱신과 temporary workflow 제거를 같은 follow-up commit으로 묶어 canonical `ci.yml`을 트리거한다. 이 follow-up commit은 production engine/test tree를 그대로 포함하므로 canonical CI가 새 permanent regression을 실제 discovery하는 최종 gate다.

최종 cleanup 후 `.github/workflows`에는 다음만 남겨야 한다.

- `ci.yml`
- `pages.yml`

`master`는 그대로 둔다.
