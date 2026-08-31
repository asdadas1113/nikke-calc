# Fast Engine — greenfield architecture contract

Status: Phase 2 baseline. This document defines the production Fast Engine direction. The earlier Crown/Mast research engine was a controlled experiment only; its source/archive has been removed from Git and only reusable lessons remain in `fast_engine/research/LESSONS.md`.

## Objective

Fast Engine is a **high-throughput theoretical ranking engine**, not a detailed combat calculator.

Its output only needs enough consistency to answer:

> Under the same theoretical 180-second static-target assumptions, which squads are likely stronger and therefore deserve expensive Moris verification?

Moris remains the final damage authority.

## Priority order

1. throughput
2. Moris Top-N recall / low catastrophic false-negative rate
3. stable relative ordering across team archetypes
4. enough combat fidelity to preserve meaningful team synergies
5. absolute Fast-vs-Moris damage accuracy

A small absolute damage error is not a defect if ranking recall remains strong. A systematic error that removes a genuinely strong archetype from the shortlist is a defect even when mean absolute error is small.

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
  - calc_base_stats(char)          # compile-time reuse
  - char_effects(name, stage)      # favorite-stage selection reuse
  - parsed_nikke / parsed_skills   # source language
        ↓
immutable Fast IR / compiled squad
        ↓
independent Fast runtime
```

This keeps account growth, equipment, cube, collection/favorite, and variant-selection semantics compatible with Moris while leaving the expensive combat execution path independent.

Fast must not call Moris `timeline.simulate()` during a normal Fast evaluation.

## Time model

The fight horizon defaults to **180 seconds**. The timestep is **not fixed**.

Fast uses continuous-time event scheduling:

```text
current state
  → next meaningful boundary
  → aggregate unchanged interval
  → process boundary
  → repeat until 180 s
```

Meaningful boundaries include burst transitions, buff/state expiry, periodic effects, reload completion, weapon-mode changes, and shot/trigger thresholds that can change state.

There is no default 1/60-second loop. Frame granularity may be used only for a mechanic that demonstrably needs it and should be isolated to that mechanic rather than turning the whole engine into a frame simulator.

## Aggregation rule

If state relevant to damage/triggering is unchanged across an interval, repeated work may be collapsed.

Examples:

- `N` identical normal shots → one expected-damage calculation × `N`.
- expected crit/core counts may accumulate fractionally.
- if an every-30-hit trigger exists, split the interval only at the hit-count boundary rather than per bullet.
- identical DoT ticks may be batched until a state or trigger boundary interrupts them.

Accuracy is spent only where it protects ranking.

## Enemy model

Initial target is patternless and static:

- DEF
- element/code
- core expected exposure
- duration

```text
effective_core_rate = core_uptime × core_hit_rate_when_open
```

Core weighting must feed both expected core damage and core-hit-driven expected trigger progress where appropriate.

Initial exclusions: immunity windows, elemental timing windows, boss attacks, stun, cover destruction, movement, boss AI, and timed part-break chronology. Moris handles final boss-pattern verification.

## Runtime state budget

Production state should contain only values that can change future score/order. The initial contract allows:

- active states/buffs and expiries
- stack/counter/gauge values
- ammo/reload/charge/weapon mode
- burst stage/full-burst state/cooldowns
- character-owned HP/shield state
- hit/crit/core expected trigger progress
- last dealt damage when a later effect references it
- damage accumulators when an effect stores and releases dealt damage
- per-character and squad damage totals

Full hit histories and verbose logs are diagnostic-only opt-ins.

## State-version / cache invalidation model

Fast must not use one monolithic "state changed" flag for every hot-path cache. Runtime state is split into invalidation domains:

- effect/state (named buffs, stacks, gauges, counters)
- health (HP/shield)
- resource/cadence (ammo, weapon mode)
- damage memory (last dealt damage, delayed-damage accumulators)
- burst state

Each mutation increments only the relevant domain version, with actor-scoped versions in addition to global domain versions. This lets a future buff snapshot depend only on the actors/domains it actually reads. For example, updating `last_dealt_damage` must not invalidate an ATK/crit buff cache unless that cache explicitly depends on damage memory.

Named-state expiry uses generation tokens. Refreshing a state creates a new generation, so an old queued expiry becomes a cheap no-op instead of requiring deletion from the event heap.

## Damage semantics

`calculator.damage.calc_damage()` is not the whole combat model. It is the final single-hit DealForm after runtime state has already derived many values.

Before declaring broad runtime coverage, every Moris damage-affecting path must be classified as one of:

- **Hit formula** — coefficient, ATK/DEF, crit/core/full burst, charge, typed damage, received damage, element.
- **Derived state** — values derived from caster ATK/HP, ammo, gauge, etc. before damage is evaluated.
- **Damage event** — bonus/DoT/sequential/fixed/accumulated/released damage.
- **Cadence/timeline** — fire rate, ammo, reload, charge, burst and state timing.
- **Moris NOP** — not currently reflected by Moris authority.
- **Fast unsupported** — explicit Moris fallback/protected review until implemented.

Do not silently treat an unknown mechanism as zero.

## Character-name blindness

Runtime core must not know named characters.

Novel character behavior belongs in parsed/compiled effects or in a reusable generic primitive. A named special case is a last resort and should be capability-routed explicitly.

## Expected-value policy

Fast is deterministic by default. RNG noise is not useful for candidate ranking.

Expected-value treatment may be used for crit, core, hit-rate and repeated-proc behavior when it does not destroy the interaction being ranked. Expected counters may be fractional and only need to split execution when a threshold changes future state.

## Research-prototype policy

The controlled Crown/Mast prototype is no longer retained as source code or an archive inside this repository.

Only its general lessons are retained:

- event/buff/damage separation is useful;
- repeated buff resolution is expensive;
- unchanged spans should be aggregated;
- a score-only runtime can discard Moris UI/history detail;
- Crown/Maid Mast-specific roster/rotation assumptions must not leak into production abstractions.

See `fast_engine/research/LESSONS.md`. Production code must not depend on the removed prototype.

## Validation

Three gates precede production pruning:

1. **primitive correctness**: scheduler/state/damage primitives against synthetic or Moris-derived cases;
2. **static-squad comparison**: same 180-second static conditions, comparing total damage, per-character damage, burst timing, shot counts and major state windows;
3. **ranking recall**: Moris Top-N survival within widening Fast Top-K shortlists across real account/team samples.

The primary production metric is shortlist recall, not exact damage equality.

## Phase 2 build order

1. greenfield immutable compiled model + Moris compile boundary;
2. continuous-time stable scheduler;
3. damage-semantics inventory and capability manifest;
4. generic state/stack/counter/gauge store + expiry dispatch;
5. burst scheduler independent of character names;
6. weapon cadence/ammo/reload/charge interval model;
7. Fast damage kernel and derived-state resolver;
8. damage-event primitives and accumulators;
9. static enemy element/core integration;
10. 5-person score-only vertical slice;
11. Moris static-parity and ranking-recall harness;
12. optimizer integration only after recall is measured.

## Performance philosophy

Do not preserve detail merely because Moris has it. Every hot-path object, lookup and event must justify itself by ranking quality.

The initial milestone remains <= 1.0 s per 180-second 5-person squad, but this is a gate rather than a target ceiling. If interval aggregation can reach substantially lower latency without materially hurting recall, prefer the faster design.
