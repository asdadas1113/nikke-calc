# Nayuta `기억 연소` rapid→charge skill weapon-change checkpoint — 2026-09-07

## Status

**COMPLETED / production 승격 완료.**

Production semantic commit:

- `38244aeda6313f7c978af9658dc9f2eae1aa6dc0` — `Fast: support rapid-to-charge skill weapon changes`

`master`와 `calculator/`는 수정하지 않았다. Moris는 의미론 oracle로만 사용했다.

## 1. Public surface

`weapon_change:나유타:기억 연소`가 있던 public source case는 정확히 3개다.

- `스쿼드2`
- `레이드_네온벨벳`
- `레이드_소다`

`레이드_네온벨벳`은 현재 public policy에서 Nayuta B2를 실제 사용하지 않지만 roster-specific unreachable shortcut은 추가하지 않았다. 세 roster 모두 동일한 generic ownership proof로 처리한다.

## 2. Owned compiled shape

이번 checkpoint가 여는 범위는 다음 exact graph다.

- self-target finite `burst_cast` weapon change
- base: non-clip `SMG / auto`
- changed: `RL / charge`
- duration `10s`
- changed max ammo `-1` (infinite)
- damage coefficient `275.18%`
- charge time `1.8s`
- full-charge multiplier `250%`
- changed RL post-fire delay `0.215s`
- `skill_damage=True`
- same-actor `full_charge_hit` consumers exactly two:
  - `위선 5`: direct damage `150%`
  - `위선 6`: bonus damage `380.46%`

Score ownership diagnostic에서 처음 staged proof가 public 3 roster를 모두 거절한 원인은 consumer target representation을 잘못 가정했기 때문이다. 두 damage consumer의 실제 compiled `target_spec.mode.value`는 모두 `enemy`였다. proof는 이 실제 representation에 맞춰 좁게 수정했고 다른 shape를 넓히지 않았다.

계속 fail-closed인 neighboring shape:

- `skill_damage=False`
- finite changed magazine
- clip/control/cover-during-delay base actor
- external recipient
- extra weapon-change parameter
- widened state/consumer graph
- unrelated rapid→charge family

## 3. Moris oracle와 sparse timing

첫 session에서 Moris 실측은 다음과 같다.

- mode enter: `3.20`
- changed-mode full-charge shots:
  - `5.016667`
  - `7.05`
  - `9.066667`
  - `11.083333`
  - `13.10`
- mode expire/base resume: `13.20`

만료 시 unfinished charge는 취소된다. base rapid magazine은 mode 진입 전 탄수를 복원하지 않고 **만료 시점 live full magazine**으로 재개한다.

`스쿼드2` isolated harness에서 Privaty `EX 매거진 3`의 max-ammo 효과만 재현해 unrelated static last-bullet guard를 열지 않고 검증했다.

- expiry live full: `215`
- base SMG resume shot: `13.20`
- 그 shot 뒤 ammo: `214`

초기 Fast staged runtime은 `13.20` 뒤 nominal `13.241667`에도 한 발을 더 발사해 13.25 half-open horizon에서 ammo `213`이 되는 divergence가 있었다.

Moris는 outer 60Hz observation 때문에 nominal `13.241667` deadline을 다음 frame `13.25`에서 관측한다. horizon `[0, 13.25)`에서는 이 두 번째 shot이 발생하지 않는다.

해결은 global 60Hz loop가 아니다. 기존 sparse `_moris_frame_observed` path를 cross-mode 종료 후 base rapid actor에도 generic하게 이어 주었다. `resume_with_live_full_magazine()`가 해당 actor를 frame-observed rapid cadence로 재-anchor하고 기존 sparse deadline quantization을 재사용한다.

결과:

- last base shot before horizon: `13.20`
- next phase end / observed deadline: `13.25`
- ammo at 13.25 boundary: `214`

캐릭터명 기반 runtime branch는 없다.

## 4. Damage classification

`기억 연소` changed-mode shot은 ordinary normal attack이 아니라 weapon-mode skill damage다.

Fast는 다음을 보존한다.

- `is_normal_atk=False`
- `is_weapon_mode_skill=True`
- full-charge layer 적용
- weapon-mode skill core semantics 적용
- ordinary normal-attack damage bonus 미적용
- `duration_bullets` 미소비
- post-shot `full_charge_hit` 발생 후 `위선 5/6` same-timestamp 파생
- changed weapon이 RL이라는 이유만으로 projectile-explosion bonus를 부여하지 않음

## 5. Privaty safety boundary

처음 public full-runtime timing harness는 `스쿼드2`의 기존 Privaty `EX 매거진 2/3` static last-bullet fail-closed guard에서 먼저 중단했다.

이번 checkpoint에서는 Privaty를 열지 않았다. Nayuta timing은 lower-level isolated runtime harness로 검증했고, Privaty `EX 매거진 2/3` public certification은 여전히 별도 checkpoint다.

또한 기존 `test_live_periodic_accuracy_still_invalidates_static_core_count_plan`은 새 Nayuta dynamic weapon guard가 먼저 발동해 원래 `기억 흡수` safety property를 가렸다. assertion regex를 바꾸지 않고 synthetic fixture에서 `기억 연소` effect slot/effect_id를 보존한 채 inert effect로 바꿔 원래 `기억 흡수` fail-closed를 직접 검증하도록 격리했다.

## 6. Validation

Promotion workflow run:

- run `34104960960`
- job `101687759145`
- result: `success`

Focused:

- Nayuta: `6/6`
- neighboring regressions: `29/29`
- periodic named-stack isolation: `4/4`

Complete Fast discovery:

- `356/356`
- runtime `64.006s`
- performance sample: median `200.58ms`, events `539`

Public frontier after patch:

- source cases: `24`
- certified source cases: `6`
- source-case gaps: `18`
- blocker families:
  - cadence `56`
  - control `5`
  - normal_delivery `47`
  - normal_state `18`
  - periodic_grid `1`
  - skill_damage `25`
  - skill_state_delivery `49`
  - weapon_change `4`

A/B에서 바뀐 family는 `weapon_change`뿐이며 `7 → 4`다. 제거된 blocker는 정확히 세 public source case의 `weapon_change:나유타:기억 연소`뿐이다. certified count가 6으로 유지되는 것은 세 roster에 다른 blocker가 남아 있기 때문이다.

이 scanner는 source case 기준이라 `24 / 6 / 18`을 보고한다. 기존 handoff의 `23 unique memberships / 17 gaps` 표기는 membership de-duplication 관점이므로 서로 다른 집계 기준이다.

## 7. Production diff scope

Semantic commit의 변경은 `fast_engine/` 안의 다음 8개 파일뿐이다.

- `fast_engine/engine/burst_runtime.py`
- `fast_engine/engine/dispatcher.py`
- `fast_engine/engine/dynamic_rapid.py`
- `fast_engine/engine/dynamic_weapon.py`
- `fast_engine/engine/score.py`
- `fast_engine/engine/weapon.py`
- `fast_engine/tests/test_damage_nayuta_cross_mode_weapon_change.py`
- `fast_engine/tests/test_periodic_named_stack_delivery.py`

`calculator/` diff는 없다.

## 8. Checkpoint hygiene

완료 후 다음 temporary assets를 제거했다.

- `.github/workflows/tmp-nayuta-diagnostic.yml`
- `.github/tmp_nayuta_apply.py`
- `.github/tmp_nayuta_probe.py`
- `.github/tmp_nayuta_integrate.py`
- `.github/tmp_nayuta_regression_fix.py`

최종 workflow hygiene는 `ci.yml`, `pages.yml`만 남는 상태로 확인한다.

## 9. Phase

Phase는 계속 **false-supported safety closure → semantics restoration**이다.

이번 checkpoint는 generic rapid→charge skill weapon-change의 정확히 증명된 slice만 복원했다. raw coverage expansion이나 optimizer integration으로 phase를 바꾸지 않는다. 다음 semantic checkpoint는 clean final CI와 frontier 상태를 확인한 뒤 별도로 선택한다.
