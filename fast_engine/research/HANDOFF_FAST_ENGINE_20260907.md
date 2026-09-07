# Fast Engine 작업 인계 — 2026-09-07

## 0. 재개 원칙

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다. `calculator/`는 Moris 의미론 oracle로만 사용한다.**

Fast Engine은 Moris 복제품이 아니라 optimizer용 고속 sparse-event ranking engine이다.

금지 원칙:

- global 60Hz loop 추가 금지
- 캐릭터명 기반 runtime 분기 금지
- unsupported comparison-critical mechanic silent zero 금지
- 한 번에 하나의 semantic checkpoint만 완결
- false-supported safety closure보다 coverage 숫자를 우선하지 않음

작업 시작 시 branch HEAD와 `master`를 다시 조회한다. 이 문서의 SHA는 semantic 기준점을 기록하는 것이며 현재 HEAD 자체를 뜻하지 않을 수 있다.

먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260907.md`
2. `fast_engine/research/NAYUTA_RAPID_TO_CHARGE_SKILL_WEAPON_CHANGE_WIP_CHECKPOINT_20260907.md`
3. `fast_engine/research/PRIVATY_CHARGE_LIVE_MAX_AMMO_SAFETY_CHECKPOINT_20260907.md`
4. `fast_engine/research/MORAN_RAPID_WEAPON_CHANGE_LIFECYCLE_CHECKPOINT_20260907.md`
5. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`

## 1. Latest completed semantic checkpoint

최신 production semantic commit:

- `38244aeda6313f7c978af9658dc9f2eae1aa6dc0` — `Fast: support rapid-to-charge skill weapon changes`

완료 checkpoint:

- Nayuta `기억 연소` rapid→charge skill weapon-change lifecycle

상세 기록:

- `fast_engine/research/NAYUTA_RAPID_TO_CHARGE_SKILL_WEAPON_CHANGE_WIP_CHECKPOINT_20260907.md`
  - 파일명에는 역사적으로 `WIP`가 남아 있지만 문서 status는 **COMPLETED**다.

`master` 기준 SHA:

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

이 SHA가 계속 불변이어야 한다.

## 2. Nayuta에서 복원한 exact semantics

Public source cases:

- `스쿼드2`
- `레이드_네온벨벳`
- `레이드_소다`

Owned exact shape:

- base `SMG / auto`, non-clip
- self finite `burst_cast` weapon change
- changed `RL / charge`
- duration `10s`
- infinite changed magazine
- damage coeff `275.18%`
- charge time `1.8s`
- full-charge mult `250%`
- post-fire delay `0.215s`
- `skill_damage=True`
- same actor `full_charge_hit` damage consumers exactly two:
  - `위선 5` `150%`
  - `위선 6` `380.46%`

중요 proof correction:

- 두 consumer의 실제 compiled `target_spec.mode.value`는 `enemy`
- 초기 staged proof의 `all_enemies` / `same_target` 가정이 over-reject 원인이었음
- 실제 compiled representation만 인정하도록 좁게 수정함

Neighboring widened shape는 계속 fail-closed다.

## 3. Moris timing과 sparse frame observation

첫 session Moris oracle:

- mode enter `3.20`
- changed shots:
  - `5.016667`
  - `7.05`
  - `9.066667`
  - `11.083333`
  - `13.10`
- expire/base resume `13.20`

만료 시 unfinished charge는 취소되고 base rapid는 **종료 시점 live full magazine**으로 재개한다.

`스쿼드2` isolated harness:

- live full at expiry `215`
- resume shot `13.20`
- ammo after resume shot `214`

발견했던 real Fast divergence:

- 초기 staged Fast는 nominal `13.241667`에도 두 번째 SMG shot을 발사해 13.25 boundary 전에 ammo `213`이 됨
- Moris는 해당 nominal deadline을 다음 60Hz frame `13.25`에서 관측
- half-open horizon `[0, 13.25)`에서는 두 번째 shot이 없음

수정:

- global frame loop를 추가하지 않음
- 기존 sparse `_moris_frame_observed` deadline path를 cross-mode 종료 후 base rapid resume에도 generic하게 이어 줌
- `resume_with_live_full_magazine()`가 actor를 frame-observed cadence로 re-anchor

결과:

- `13.20` 한 발만 발생
- next observed phase end `13.25`
- ammo `214`

## 4. Damage classification

Changed-mode shot은 ordinary normal attack이 아니라 weapon-mode skill damage다.

보존된 의미론:

- `is_normal_atk=False`
- `is_weapon_mode_skill=True`
- full-charge layer 사용
- weapon-mode skill core semantics 사용
- normal attack bonus 미적용
- `duration_bullets` 미소비
- `full_charge_hit` 후 `위선 5/6` same-timestamp 파생
- changed RL이라는 이유만으로 projectile explosion bonus를 붙이지 않음

## 5. Privaty와 기존 safety guard

Nayuta public timing을 full `스쿼드2` runtime으로 검증하려 하면 기존 Privaty `EX 매거진 2/3` static last-bullet guard가 먼저 fail-closed한다.

이번 checkpoint에서는 Privaty를 열지 않았다.

- Privaty `EX 매거진 2/3` public certification은 여전히 별도 문제
- Nayuta timing은 isolated lower-level runtime harness로 검증

기존 periodic/core-count safety test도 약화하지 않았다.

- 새 dynamic weapon guard가 원래 `기억 흡수` guard를 가리던 synthetic fixture만 격리
- effect slot/effect_id를 유지한 inert `기억 연소`로 바꿔 원래 `기억 흡수` fail-closed를 직접 검증

## 6. Promotion validation

Semantic promotion workflow:

- run `34104960960`
- job `101687759145`
- result `success`

Gate results:

- periodic named-stack isolation `4/4`
- Nayuta focused `6/6`
- neighboring regressions `29/29`
- complete Fast discovery `356/356`
- performance sample median `200.58ms`, events `539`

Semantic diff는 `fast_engine/`의 8개 파일뿐이다.

- engine 6개
- 신규 Nayuta regression 1개
- 기존 periodic named-stack regression 1개

`calculator/` diff 없음.

## 7. Current public frontier

표준 `fast_engine/research/public_blocker_frontier.py` 기준:

- source cases `24`
- certified source cases `6`
- source-case gaps `18`

blocker family counts:

- cadence `56`
- control `5`
- normal_delivery `47`
- normal_state `18`
- periodic_grid `1`
- skill_damage `25`
- skill_state_delivery `49`
- weapon_change `4`

Nayuta A/B에서 바뀐 family는 `weapon_change`뿐이다.

- before `7`
- after `4`

없어진 blocker는 정확히 다음 세 source case의 `weapon_change:나유타:기억 연소`다.

- `스쿼드2`
- `레이드_네온벨벳`
- `레이드_소다`

certified count가 증가하지 않은 것은 세 roster에 다른 blockers가 남아 있기 때문이다.

집계 주의:

- scanner raw view: `24 source / 6 certified / 18 gaps`
- 이전 handoff의 `23 unique memberships / 17 gaps`는 membership de-duplication view
- 두 수치는 집계 단위가 다르다.

## 8. Cleanup state

Nayuta checkpoint 완료 후 다음 temporary assets는 제거했다.

- `.github/workflows/tmp-nayuta-diagnostic.yml`
- `.github/tmp_nayuta_apply.py`
- `.github/tmp_nayuta_probe.py`
- `.github/tmp_nayuta_integrate.py`
- `.github/tmp_nayuta_regression_fix.py`

최종 `.github/workflows`에는 다음 두 개만 남아야 한다.

- `ci.yml`
- `pages.yml`

재개 시 이 hygiene를 다시 확인한다.

## 9. Current phase

계속 **false-supported safety closure → semantics restoration** 단계다.

현재까지 주요 restoration 축:

- finite self rapid weapon-change lifecycle
- sparse Moris rapid nominal-fire deadline observation
- rapid effective weapon view isolation
- Little Mermaid enemy replacement + global squad ammo crossing
- Crown shared lifetime/heal_received
- charge live max-ammo source quantization/clamp safety repair
- exact self rapid→charge skill weapon-change lifecycle

Nayuta checkpoint는 닫혔다. 다음 작업은 clean final canonical CI와 current frontier를 확인한 뒤 **다음 단일 semantic checkpoint를 선택**하는 것이다. raw coverage expansion이나 optimizer integration으로 바로 넘어가지 않는다.

## 10. 다음 작업자가 할 순서

1. branch HEAD 조회
2. `master`가 `fb2fd9157aa14499daf6b9f185beb685d4393f90`인지 확인
3. 이 handoff와 completed Nayuta checkpoint 읽기
4. `.github/workflows`가 `ci.yml`, `pages.yml`뿐인지 확인
5. 최신 canonical CI가 green인지 확인
6. current public frontier를 필요 시 재실행
7. 남은 blockers 중 false-supported risk와 semantic leverage를 기준으로 다음 **하나의** checkpoint 선택
8. Moris oracle로 의미론을 먼저 고정
9. narrow ownership proof + focused regression
10. full Fast discovery + frontier A/B + canonical CI 후에만 완료 처리

## 11. 절대 하지 말 것

- `master` 수정/병합
- `calculator/` production 수정
- global 60Hz loop
- 캐릭터명 기반 runtime special-case
- unsupported mechanic silent zero
- 테스트 편의를 위한 unrelated blocker 개방
- Moris 불일치를 tolerance 확대로 숨기기
- proof 없이 family 전체를 열기
- 한 checkpoint가 닫히기 전에 다음 coverage slice를 섞기
