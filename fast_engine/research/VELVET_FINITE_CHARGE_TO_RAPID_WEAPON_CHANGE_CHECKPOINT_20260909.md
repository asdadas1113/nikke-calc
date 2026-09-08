# Velvet finite charge→rapid weapon-change checkpoint — 2026-09-09

Status: **COMPLETED**

## 1. Scope

This checkpoint restores one narrow reusable class-changing weapon mode without widening unsupported weapon-change families.

Public source case:

- `레이드_네온벨벳`
- actor: `벨벳`
- effect: `깔끔한 마무리`

Exact compiled producer shape:

- base weapon fire mode: `charge` (SR)
- `effect_type = weapon_change`
- target: `self`
- one `EVENT` trigger: `burst_cast`
- finite positive duration: `10.0s`
- temporary `weapon_type = MG`
- temporary `damage_coeff = 7.0`
- temporary `max_ammo = -1`
- no condition rules
- no tick interval
- no stacking/wider dependency graph

Production semantic commit:

- `822944c3de7719434ef97e49225c81d517908b6b` — `Fast: support finite charge-to-rapid weapon changes`

`master` / Moris oracle baseline remains:

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

`calculator/` production was not modified.

## 2. Why the old blocker was real

The previous `weapon_change:벨벳:깔끔한 마무리` blocker could not safely be removed as a static exception.

The temporary mode changes all of the following at runtime:

- weapon class from charge SR to rapid MG
- effective normal-attack coefficient
- magazine semantics to infinite ammo
- MG warmup cadence
- ownership of the actor's shot scheduler
- whole-combat `hit_count` phase while entering and leaving the mode
- base SR charge-state progression while MG owns the actor
- raw expiry → Moris outer-frame resume timing

Ignoring any of these would create false support.

## 3. Moris oracle

The public Moris trace established the required lifecycle.

For the first 10-second MG session:

- temporary MG shots: **451**
- first `hit_count:50` crossing: **6.466666…s**
- nine `hit_count:50` crossings occur during the session

Mode expiry / base SR resume:

- first resume: `13.200000000000236`
- second raw expiry is observed on the next Moris outer frame: `25.74999999999982`
- base SR returns with a live-full magazine and its resumed shot consumes one round (`14 → 13` in the oracle trace)

The count phase is whole-combat rather than mode-local: pre-mode SR hits, temporary MG hits, and post-mode SR hits belong to one actor-scoped `hit_count` sequence.

## 4. Sparse runtime design

No global 60Hz loop was added.

### 4.1 Exact shape/runtime proof

`TriggerDispatcher` now owns only the exact finite self charge→ordinary infinite-MG shape above.

Runtime proof additionally requires:

- base `fire_mode == charge`
- non-clip base weapon
- no base weapon control program

The same proof is wired into both:

- executable-effect admission
- `_activate()` weapon-change whitelist

This second seam matters: the first staging attempt proved the shape executable but did not yet allow `_activate()` to commit it, so focused lifecycle activation failed. The fix was to connect the same exact proof at the activation seam, not to broaden the family.

### 4.2 Frozen base charge state

The existing charge runtime remains the owner of the base SR state, but an owned temporary rapid mode suspends base charge progression while active.

While MG owns the actor:

- base charge prediction returns no shot
- base non-shot progression does not advance
- live base state is preserved rather than reconstructed every frame

On mode exit:

- the temporary weapon disappears
- base ammo is restored to live-full
- the matured base phase is reanchored through existing Moris-frame observation
- base charge scheduling resumes on the first outer frame that observes the raw expiry

### 4.3 Dormant temporary rapid state

The rapid runtime can now register an actor whose base weapon is not rapid as a **mode-only rapid actor**.

Before weapon change it is dormant. On exact temporary MG activation it initializes from the effective weapon view:

- effective MG fire-rate fields
- `fire_rate_max`
- MG warmup cap
- temporary infinite ammo
- current dispatcher `hit_count` seed

This reuses sparse rapid cadence logic rather than introducing a parallel MG simulator.

### 4.4 Effective MG warmup

MG warmup calculations now use the effective temporary weapon rather than assuming the actor's base weapon is already MG.

The existing sparse cadence path still applies the 60fps shot cap and warmup progression. There is no per-frame global bookkeeping.

### 4.5 Whole-combat hit-count handoff

`BurstRuntime` attaches a read-only dispatcher event-count getter to the weapon runtime.

On mode entry:

- rapid state seeds its `hit_count` and dispatched count from the actor's existing dispatcher count

During MG:

- reducible modulo crossings are dispatched normally

On mode exit:

- any residual count since the last reduced crossing is flushed before base SR resume

This preserves the same whole-combat phase without a new global counter.

## 5. Score ownership and fail-closed boundary

`score.py` proves this shape only when the dependency graph is narrow enough for the sparse lifecycle above.

The proof rejects, among other things:

- multiple/overlapping weapon changes for the actor
- state-name consumers or state-end dependencies on the weapon-change name
- unsupported weapon event consumers
- non-reducible / non-modulo `hit_count` consumers
- supported squad-body-hit consumers that would require a wider shot-event model
- reload/control shapes outside the owned contract

`모더니아:섬멸 모드` remains fail-closed and is retained as the neighboring class-changing witness.

No character-name runtime branch was added.

## 6. Tests

New focused regression:

- `fast_engine/tests/test_damage_charge_to_rapid_weapon_change.py`

It covers:

1. exact public shape ownership and Modernia fail-closed neighbor
2. effective MG view plus whole-combat hit-count seed
3. first public MG session = Moris 451 shots and first `hit_count:50` timing
4. residual flush before same-frame live-full SR resume
5. second raw expiry → next Moris outer-frame reanchor
6. neighboring wider modes remain fail-closed

Existing regression updates are limited to stale ownership/frontier expectations caused by this completed slice.

A direct fixture initially jumped the rapid state to count `453` while leaving dispatcher count at the pre-mode `2`; that fixture incorrectly observed residual `+3` as dispatcher count `5`. The production runtime was not wrong. The fixture was corrected to mirror the already-dispatched `450` state before testing the residual flush.

## 7. Staging validation

Final staging gate:

- run `34263340013`
- job `102186484455`
- result: `success`

Results:

- focused Velvet lifecycle: `6/6`
- neighboring weapon-change regressions: `21/21`
- full Fast discovery: `374/374`
- performance median: `180.92ms`
- scheduled events: `539`
- `RAPI_CHAIN_30S` relative error: `0.0003858566668650809`
- public blocker frontier: success
- `git diff --check`: success
- `calculator/` diff: none

The full-suite staging pass also exposed two stale shared-frontier assertions whose aggregate `cadence:` count changed from `52` to `51`; those expectations were updated only after the complete suite demonstrated the new ownership surface. This document does **not** claim a separate public cadence-family checkpoint from that aggregate count alone.

## 8. Promotion

Promotion workflow:

- run `34263609821`
- job `102187383687`
- result: `success`

It reran the same focused, neighboring, full-discovery, frontier, and scope gates, then committed only `fast_engine/` changes.

Semantic diff:

- 12 `fast_engine/` files
- 568 insertions
- 32 deletions
- no `calculator/` production change

## 9. Public frontier after the checkpoint

The public frontier remains:

- source cases: `24`
- certified source cases: `7`
- source-case gaps: `17`

This checkpoint does **not** create an eighth certified team because `레이드_네온벨벳` still has unrelated blockers.

Targeted A/B for `레이드_네온벨벳`:

Removed:

- `weapon_change:벨벳:깔끔한 마무리`

Remaining raw blockers:

- `normal_delivery:네온 : 비전 아이:초화력:atk_dmg_pct`
- `skill_damage:리틀 머메이드:거품 난사:sequential_damage:10`
- `skill_state_delivery:네온 : 비전 아이:초화력:atk_dmg_pct`

Remaining conceptual blockers:

- `damage_delivery:네온 : 비전 아이:초화력:atk_dmg_pct`
- `skill_damage:리틀 머메이드:거품 난사:sequential_damage:10`

`unsupported_count = 0` for this source case.

## 10. Cleanup

Temporary investigation/promotion assets were removed after semantic promotion:

- `.github/tmp_next_frontier_probe.py`
- `.github/workflows/tmp-next-frontier-probe.yml`

Post-clean `.github/` contains only:

- `scripts/`
- `workflows/`

Post-clean `.github/workflows/` must contain only:

- `ci.yml`
- `pages.yml`

## 11. Next boundary

Do not widen this checkpoint into general weapon-change support.

The nearest non-certified public source cases now include both:

- `레이드_네온벨벳` — 3 raw / 2 conceptual blockers
- `스쿼드1` — 3 raw / 2 conceptual blockers

Both share:

- `skill_damage:리틀 머메이드:거품 난사:sequential_damage:10`

That makes Little Mermaid sequential damage a high-leverage **investigation candidate**, not an automatic implementation target.

Before opening it:

1. inspect exact compiled effect and all consumers/dependencies
2. run Moris oracle traces for activation/count/order semantics
3. determine whether a narrow generic sequential-damage runtime is possible
4. if the mechanic widens into unsupported ordering/tick semantics, leave it fail-closed
5. only then run focused → neighboring → full discovery → frontier A/B → promotion
