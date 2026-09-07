# Rapid → Single-Charge Weapon Change Checkpoint — 2026-09-07

Status: **COMPLETED**

Semantic commit:

- `b492c4d0c3d45cfe3eea5ca9b80cbd755340e13a` — `Fast: support rapid-to-single-charge weapon changes`

Protected `master` baseline:

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

`calculator/` was not modified. Moris was used only as the semantic oracle.

## 1. Scope

This checkpoint owns the exact public rapid-base → one ordinary SR full-charge shot lifecycle emitted by a self `burst_cast` weapon change whose lifetime is one consumed bullet.

Public source shapes:

- `스쿼드2` — 츠바이 `과충전 공식`
- `레이드_헬름아쿠아스노우` — 스노우 화이트 `세븐스 드워프 : I`

Compiled common shape:

- base weapon: non-clip `auto`
- target: self
- trigger: `burst_cast`
- changed weapon: `SR`
- changed max ammo: `1`
- no finite time duration
- `duration_bullets=1`
- positive `damage_coeff`
- positive `charge_time`
- positive `full_charge_mult`
- **no `skill_damage=True`**
- one sibling self `pierce_enabled` buff with the same `burst_cast` trigger and `duration_bullets=1`

Wider shapes remain fail-closed.

## 2. Moris oracle

### Zwei / 과충전 공식

Observed first session:

- mode enter: `3.05`
- changed SR full-charge shot: `4.266667`
- weapon-change and one-shot pierce lifetime end on that shot
- base SG resumes on next Moris outer frame: `4.283333`

### Snow White / 세븐스 드워프 : I

Observed first session:

- mode enter: `3.35`
- changed SR full-charge shot: `8.35`
- weapon-change and one-shot pierce lifetime end on that shot
- base AR resumes on next Moris outer frame: `8.366667`

The changed SR shot is an ordinary full-charge weapon attack, not a weapon-mode skill shot.

## 3. Resume semantics

A key oracle result is that mode end does **not** restore the pre-entry rapid magazine or a newly computed full magazine.

After the changed one-shot SR is consumed, Moris resumes the base rapid weapon on the next repeated-add 60 Hz observation frame with exactly **one restored base round**. That base shot then reaches zero and proceeds into the ordinary reload lifecycle.

Fast therefore adds a sparse `resume_after_single_charge()` re-anchor:

- no global 60 Hz loop
- use existing Moris frame-lattice helpers
- schedule first base shot on `moris_next_tick(mode_shot_time)`
- base rapid ammo = `1`
- preserve compressed rapid runtime thereafter

## 4. Source-frame precision repair

An initial staged implementation exposed a real Snow White divergence:

- decimal cast boundary was represented as `3.35`
- naive `3.35 + 5.0` then Moris observation produced `8.366667`
- Moris repeated-add timeline observes the source frame itself such that the 5-second charge releases at `8.35`

The repair is restricted to this one-shot mode family:

- anchor mode entry to `moris_observed_tick(now, epsilon=1e-9)`
- keep ordinary dynamic charge behavior unchanged
- do not hide the mismatch with a wider tolerance

## 5. Bullet lifetime and ordering

The changed SR shot must see both one-shot states before they are removed:

1. score ordinary full-charge changed-weapon shot
2. emit already-owned reducible hit-count crossings where applicable
3. consume `duration_bullets=1`
4. remove weapon change and sibling `pierce_enabled`
5. resume base rapid on next Moris frame

This reuses `ActiveEffectStore.consume_dynamic_bullet()` and the existing sparse boundary system rather than materializing every frame.

The mode itself is also registered as a dynamic bullet-lifetime target. This is deliberately different from Nayuta `기억 연소`, whose skill-weapon shots do not consume ordinary bullet-duration buffs.

## 6. Score ownership proof

Score certification requires all of the following:

- exactly one weapon-change affecting the actor
- exact rapid → one-shot SR shape
- exact one-shot self `pierce_enabled` companion
- no named-state reference graph around the weapon-change state
- no executable raw `full_charge_hit` / `on_attack` consumers introduced by this checkpoint
- existing reducible `hit_count` consumers may continue through the already-owned charge cadence path

Public owned scope regression confirms exactly the intended Zwei and Snow White shapes.

Still-unowned class-changing examples remain explicitly fail-closed:

- `레이드_네온벨벳` — `weapon_change:벨벳:깔끔한 마무리`
- `레이드_작열짬` — `weapon_change:모더니아:섬멸 모드`

## 7. Transitive Privaty dependency change

`스쿼드2` had a pre-existing generic dynamic reload implementation for Privaty `EX 매거진 2`, but its score proof was blocked by an unsafe recipient cadence.

Once Zwei's exact cadence became owned, that recipient dependency became safe. Therefore this checkpoint also removes:

- `cadence:프리바티:EX 매거진 2:reload_speed_pct` from `스쿼드2`

This is not a new Privaty mechanic implementation; it is a transitive proof consequence of the newly certified recipient cadence.

`EX 매거진 3:max_ammo_pct` remains fail-closed in `스쿼드2`, and other public Privaty pairs retain their unresolved recipient dependencies.

## 8. Stale regression repair

Focused tests passed before full discovery, but full Fast discovery found five regressions that encoded the old frontier rather than runtime semantics:

- two de-duplicated cadence-count expectations (`53` → `52`)
- two Snow White tests requiring `세븐스 드워프 : I` weapon-change/pierce blockers to remain
- one generic class-changing weapon-change test whose only Snow White witness was the newly owned exact shape

They were updated narrowly:

- new current cadence count only
- newly owned Snow White blockers asserted absent
- unrelated Velvet/Modernia class-changing families asserted present

No runtime mismatch was masked.

## 9. Promotion validation

Temporary promotion gate:

- workflow run `34135447642`
- job `101785202117`
- result: `success`

Focused / neighboring regressions:

- new single-charge suite: `5/5`
- neighboring grouped suite: `35/35`
- performance sample median: `198.38ms`, events `539`

Complete Fast discovery:

- `361/361`
- `65.368s`
- performance median in complete run: `201.28ms`, events `539`

Promotion guard also rechecked:

- `master == fb2fd9157aa14499daf6b9f185beb685d4393f90`
- no `calculator/` diff
- staged diff limited to `fast_engine/`

Semantic commit diff:

- 12 `fast_engine/` files
- 420 insertions / 40 deletions
- engine changes: dispatcher, dynamic rapid, dynamic weapon, score
- one new focused regression file plus neighboring expectation repairs

## 10. Public frontier A/B

Before this checkpoint:

- source cases `24`
- certified `6`
- gaps `18`
- cadence `56`
- normal_delivery `47`
- weapon_change `4`

After:

- source cases `24`
- certified `6`
- gaps `18`
- cadence `55`
- control `5`
- normal_delivery `45`
- normal_state `18`
- periodic_grid `1`
- skill_damage `25`
- skill_state_delivery `49`
- weapon_change `2`

Direct intended removals:

- `weapon_change:츠바이:과충전 공식`
- `normal_delivery:츠바이:과충전 공식 2:pierce_enabled`
- `weapon_change:스노우 화이트:세븐스 드워프 : I`
- `normal_delivery:스노우 화이트:세븐스 드워프 : I 2:pierce_enabled`

Transitive removal:

- `cadence:프리바티:EX 매거진 2:reload_speed_pct` in `스쿼드2`

`레이드_헬름아쿠아스노우` now has only:

- `periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval`
- `normal_state:미란다:웨이크업! 4:rank_target_timing`

Certified count remains `6` because affected public rosters still have other blockers.

## 11. Cleanup

All checkpoint-only temporary assets were removed after semantic promotion:

- `.github/workflows/tmp-next-frontier.yml`
- `.github/tmp_single_charge_apply.py`
- `.github/tmp_single_charge_fix1.py`
- `.github/tmp_single_charge_regression_fix.py`

Final workflow hygiene must remain:

- `.github/workflows/ci.yml`
- `.github/workflows/pages.yml`

## 12. Boundary for next work

This checkpoint is closed.

Do not widen it into:

- arbitrary rapid → charge weapon changes
- arbitrary `duration_bullets` weapon modes
- raw `full_charge_hit` / `on_attack` families
- global 60 Hz simulation
- character-name runtime branches

Continue the project phase as **false-supported safety closure → semantics restoration** and select the next single checkpoint from the current frontier only after final canonical CI is green.
