# Ada targeted effect-interval periodic-grid checkpoint — 2026-09-08

Status: **COMPLETED**

## 1. Scope

Repository: `asdadas1113/nikke-calc`

Branch: `fast-engine-phase2-20260901`

Protected baseline:

- `master`: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- `calculator/` was used only as the Moris oracle and was not modified.

This checkpoint restores one generic semantic slice:

> a finite self `burst_cast` `effect_interval` buff that names exactly one same-actor score-supported periodic damage effect through `target_effect`, with Moris-style mid-cooldown phase rescaling.

Public source case:

- `레이드_헬름아쿠아스노우`

Public producer/target pair:

- Ada `섬광 수류탄 투척 발동 시간 조건`
  - `effect_type=buff`
  - `stat=effect_interval`
  - `value=-1.0`
  - `duration=10.0`
  - `max_stack=1`
  - `target=self`
  - `parameters={"target_effect": "섬광 수류탄 투척"}`
  - one `burst_cast` event trigger
- Ada `섬광 수류탄 투척`
  - `effect_type=damage`
  - `stat=armor_break_damage`
  - value `420`
  - enemy target
  - periodic base interval `2.0s`
  - gated by `during_full_burst`
  - already supported by `SimpleDamageScoreSink`

This checkpoint does **not** generalize arbitrary interval modifiers, arbitrary target scopes, arbitrary conditions, multiple target effects, or non-damage periodics.

## 2. Why the existing blocker was real

Before this checkpoint, the public row carried:

- `periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval`

The modifier itself was not runtime executable. Removing only the blocker would therefore have been a false-supported change.

A diagnostic run with a real `SimpleDamageScoreSink` confirmed that Ada's periodic damage was already score-supported; the missing semantic was specifically the changing `every:Ns` cadence.

## 3. Moris oracle

`calculator/buff_manager.py` owns the reference behavior for `every:Ns` effects.

For a periodic effect with base interval `base_interval`, Moris computes an effective interval using matching `effect_interval` modifiers and, when the interval changes while a cooldown is in progress, rescales the remaining cooldown proportionally:

```text
next_t = t + max(0, next_t - t) * (new_interval / previous_interval)
```

After a fire, the next raw deadline advances by the current interval.

Ada changes `섬광 수류탄 투척` from `2.0s` to `1.0s` during the 10-second modifier window.

### Exact public timing

Relevant Moris burst sequence in the 35-second oracle run:

- `21.233333...` Miranda burst cast
- `21.383333...` Helm burst cast
- `21.533333...` Ada burst cast — interval modifier activates
- `21.583333...` full burst starts

Moris grenade activations:

- `4.016666666666658`
- `6.016666666666651`
- `8.016666666666644`
- `10.000000000000076`
- `12.000000000000176`
- after Ada's second burst cast:
  - `21.783333333333378`
  - `22.783333333333320`
  - `23.783333333333264`
  - `24.783333333333207`
  - `25.783333333333150`
  - `26.783333333333093`
  - `27.783333333333037`
  - `28.783333333332980`
  - `29.783333333332923`
  - `30.783333333332866`

## 4. The first staged divergence

The first sparse implementation rescaled immediately on Ada's `burst_cast` frame and produced the first accelerated grenade at:

- Fast: `21.766666666666712`
- Moris: `21.783333333333378`

This was an exact one-frame error.

The cause was Moris phase ordering, not tolerance or arithmetic noise:

- the outer Moris loop runs `BuffManager.tick()` / periodic cooldown processing before the burst controller on a frame;
- Ada's `burst_cast` modifier is created later on that same frame;
- therefore the periodic subsystem first observes the new interval on the **next repeated-add 60 Hz frame**.

The fix did not add a 60 Hz global loop. Instead it schedules one sparse `PERIODIC_SYNC` observation boundary on `moris_next_tick(cast_time)` for an actor that owns one of these exact interval relationships.

After this change the public Fast activation list matches Moris frame-for-frame.

## 5. Sparse runtime design

New module:

- `fast_engine/engine/dynamic_periodic.py`

`DynamicPeriodicCadenceRuntime` owns only periodics explicitly targeted by a supported modifier.

It stores per owned periodic:

- base interval
- current interval
- raw `next_nominal` deadline
- generation number

On interval change it rescales only the remaining raw cooldown. The resulting deadline is observed through the existing repeated-add Moris frame lattice.

Old reservations are not globally cancelled; generation-tagged tokens make stale reservations no-ops.

Additional generic pieces:

- `ActiveEffectStore.sum_targeted_stat(...)`
  - sums a stat only from active effects whose `target_effect` names the periodic being evaluated
- `EventKind.PERIODIC_SYNC`
  - sparse phase boundary used only for the next-frame observation described above
- `BurstRuntime`
  - excludes dynamically owned periodics from the fixed-periodic scheduler
  - routes dynamic periodic ticks through generation tokens
  - immediately reconciles expiry-side interval transitions
  - defers burst-cast-side transitions to the next Moris frame

### Sparse-event performance repair

An intermediate version scheduled deferred periodic sync after every burst-machine event and increased the normal performance contract event count from `539` to `577`.

Although semantically harmless, this violated the intended sparse shape.

The final implementation records the actors that actually own a supported targeted interval relationship and schedules a deferred sync only after that actor's `burst_cast` signal. This is actor/shape based, not character-name based.

Final performance contract event count returned to:

- `539`

## 6. Narrow ownership proof

`TriggerDispatcher._finite_self_effect_interval_shape_supported()` accepts only the following producer shape:

- `effect_type == "buff"`
- `stat == "effect_interval"`
- self target
- explicit numeric value
- positive finite duration
- no stacking beyond one
- no `tick_interval`
- parameters exactly `{target_effect}`
- no condition rules
- exactly one event trigger
- event key exactly `burst_cast`

The score proof additionally requires:

- exactly one same-actor compiled effect with the named `target_effect`
- exactly one positive periodic trigger on that target
- target effect type is `damage`
- `SimpleDamageScoreSink` supports that target damage effect

Only then is the `periodic_grid` blocker removed.

Malformed neighboring variants remain fail-closed in regression tests.

## 7. Validation

Semantic promotion run:

- workflow run `34150287961`
- job `101830953514`
- result: `success`

Focused validation:

- new Ada effect-interval regression: `3/3`
- neighboring periodic/runtime/performance regressions: `17/17`
- public Fast/Moris grenade activation frames match to 9 decimal places

Full Fast discovery before promotion:

- `364/364`
- `65.253s`

Structural performance sample:

- median `199.36ms`
- events `539`

Production semantic commit:

- `2063efc88d4947225b44746bab29364afc9a09cf` — `Fast: support targeted dynamic periodic intervals`

Semantic diff:

- 9 `fast_engine/` files
- 480 insertions / 23 deletions
- no `calculator/` diff

## 8. Public frontier A/B

Before:

- source cases `24`
- certified `6`
- gaps `18`
- `periodic_grid = 1`

After:

- source cases `24`
- certified `6`
- gaps `18`
- `periodic_grid = 0`

Other family counts remain:

- cadence `55`
- control `5`
- normal_delivery `45`
- normal_state `18`
- skill_damage `25`
- skill_state_delivery `49`
- weapon_change `2`

`레이드_헬름아쿠아스노우` is now exactly one blocker from certification:

- `normal_state:미란다:웨이크업! 4:rank_target_timing`

Its `unsupported` tuple is empty.

Certified count stays at 6 because that Miranda blocker remains.

## 9. Cleanup

All temporary Ada diagnostic/promotion assets were removed after semantic promotion:

- `.github/tmp_periodic_grid_probe.py`
- `.github/tmp_periodic_grid_apply.py`
- `.github/tmp_periodic_grid_fix1.py`
- `.github/tmp_periodic_grid_fix2.py`
- `.github/tmp_periodic_grid_regression_fix.py`
- `.github/workflows/tmp-periodic-grid-probe.yml`

Final hygiene before documentation:

- `.github/` contains only `scripts/` and `workflows/`
- `.github/workflows/` contains only `ci.yml` and `pages.yml`

## 10. Next boundary

This checkpoint is closed.

The current phase remains:

**false-supported safety closure → semantics restoration**

`레이드_헬름아쿠아스노우` is a high-leverage next investigation because only Miranda `rank_target_timing` remains, but that must be treated as a new independent semantic checkpoint:

1. inspect the exact compiled Miranda shape and all target-ranking dependencies;
2. use Moris oracle first;
3. prove ranking is stable or implement the actual dynamic rank timing;
4. do not remove the blocker merely to certify the roster;
5. run focused regression, full Fast discovery, frontier A/B, and canonical CI before promotion.
