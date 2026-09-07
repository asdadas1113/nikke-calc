# Miranda lazy rank + one-bullet lifetime checkpoint — 2026-09-08

Status: **COMPLETED**

Production semantic commit:

- `c877c523032459e6232547a1db21fc2db23373b8` — `Fast: support lazy rank bullet lifetimes`

Protected `master` baseline:

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

`master` and `calculator/` were not modified.

## 1. Public source case and blocker

Source roster:

- `레이드_헬름아쿠아스노우`
- `미란다 / 헬름 : 아쿠아마린 / 에이드 : 에이전트 바니 / 스노우 화이트 / 에이다`

Before this checkpoint the roster's only blocker was:

- `normal_state:미란다:웨이크업! 4:rank_target_timing`

`unsupported` was already empty.

## 2. Exact compiled effect

Miranda `웨이크업! 4` compiles as:

- effect type: `buff`
- stat: `crit_rate`
- value: `85.42`
- duration: `None`
- target: `allies_top_atk_excl:1`
- target mode: `top_atk_excl_self`
- trigger: one `full_burst_start` event
- conditions: none
- parameters: `favorite=2`, `duration_bullets=1`

This is not a static-rank case. The roster contains live ATK mutations in the same burst transaction, including Miranda's own top-ATK buff and Ada's burst ATK buffs.

## 3. Moris oracle: target really changes

Moris was instrumented at rank-target resolution. Over 70 seconds the exact `웨이크업! 4` target sequence was:

1. `3.399999999999993` → `스노우 화이트`
2. `21.58333333333339` → `에이다`
3. `37.56666666666582` → `스노우 화이트`
4. `50.94999999999839` → `에이다`
5. `64.33333333333097` → `스노우 화이트`

Therefore the previous blocker could not be removed with a static ranking proof.

A forced diagnostic that only allowed this effect through Fast's **existing** generic lazy-rank pending store produced the same target sequence exactly and left no pending state behind. This established that no new transaction system was required.

Relevant diagnostic runs:

- Moris target probe: run `34151843589`, job `101835584046`
- candidate cadence ownership probe: run `34152604580`, job `101837812215`

## 4. Reused generic lazy infrastructure

The implementation reuses the existing generic machinery:

- `PendingTargetEffect`
- `ActiveEffectStore._pending_target`
- `attach_lazy_target_resolver()`
- `defer_target_group()`
- `_materialize_pending_stat()`

The new production shape is intentionally narrow: one direct-damage state with

- `top_atk_excl_self`
- exactly one target
- exactly one `full_burst_start` trigger
- no conditions
- no finite time duration
- one stack
- `duration_bullets == 1`
- only `favorite` / `duration_bullets` metadata parameters

Neighboring shapes such as two bullets, finite duration, or two rank targets remain fail-closed.

No character-name runtime branch was added.

## 5. Live cadence ownership proof

`possible_ally_targets()` intentionally over-approximates dynamic rank targets. For this public roster it returned all five actors.

Every conservative candidate is already owned by an exact Fast score cadence family:

- Miranda: rapid score cadence safe
- Helm : Aquamarine: rapid score cadence safe
- Ade : Agent Bunny: charge score cadence safe
- Snow White: rapid score cadence safe; existing rapid→single-charge ownership also remains intact
- Ada: charge score cadence safe

Production does not encode these names. The proof is generic: every possible candidate must satisfy charge or rapid score-cadence ownership.

A new rapid analogue of the existing charge bullet-lifetime registration enrolls safe possible rapid recipients into live cadence before scoring.

## 6. One-shot lifetime safety contract

Lazy target selection and `duration_bullets=1` must not fall back to a stale static Nth-shot estimate.

When a deferred one-bullet effect materializes, the resolved recipient must already be in `ActiveEffectStore`'s dynamic bullet-lifetime target set. Otherwise Fast raises:

- `Fast lazy duration_bullets requires live recipient cadence: ...`

The recipient's live weapon runtime then scores the consuming shot first and removes the one-bullet state after the shot's damage/post-hit semantics.

The existing bare-dispatcher safety contract was preserved:

- dynamic-target bullet-lifetime effects remain runtime-executable in a bare dispatcher;
- if strict delivery resolves an unowned actual target, activation still fails atomically through the existing ownership guard;
- no state or scheduler residue is left.

This mattered because the first staged implementation accidentally rejected the effect too early and broke that existing regression contract.

## 7. Staged failures and corrections

First semantic gate attempt:

- run `34152886929`
- job `101838628637`
- new focused tests: `4/4` passed
- failed only because the first ownership check made bare-dispatcher `is_runtime_executable_effect()` false and one older frontier count remained at 6

Correction:

- keep generic executable behavior
- enable lazy delivery only after score runtime has registered every possible recipient
- preserve atomic actual-target failure for unowned bare-dispatcher cases

Second gate attempt:

- run `34152987453`
- job `101838915154`
- focused + neighboring tests passed
- full discovery exposed exactly three stale historical frontier expectations: one old Miranda blocker assertion and two aggregate `certified == 6` assertions

Those tests' mechanic-specific assertions were left intact; only shared-frontier expectations were updated.

## 8. Final validation and promotion

Final semantic gate:

- run `34153154510`
- job `101839405882`
- result: `success`

Results:

- focused Miranda regression: `4/4`
- neighboring regression batch: `25/25`
- complete Fast discovery: `368/368` in `57.660s`
- structural performance: median `181.25ms`, events `539`
- no `calculator/` diff
- protected `master` assertion passed immediately before promotion

Moris/Fast public target selection matches exactly:

- Snow White → Ada → Snow White → Ada → Snow White

The focused regression also verifies that every selected one-bullet state is consumed by the recipient's next live scored shot.

## 9. Semantic production surface

Semantic diff from parent `1599c7ee7b2729f41c92a806c063f53ae157827a` to `c877c523032459e6232547a1db21fc2db23373b8` contains exactly 8 `fast_engine/` files:

- `fast_engine/engine/dispatcher.py`
- `fast_engine/engine/effects.py`
- `fast_engine/engine/score.py`
- `fast_engine/tests/test_damage_miranda_lazy_rank_bullet_lifetime.py` — new
- `fast_engine/tests/test_damage_effect_interval_periodic_grid.py`
- `fast_engine/tests/test_damage_full_charge_bullet_lifetime.py`
- `fast_engine/tests/test_damage_full_charge_hit_charge_speed.py`
- `fast_engine/tests/test_damage_stat_applied_charge_speed.py`

Stats:

- 190 insertions
- 13 deletions

The four older test edits only update shared-frontier expectations made stale by this newly certified roster.

## 10. Public frontier A/B

Before:

- source cases `24`
- certified `6`
- gaps `18`
- `normal_state = 18`
- target roster had one Miranda rank-timing blocker

After:

- source cases `24`
- certified `7`
- gaps `17`
- `normal_state = 17`
- target roster blockers: `()`
- target roster unsupported: `()`

Other family counts at final promotion:

- cadence `55`
- control `5`
- normal_delivery `45`
- skill_damage `25`
- skill_state_delivery `49`
- weapon_change `2`
- periodic_grid `0`

## 11. Cleanup

After promotion all Miranda temporary assets were removed:

- `.github/tmp_miranda_rank_probe.py`
- `.github/tmp_miranda_rank_apply.py`
- `.github/tmp_miranda_rank_fix1.py`
- `.github/tmp_miranda_rank_fix2.py`
- `.github/workflows/tmp-miranda-rank-probe.yml`

Verified clean layout:

- `.github/` contains only `scripts/` and `workflows/`
- `.github/workflows/` contains only `ci.yml` and `pages.yml`

## 12. Design lesson

A dynamic rank blocker should not be treated as proof that a new rank runtime is always needed.

For this case the missing semantic composition was:

1. existing Moris-style lazy target selection,
2. existing live rapid/charge cadence ownership,
3. one-bullet lifetime materialization guarded against stale static scheduling.

The safe solution was to compose those generic pieces, not add a Miranda special case or a global frame loop.
