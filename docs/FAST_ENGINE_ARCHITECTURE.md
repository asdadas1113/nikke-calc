# Fast Engine — architecture contract

Status: Phase 2 active development. Canonical live state/checkpoint information is in `docs/OPTIMIZER_PROJECT_STATE.md`; this document defines the engineering contract.

## Objective

Fast Engine is a **high-throughput theoretical ranking engine**, not a detailed combat calculator.

Its job is to cheaply answer:

> Under the same theoretical 180-second static-target assumptions, which squads are likely stronger and therefore deserve expensive Moris verification?

Production intent:

```text
thousands of plausible squads
        ↓
Fast broad ranking
        ↓
wide/protected shortlist
        ↓
Moris authoritative re-score
        ↓
exact non-overlap 5-team allocation
```

Moris remains the final damage authority.

## Priority order

1. throughput;
2. Moris Top-N recall / low catastrophic false-negative rate;
3. stable pairwise ordering across team archetypes;
4. meaningful synergy preservation;
5. absolute Fast-vs-Moris damage accuracy.

A small common absolute error can be acceptable. A systematic weapon/mechanic-specific bias is not acceptable even if average error is small.

## Compatibility boundary

Do not duplicate account/build assembly.

```text
profile / account / overrides
        ↓
context.spec.build_squad(...)      # Moris-owned
        ↓
Moris character dicts
        ↓
Fast compile boundary
  - calc_base_stats(char)
  - active favorite-stage selection
  - parsed_nikke / parsed_skills / weapon mechanics
        ↓
immutable Fast IR
        ↓
independent Fast runtime
```

Fast must not call `timeline.simulate()` during a normal evaluation.

## Time model

The fight horizon defaults to 180 seconds and is treated as `[0, duration)`.

There is **no global 1/60 loop**.

```text
current state
  → next meaningful boundary
  → aggregate unchanged span
  → process boundary
  → repeat
```

Equal-time semantic phases mirror the relevant Moris ordering:

```text
state expiry
→ fixed periodic
→ burst transitions/effects
→ weapon/damage boundaries
```

Frame granularity may only be introduced for an isolated mechanic that demonstrably requires it. Do not turn the entire runtime into a frame simulator to erase harmless Moris quantization differences.

## Aggregation contract

The fundamental rule is:

> **If future-relevant state does not change, do not recalculate.**

Examples already used by the runtime:

- `N` identical normal shots → one DealForm evaluation × `N`;
- unchanged weapon spans → compressed shot blocks;
- count triggers → materialize only threshold crossings;
- raw `full_charge_hit` → only actors that actually consume it promote every charge shot;
- damage-state snapshots → actor/enemy scoped version cache;
- DoT → schedule actual meaningful ticks, not frames;
- stale expiry/DoT schedules → generation-token no-op instead of heap deletion.

A global per-shot or per-pellet scheduler is prohibited unless a mechanic truly changes state at every such hit and no equivalent aggregation exists.

## Weapon event semantics

Keep event families distinct.

Current Moris authority semantics include:

- generic `hit_count`: one per ordinary weapon trigger pull/shot;
- `pellet_hit`: one per pellet hit;
- `full_charge_hit`: one per full-charge release;
- `full_charge_count:N`: modulo threshold over full-charge hits.

Do not infer that SG `hit_count` equals pellet count. Fast previously made this mistake and it can materially over-trigger SG count effects.

## Runtime state / invalidation

Runtime state should contain only values that can change future ranking score.

Domains include:

- active effects/named states/stacks/counters/gauges;
- health/shield;
- ammo/resource/cadence;
- damage memory/accumulators;
- burst state.

Mutations increment actor/domain scoped versions. Hot caches should depend on the smallest relevant token rather than one global “state changed” flag.

`DamageTermResolver`, for example, caches an actor's numeric damage state and should not invalidate because an unrelated ally's ammo changed.

## Target/snapshot contract

Target selection is a mechanic, not a character special case.

Rank-based target cohorts should preserve Moris snapshot identity. Same caster + same activation time + same raw rank target should share the same selected cohort.

Position/adjacency, B3-only rank selection, burst-cast history, weapon/class/element targets should be reusable target primitives.

Do not encode “Rouge”, “Milk”, etc. into scheduler logic merely because those characters exposed the mechanic first.

## Damage semantics

Fast lowers Moris damage into three layers:

1. **compiled hit/event shape** — coefficient, hit type, multi-hit count, DoT/pending flags;
2. **cached derived numeric state** — `DamageTerms` such as ATK, crit, core, charge, received damage, element;
3. **branch-light expected-value DealForm** — reused across many identical shots/ticks.

Unknown derived states must block scoring if they can contaminate otherwise-supported hits.

Unsupported damage events may be reported explicitly in `FastScore.unsupported`, but comparison-critical state delivery must fail closed rather than return a biased subtotal.

## Expected-value policy

Fast is deterministic by default.

Expected-value treatment is preferred for repeated probabilistic mechanics when it preserves long-run ranking:

- crit damage;
- core damage;
- repeated probabilistic proc counters.

For count-triggered probabilistic events, use fractional accumulation and materialize only the threshold crossing that changes state.

Do not use RNG noise for candidate ranking.

## Core model

Core handling is being upgraded from a squad-wide scalar to a weapon-aware model.

Fallback static model:

```text
effective_core_rate = core_uptime × core_hit_rate_when_open
```

When `core_px` is available, mirror Moris weapon accuracy geometry:

```text
D = max(base_diameter - acc_slope × accuracy_pct, 1)
R = D / 2
r_core = core_px / 2
P_core = min(1, (r_core / R) ^ model_n)
```

Weapon parameters come from `data/weapon_mechanics.json`.

Design requirement:

- compute probability from cached state, not per bullet;
- normal-shot blocks reuse it while accuracy/core state is unchanged;
- `core_hit_count:N` later consumes expected fractional progress and only emits threshold crossings.

This is comparison-critical because AR/SMG/SG/MG/SR/RL can have very different core probabilities on the same boss.

## Damage events

Currently certified/partially certified generic event families include:

- simple immediate damage;
- safe B3 pending `bonus_damage` slice;
- fixed-tick DoT slice;
- compressed normal attacks.

### B3 pending contract

Only exact `stat == "bonus_damage"` uses the certified delayed B3 path. `bonus_damage:N` is immediate multi-hit.

Pending damage is evaluated after Full Burst start buffs settle. Complex source-order masks remain fail closed until explicitly represented.

### Fixed DoT contract

Initial DoT support is intentionally narrow:

- fixed coefficient;
- fixed tick interval;
- fixed lifetime;
- no dynamic stack/gauge coefficient scaling;
- no same-target ramp;
- no `dmg_scale_mag_pct` style dynamic magnification.

Refresh uses generation tokens. Moris immediate/default first-tick and expiry-boundary behavior must be preserved.

## Character-name blindness and anomaly diagnosis

Runtime core must not know named characters.

When one character diverges, do not immediately change shared code.

Diagnosis hierarchy:

```text
many characters fail similarly → common runtime/formula
one mechanic cohort fails       → mechanic module
one character fails             → character data/unique mechanic first
```

Only after confirming a truly unique rule should a character-specific exception be considered.

## Static enemy model

Initial Fast target intentionally excludes detailed boss chronology.

Inputs may include:

- DEF;
- element/code;
- core exposure/core size;
- duration.

Initial exclusions:

- immunity windows;
- element-restriction time scripts;
- boss attacks/incoming-damage chronology;
- stun;
- cover destruction;
- movement;
- timed part-break chronology;
- boss AI.

These remain Moris final-validation concerns unless a specific static approximation proves necessary for shortlist recall.

## Performance contract

Fast exists to make **thousands of candidate scores practical**.

Rules:

- no global frame loop;
- no global per-shot objects;
- no per-pellet scheduler for SG;
- only actors with raw-event consumers get raw boundaries;
- state-version caches must survive unrelated mutations;
- batch identical shot/tick damage;
- prefer threshold-crossing event counts to total hit counts.

Initial milestone was <=1 s per 180 s five-person squad. Actual branch measurements are far below that, but benchmark fixtures differ, so optimize trends rather than worship one number.

Keep a CI wall-clock regression gate and structural event-count tests.

## Validation gates before production pruning

### 1. Primitive correctness

Synthetic/Moris-derived tests for:

- scheduler phase ordering;
- target snapshots;
- cadence/count semantics;
- damage layers;
- DoT/pending boundaries;
- expected probabilistic thresholds.

### 2. Static Moris comparison

Compare under equivalent static conditions:

- squad/per-character damage;
- burst timing;
- shot/reload counts;
- major buff windows;
- trigger activation count/timing.

### 3. Ranking recall

Required before Fast is allowed to prune production candidates:

- Moris Top-N recall within Fast Top-K;
- pairwise ordering;
- false-negative/tail rate;
- archetype/weapon/mechanic bias;
- unsupported frequency;
- final 5-team Moris score after shortlist;
- wall time and memory.

Shortlist width must be measured, not guessed.

## Current build direction

The broad build order remains:

1. compiled model/input boundary — established;
2. event scheduler/state/effects — established;
3. burst runtime — established for major generic paths;
4. weapon cadence/count boundaries — substantial coverage;
5. damage kernel/state resolver — established;
6. normal + simple skill score vertical slice — established;
7. B3 pending + selective raw charge + fixed DoT — implemented slices;
8. weapon-aware core probability — **active WIP**;
9. expected `core_hit_count:N` / `crit_hit_count:N` thresholds;
10. widen dynamic cadence/derived-stat coverage;
11. real-account/local ranking-recall harness;
12. optimizer integration and heuristic reset audit.

See `docs/OPTIMIZER_PROJECT_STATE.md` for exact HEAD, CI blockers and next actions.
