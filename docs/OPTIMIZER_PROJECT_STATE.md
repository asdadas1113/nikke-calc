# Roster Optimizer / Fast Engine — Current Project State

> **Canonical handoff. Read this file first in a new chat/session.**
>
> Last consolidated: **2026-09-01 13:38 KST**.
>
> Repository: `asdadas1113/nikke-calc`
>
> Development branch: `fast-engine-phase2-20260901`

## 0. Immediate resume point

There are two different Git states that must not be confused.

### Last fully green checkpoint

`a33bafd86d694d435db9188c7045008fbe8fb21a`

Message: `test: connect Liberelio raw full-charge effect`

At that checkpoint the full branch CI completed successfully, including Fast tests, calculator regression, optimizer tests, browser tests and golden snapshots.

Known performance near that checkpoint: roughly **59 ms for a 180 s five-person Fast score** on the CI benchmark used at the time. Treat this as an order-of-magnitude reference, not a forever-stable microbenchmark.

### Current work-in-progress HEAD

`3e561a8c04a12f890d51cbda82a13feff9b69080`

Message: `feat: resolve accuracy into damage state`

This HEAD is **16 commits ahead** of the last fully green checkpoint and contains fixed-DoT work, the SG/hit-count semantic correction, and the beginning of weapon-specific core-probability work.

Its latest CI is **red**, but the failures are currently narrow:

1. `fast_engine.tests.test_compiled_triggers.MorisEffectExpansionTests.test_compiler_includes_all_moris_registered_effect_sources`
   - expected `equipment` source count > 0 but got 0;
   - investigate fixture/build assumptions before changing compiler semantics.
2. `test_damage_kernel.FastDamageKernelParityTests.test_skill_type_layers_and_skill_crit_lane`
   - Fast and Moris differ by only `9.313225746154785e-10`;
   - this is a 9-decimal floating-point assertion issue, not evidence of a meaningful damage-formula divergence.

All other Fast subsystems in that CI run were green, including burst, capabilities/state, dispatch, dynamic weapon signals, periodic, targets, weapon tests and structural performance.

The same red run reported structural Fast performance of about **15.41 ms**, 358 events, for that test fixture. Do not compare this directly to the earlier ~59 ms number unless the benchmark inputs are confirmed identical.

### First action in the next session

1. Fix or correctly reframe the two current CI failures above.
2. Get the current branch back to full green.
3. Then finish weapon-specific core probability wiring.
4. Only after that add expected `core_hit_count:N` threshold production.

Do **not** start a new large primitive before the current HEAD is green.

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

The intended use is now explicit: **Fast should make thousands of candidate evaluations cheap enough that Moris can be reserved for the main shortlist.**

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
- `calculator/` should not be changed unless an explicitly intended Moris fix is being made; current Fast work should stay outside it.

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

Example: Rouge-style adjacency should be a generic position-targeting constraint, not a name-specific synergy bonus.

## 5. Current Fast implementation — completed/validated foundations

Production code: `fast_engine/engine/`

Tests: `fast_engine/tests/`

### Compile/input boundary

- Moris `context.spec.build_squad()` remains input authority.
- Fast compile reuses Moris base-stat/build/favorite-stage semantics.
- compiled model is immutable and runtime-oriented.
- capability inventory/fail-closed routing exists.

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

### Important corrected semantics

`hit_count` and `pellet_hit` are distinct.

Moris currently treats ordinary weapon `hit_count` as **one per trigger pull/shot**, while `pellet_hit` is per pellet. Fast temporarily over-counted SG `hit_count` by pellet count; this was identified as a ranking-bias bug and corrected in the current WIP line.

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
- static shot blocks (`1 DealForm × N shots`).

### Score vertical slice

`score_static_squad()` exists and can combine:

- compressed normal attacks;
- currently certified simple damage events;
- supported state/buff delivery;
- explicit `unsupported` damage-event reporting;
- fail-closed comparison-critical state blockers.

Validated static fixtures have shown per-character/combined Fast-vs-Moris comparisons within about 1% for supported subsets.

### B3 pending bonus damage

Implemented safe slice for Moris B3 behavior:

- exact `stat == "bonus_damage"` can be queued at `burst_cast`;
- damage is evaluated after `full_burst_start` buffs settle;
- `bonus_damage:N` remains immediate multi-hit, not pending;
- source-order cases with later same-cast buffs remain fail-closed unless explicitly modeled.

Actual Liberelio B3 case was used as parity evidence.

### Fixed DoT — current WIP line

Implemented first fixed-tick DoT slice:

- fixed coefficient;
- fixed tick interval;
- no stack/gauge/dynamic coefficient scaling;
- generation-token refresh invalidates stale queued ticks;
- default first tick after one interval;
- `tick_start: immediate` starts immediately;
- default expiry-boundary and immediate-expiry semantics mirror Moris.

Synthetic tests and a real Mana DoT parity fixture passed the Fast damage test stage before later core-probability work was layered on top.

Complex DoT remains fail-closed.

## 6. Current work: core probability / core-hit triggers

This is the active unfinished feature area.

### Why the old scalar is insufficient

The original static enemy model exposed:

```text
effective_core_rate = core_uptime × core_hit_rate_when_open
```

That is useful as a fallback, but Moris core-hit probability can depend on:

- weapon type;
- accuracy percentage;
- boss core size (`core_px`).

Therefore one common rate can introduce weapon-archetype ranking bias on core-heavy bosses.

### Moris model being mirrored

Moris currently uses weapon accuracy geometry roughly as:

```text
D = max(base_diameter - acc_slope * accuracy_pct, 1)
R = D / 2
r_core = core_px / 2
P_core = min(1, (r_core / R) ** model_n)
```

with parameters in `data/weapon_mechanics.json`.

Current WIP changes have begun to lower accuracy data into Fast compile/runtime state and add `accuracy_pct` into `DamageTerms`.

### Next implementation target

After current CI is green:

1. finish `EnemyStaticProfile`/weapon-specific core probability API;
2. verify Fast core probabilities numerically against Moris `_core_hit_prob()` for AR/SMG/SG/MG/SR/RL and accuracy modifiers;
3. feed that probability into normal-attack scoring instead of a squad-wide common scalar when `core_px` is supplied;
4. use expected fractional accumulation for `core_hit_count:N`;
5. only split/materialize at threshold crossings that can change future state;
6. add real parsed cases, including core-hit-driven damage/buff characters, and compare against Moris expected mode;
7. remeasure 180 s score cost.

Do not create one scheduler event per probabilistic core hit.

## 7. Explicit fail-closed / not-yet-certified areas

This list is intentionally conservative and should be updated as mechanics are certified.

- generic raw `hit_count` every-hit producer;
- expected `core_hit_count:N` runtime production (next feature);
- expected `crit_hit_count:N` production;
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

Historical measurements from this branch include:

- ~59.33 ms / 180 s five-person score near the last fully green broad-score checkpoint;
- 15.41 ms / 358 events in the latest red CI's structural-performance fixture.

Keep the CI regression gate conservative (currently much looser than these observed values). The production metric later should include calls/sec and end-to-end shortlist wall time, not just one microbenchmark.

## 9. Validation hierarchy before optimizer integration

### Primitive correctness

Synthetic tests for scheduler, targets, counts, DoT, damage formula, boundary order.

### Static Moris comparison

Under equivalent conditions compare:

- per-character damage;
- squad total;
- burst timing;
- shot/reload counts;
- important effect windows;
- trigger count/timing.

### Ranking validation — required before production pruning

This is the most important missing project gate.

Measure across real/local account samples without committing personal data:

- Moris Top-N recall inside Fast Top-K;
- pairwise ordering accuracy;
- false-negative/tail failure rate;
- bias by weapon class/mechanic/archetype;
- unsupported/fallback frequency;
- final five-team Moris score after Fast shortlist;
- Fast calls, Moris calls, wall time, peak memory.

Do not choose shortlist width by intuition.

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

Real account data used during development has been kept outside Git/File Library where applicable; Git tests should use synthetic/public/static fixtures.

### Moris calculator

Moris is the authority and should remain intact. Do not casually change `calculator/` merely to make Fast match. If one character disagrees, inspect unique mechanics/data first.

## 12. Files to read in a fresh session

Read in this order:

1. `docs/OPTIMIZER_PROJECT_STATE.md` — this file, current handoff;
2. `docs/FAST_ENGINE_ARCHITECTURE.md` — architecture/performance contract;
3. `fast_engine/research/LESSONS.md` — research lessons and anti-overfit rules;
4. current branch HEAD and latest CI logs;
5. active files for the next feature (`model.py`, `compiler.py`, `damage_state.py`, `score.py`, `weapon_events.py`, `dynamic_weapon.py`, relevant tests).

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
