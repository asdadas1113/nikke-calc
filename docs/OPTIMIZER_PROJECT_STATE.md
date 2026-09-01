# Roster Optimizer / Fast Engine — Current Project State

> **Canonical handoff. Read this file first in a new chat/session.**
>
> Last consolidated: **2026-09-01**.
>
> Repository: `asdadas1113/nikke-calc`
>
> Development branch: `fast-engine-phase2-20260901`

## 0. Immediate resume point

### Latest fully verified Fast code checkpoint

`2017fbc18189d5351c9f33f24fe8467cb8fbaee8`

Message: `docs: record core-count parity lessons`

GitHub Actions run `33477782548` completed fully green. It included:

- doclint;
- all Fast burst/state/trigger/damage/runtime/weapon suites;
- the dedicated Fast **core semantics** gate;
- structural performance;
- calculator regression;
- optimizer tests;
- bridge smoke tests;
- browser tests;
- golden snapshots **29/29**.

The structural Fast score fixture in that run measured:

```text
median = 20.19 ms / 180 s five-person score
samples = [20.19, 19.90, 20.50] ms
events = 358
```

Treat this as a CI-runner reference point, not a universal microbenchmark.

A later commit may be documentation-only. Always check the current branch HEAD and latest CI before writing code, but do not reopen already-certified core work merely because the handoff document itself has a newer SHA.

### What was completed since the previous handoff

The old resume point around `3e561a8c...` is obsolete. The branch is back to green and now includes:

1. compiler effect-source provenance fix using Moris `_source_tag`;
2. floating-point damage-kernel test tolerance fix for sub-`1e-8` noise;
3. weapon-specific core probability wired into normal scoring;
4. Moris parity tests for AR/SMG/SG/MG/SR/RL core probability and accuracy;
5. compressed expected `core_hit_count:N` threshold boundaries;
6. real parsed core-count damage evidence with `루드밀라 : 윈터 오너` / `눈보라`;
7. real parsed core-count buff evidence with `길로틴 : 윈터 슬레이어` / `경험치`;
8. fail-closed protection when ammo refill or other live weapon state can invalidate a static core/cadence plan;
9. the same ammo-refill protection added to ordinary static normal-attack scoring;
10. a dedicated CI gate so core-probability and core-boundary tests cannot silently fall outside test discovery.

### First action in the next session

The next major task is **ranking validation**, not another mechanic chosen by intuition.

Build a reusable validation harness that can compare a broad Fast-scored candidate pool with Moris authoritative scores and report at least:

- Moris Top-N recall inside Fast Top-K;
- pairwise ordering accuracy;
- catastrophic false-negative / tail-miss rate;
- systematic bias by weapon class, mechanic and archetype;
- unsupported/blocker frequency and which mechanics cause it;
- Fast calls, Moris calls, wall time and peak memory;
- eventually the final five-team Moris score after Fast shortlist/allocation.

Use public/synthetic fixtures in Git. Real account samples may be used locally for measurement but must not be committed.

Use the unsupported/blocker distribution from this harness to decide whether the next implementation should be dynamic ammo/cadence/core replanning, `crit_hit_count:N`, or another missing primitive. Do not assume which one matters most before measuring.

## 1. Project goal

Given an account roster/build, discover five strong non-overlapping Solo Raid teams without brute-forcing every five-person squad through full Moris simulation.

Target production pipeline:

```text
account/profile
    ↓
structural candidate generation
    ↓
Fast Engine broad scoring (thousands of squads)
    ↓
wide shortlist + protected/diversity candidates
    ↓
Moris authoritative re-score
    ↓
exact 5-team no-overlap allocation
    ↓
optional replacement/refinement
```

The intended use is explicit: **Fast should make thousands of candidate evaluations cheap enough that Moris can be reserved for the shortlist and final allocation.**

## 2. What Fast is optimizing for

Fast is not a second detailed combat calculator.

Priority order:

1. throughput;
2. Moris Top-N recall inside Fast Top-K;
3. low catastrophic false-negative rate;
4. stable pairwise ordering across weapon/mechanic/team archetypes;
5. preservation of meaningful synergy;
6. absolute Fast-vs-Moris damage accuracy.

A small, broadly shared absolute error can be acceptable. A mechanic-specific error that systematically pushes a strong archetype down the ranking is not acceptable even if mean absolute error is small.

False negatives are more expensive than false positives: Moris can remove an over-ranked squad later, but cannot recover a strong squad that Fast pruned.

## 3. Non-negotiable architecture rules

- Moris remains the final damage authority.
- Normal Fast evaluation must not call `calculator.timeline.simulate()`.
- Runtime is continuous-time/event-driven, not a global 1/60 loop.
- No global per-bullet objects/events when state does not change.
- Aggregate unchanged shot spans and only materialize meaningful boundaries.
- Unknown/unjustified mechanics must never silently become zero.
- Capability claims must be conservative: partial auxiliary support does not imply general READY.
- Runtime core should be character-name blind wherever possible.
- Unique character behavior should be represented as generalized mechanics/constraints if possible.
- Anonymous account/profile/personal temporary data must never be committed.
- `master` must never be modified or merged implicitly from this work.
- `calculator/` should not be changed unless an explicitly intended Moris fix is being made; Fast work should stay outside it by default.

Current `master` SHA remains:

`fb2fd9157aa14499daf6b9f185beb685d4393f90`

## 4. Debugging rule for character-specific anomalies

Do not modify common runtime logic merely because one character disagrees with Moris.

Use this diagnosis order:

1. same error across many characters → common formula/runtime issue;
2. same error across one mechanic/weapon cohort → mechanic module issue;
3. error isolated to one character → inspect that character's parsed data and unique mechanics first.

Typical unique mechanics to inspect:

- position/adjacency;
- target-selection rules such as Top ATK/Lowest ATK/B3-only;
- HP/ammo/stack/gauge conditions;
- snapshot vs continuously re-evaluated selection;
- unusual stacking/refresh behavior;
- caster-based values;
- max-HP/charge/core/share damage;
- invulnerability/cover/taunt/pierce/parts/summons;
- source-order effects and delayed burst damage.

Preferred layering:

```text
common calculation
    ↓
mechanic-level handler
    ↓
character-specific exception only if genuinely unavoidable
```

A character exposing a mechanic first does not make that mechanic character-specific.

## 5. Current Fast implementation — completed/validated foundations

Production code: `fast_engine/engine/`

Tests: `fast_engine/tests/`

### Compile/input boundary

- Moris `context.spec.build_squad()` remains input authority.
- Fast compile reuses Moris base-stat/build/favorite-stage semantics.
- Compiled model is immutable and runtime-oriented.
- Capability inventory/fail-closed routing exists.
- Moris effect provenance (`skill` / `equipment` / `cube` / `collection`) is preserved through `_source_tag`.

### Scheduler/state

- continuous-time stable scheduler;
- equal-time Moris semantic phases: expiry → periodic → burst → weapon;
- actor/domain-scoped state versions;
- generation-token expiry/refresh;
- active-effect target cohorts preserve cohort identity;
- same-caster/time/raw rank target shares cohort snapshot.

### Burst runtime

- B1→B2→B3→Full Burst cycle;
- stage override/reentry primitives;
- burst cooldown reduction paths;
- fixed periodic `every:Ns` scheduling;
- battle horizon is `[0, duration)`, matching Moris end-boundary behavior.

### Weapon/cadence

- AR/SMG fixed cadence;
- SG pellets/muzzles;
- MG warmup + frame-rate cap semantics;
- SR/RL charge cadence;
- ammo/reload/clip reload;
- reload start/post delays;
- permanent cadence modifiers;
- dynamic charge cadence and replanning;
- `full_charge_count:N` compressed boundaries;
- actor-selective raw `full_charge_hit` producer;
- first safe `last_bullet_fire` slice;
- multi-signal charge boundary support.

### Important corrected count semantics

`hit_count` and `pellet_hit` are distinct.

Moris treats ordinary weapon `hit_count` as **one per trigger pull/shot**, while `pellet_hit` is per pellet. Fast temporarily over-counted SG `hit_count` by pellet count; this was identified as a ranking-bias bug and corrected.

Do not reintroduce pellet-based generic `hit_count` without new Moris evidence.

### Target primitives

Includes general modes needed by validated cases such as:

- all/self/excluding self;
- weapon/class/element;
- adjacent;
- burst-casted / not-casted;
- B3;
- Top ATK;
- Lowest ATK among base B3 actors;
- named-state cohorts.

### Damage kernel / state resolver

- deterministic expected-value DealForm;
- ATK/DEF/crit/core/charge/FB/type/received/element layers;
- actor-scoped cached `DamageTerms`;
- source/caster-based ATK handling;
- enemy defense-down/personal routing corrected;
- normal attack expected damage aggregation;
- static shot blocks (`1 DealForm × N shots`);
- `accuracy_pct` is resolved into damage state and can affect actor-specific core probability.

### Score vertical slice

`score_static_squad()` can combine:

- compressed normal attacks;
- currently certified simple damage events;
- supported state/buff delivery;
- explicit `unsupported` damage-event reporting;
- fail-closed comparison-critical state blockers.

Validated static fixtures have shown per-character/combined Fast-vs-Moris comparisons within about 1% for supported subsets. Ranking validation, rather than this absolute-error observation, is the required production gate.

### B3 pending bonus damage

Implemented safe slice for Moris B3 behavior:

- exact `stat == "bonus_damage"` can be queued at `burst_cast`;
- damage is evaluated after `full_burst_start` buffs settle;
- `bonus_damage:N` remains immediate multi-hit, not pending;
- source-order cases with later same-cast buffs remain fail-closed unless explicitly modeled.

Actual Liberelio B3 was used as parity evidence.

### Fixed DoT — certified first slice

Implemented first fixed-tick DoT slice:

- fixed coefficient;
- fixed tick interval;
- no stack/gauge/dynamic coefficient scaling;
- generation-token refresh invalidates stale queued ticks;
- default first tick after one interval;
- `tick_start: immediate` starts immediately;
- default expiry-boundary and immediate-expiry semantics mirror Moris.

Synthetic tests and a real Mana DoT parity fixture pass. Complex DoT remains fail-closed.

## 6. Core probability / expected core-hit count — current certified state

### Weapon-specific core probability

The old static scalar remains a fallback:

```text
effective_core_rate = core_uptime × core_hit_rate_when_open
```

When `core_px` is supplied, Fast now mirrors Moris weapon accuracy geometry per actor:

```text
D = max(base_diameter - acc_slope * accuracy_pct, 1)
R = D / 2
r_core = core_px / 2
P_core = min(1, (r_core / R) ** model_n)
```

Parameters are lowered from `data/weapon_mechanics.json`.

Fast parity tests cover AR/SMG/SG/MG/SR/RL at multiple accuracy values. Normal scoring resolves each actor's current `accuracy_pct` and uses that actor's weapon-specific core probability rather than a squad-wide common scalar.

### Expected `core_hit_count:N`

Fast now supports a **static-cadence certified slice** of expected `core_hit_count:N`:

- expected fractional core probability is accumulated per physical hit/pellet, matching Moris expected-mode semantics;
- only absolute threshold crossings observed by executable effects are materialized;
- no scheduler event is created for every probabilistic core hit;
- one physical shot can cross several observed thresholds and produce ordered compressed increments;
- core boundaries are scheduled before shot-level `hit_count`/`on_attack` boundaries at equal timestamps, matching Moris ordering.

Real parsed evidence exists for both effect classes:

- `루드밀라 : 윈터 오너` — `눈보라`, damage, `core_hit_count:60`;
- `길로틴 : 윈터 슬레이어` — `경험치`, self ATK buff, `core_hit_count:3`.

### Moris authority spelling gap discovered during parity work

Current parsed data uses canonical `core_hit_count:N`. Moris expected-mode `_notify_frac()` is designed to feed fractional `core_hit` events for these count mechanics, but the current BuffManager timing matcher accepts the older `core_hit:N` form and does not directly match canonical `core_hit_count:N`.

Therefore current real parity tests do **not** modify `calculator/`. They isolate only this spelling gap at the test boundary by temporarily aliasing the real parsed timing to the old Moris spelling, run the intended authority mechanics, then restore the module table.

Do not change Fast to imitate the current silent Moris omission. If the Moris matcher is fixed later, treat it as an explicit calculator bugfix with its own tests and expected snapshot review.

### Static-core fail-closed boundary

Precompiled core boundaries are rejected when future probability or firing cadence can change through live state, including relevant cases such as:

- live accuracy changes;
- reload/max-ammo changes;
- ammo refill (`ammo_charge_flat`, `ammo_charge_pct`);
- attack/charge speed changes;
- pellet shape changes;
- weapon changes;
- dynamic charge actors not covered by the static plan.

Permanent unconditional self cadence folded at compile time remains safe.

The same ammo-refill problem applies to ordinary static shot blocks, so static normal scoring also blocks such squads rather than silently using a stale firing timeline.

## 7. Explicit fail-closed / not-yet-certified areas

This list is intentionally conservative and should be updated as mechanics are certified.

- generic raw `hit_count` every-hit producer where a consumer truly needs every event rather than compressed counts;
- expected `crit_hit_count:N` production;
- dynamic core-boundary replanning when accuracy/ammo/reload/attack/charge state changes future probabilities or shot times;
- legacy `core_hit:N` threshold semantics as a production static-boundary primitive when trigger-count reduction can alter the effective threshold;
- dynamic multi-hit charge intra-shot threshold crossing where not explicitly represented;
- dynamic periodic interval rescaling from `effect_interval` / skill-cooldown-style modifiers;
- complex DoT: stacks, gauges, `dmg_scale_mag_pct`, same-target ramp, dynamic coefficients;
- arbitrary source-order delayed burst masks beyond the certified B3 pending slice;
- boss attack/incoming-damage scripts;
- immunity windows/movement/stun/cover destruction;
- timed part-break chronology;
- unsupported derived stats such as HP-derived ATK/copy/magnification unless individually implemented;
- broad final ranking use for squads whose `FastScore.unsupported` or blockers remain comparison-critical.

Patternless enemy effects that require incoming enemy attacks may be classified as unreachable rather than unsupported, but only under the explicit static-enemy contract.

## 8. Performance contract

The engine must stay suitable for **thousands of candidate evaluations**.

Performance principles:

- no global 60 FPS loop;
- no global every-shot scheduler traffic;
- selective raw producers only for actors/effects that consume them;
- compressed shot blocks;
- cached damage snapshots;
- threshold-crossing events rather than raw counts;
- DoT ticks are explicit only when they are actual meaningful damage boundaries.

Useful historical measurements from this branch:

- ~59.33 ms / 180 s five-person score near an earlier broad-score checkpoint;
- 15.41 ms / 358 events in an earlier structural-performance run;
- **20.19 ms median / 358 events** in the fully green `2017fbc...` CI run after core-count and safety work.

Do not compare different measurements as regressions unless fixture/runtime scope is confirmed identical. Keep the CI regression gate conservative. Production measurement should include calls/sec and end-to-end shortlist wall time, not just one microbenchmark.

## 9. Validation hierarchy before optimizer integration

### Primitive correctness

Synthetic tests for scheduler, targets, counts, DoT, damage formula and boundary order.

### Static Moris comparison

Under equivalent conditions compare:

- per-character damage;
- squad total;
- burst timing;
- shot/reload counts;
- important effect windows;
- trigger count/timing.

### Ranking validation — **current highest priority**

This is the most important missing project gate.

Measure across representative candidate sets:

- Moris Top-N recall inside Fast Top-K;
- pairwise ordering accuracy;
- false-negative/tail failure rate;
- bias by weapon class/mechanic/archetype;
- unsupported/fallback/blocker frequency;
- final five-team Moris score after Fast shortlist;
- Fast calls, Moris calls, wall time, peak memory.

Do not choose shortlist width by intuition.

The validation harness should preserve enough metadata to answer **why** misses occur. In particular, classify candidates by blocker/unsupported reason so missing mechanics can be prioritized by actual ranking impact rather than implementation convenience.

## 10. Candidate-generator principles

Fast is only useful if candidate generation has high recall.

Do not overfit generic synergy scores to rare character gimmicks. Represent hard/soft mechanic constraints separately:

- burst-stage completeness;
- cooldown feasibility;
- sustain requirement;
- element/weapon/boss compatibility;
- position/adjacency constraints;
- target-selection dependencies;
- burst-caster dependencies.

Rare plausible mechanic combinations should be protected into the Fast pool rather than hard-pruned early. Prefer some false positives over strong-squad false negatives.

Once Fast can score enough squads, rerun the algorithm reset audit:

1. stronger Pure baseline;
2. existing Meta/Cold policies without retuning;
3. ablate scarcity-era heuristics;
4. keep only heuristics that still improve recall/tail behavior.

## 11. Git safety / data rules

### Branches

- **Never modify/merge `master` as part of Fast development.**
- Fast branch: `fast-engine-phase2-20260901`
- master currently: `fb2fd9157aa14499daf6b9f185beb685d4393f90`

### Data

Never commit:

- anonymous account JSON;
- raw profile snapshots;
- OpenID/account identifiers;
- local personal data;
- temporary user fixtures derived from private accounts.

Real account data used during development must remain outside Git. Git tests should use synthetic/public/static fixtures.

### Moris calculator

Moris is the authority and should remain intact. Do not casually change `calculator/` merely to make Fast match. If one character disagrees, inspect unique mechanics/data first.

The discovered canonical `core_hit_count:N` matcher gap is a legitimate Moris issue, but fixing it is a separate explicit calculator change because it may alter real calculator results and snapshots.

## 12. Files to read in a fresh session

Read in this order:

1. `docs/OPTIMIZER_PROJECT_STATE.md` — this file, current handoff;
2. `docs/FAST_ENGINE_ARCHITECTURE.md` — architecture/performance contract;
3. `fast_engine/research/LESSONS.md` — research lessons and anti-overfit rules;
4. current branch HEAD and latest CI logs;
5. ranking/candidate files under `optimizer/` plus `fast_engine/engine/score.py` and blocker/capability code needed by the validation harness.

For core-specific debugging, also read:

- `fast_engine/engine/core_events.py`;
- `fast_engine/engine/burst_runtime.py`;
- `fast_engine/tests/test_core_probability.py`;
- `fast_engine/tests/test_core_hit_events.py`;
- `fast_engine/tests/test_damage_core_hit_real_parity.py`;
- `fast_engine/tests/test_damage_core_hit_buff_parity.py`;
- `fast_engine/tests/test_damage_score_safety.py`.

Do not rely on chat memory when Git/docs disagree.

## 13. Historical references

Useful experiment history:

- `docs/roster-optimizer-prototype.md`
- `docs/optimizer-performance-deferred.md`
- `docs/meta-guided-cold-pool.md`
- `docs/search-budget-study.md`
- `docs/placement-order-study.md`
- `docs/BENCHMARK.md`
- `docs/DEVLOG.md`

The removed Crown/Mast research prototype must not be restored as a production dependency. Retained lessons live only in `fast_engine/research/LESSONS.md`.
