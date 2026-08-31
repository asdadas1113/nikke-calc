# Roster Optimizer / Fast Engine — Current Project State

> **Canonical status document.**
>
> This file records the current architecture decisions, validated findings, known limitations, and next steps for the roster optimizer project. Older optimizer documents remain useful as experiment history, but when they conflict with this file, **this file describes the current direction**.
>
> Last consolidated: **2026-09-01**.

## 1. Project goal

Given an account roster/build, discover five non-overlapping Solo Raid teams with high total damage without attempting to brute-force every possible five-person squad through the full Moris simulator.

The project has two separate problems:

1. **Candidate discovery:** find promising squads from a large owned roster.
2. **Authoritative evaluation/allocation:** score promising squads accurately, then choose the best five non-overlapping teams from the evaluated pool.

The second problem is already well defined: Moris remains the authoritative combat evaluator, and exact weighted set packing/global allocation is used over the evaluated candidate pool. The current development focus is reducing the cost and variance of the first problem.

## 2. Current architecture decision

### Moris is the authority, not the search engine

Moris remains the reference engine for detailed combat semantics and final damage validation.

- Do **not** replace Moris as the final damage authority.
- Do **not** require Moris upstream to accept optimizer-specific engine changes.
- Do **not** make project success depend on deep Moris runtime modifications.
- Moris data/formulas may be reused where practical.
- Unsupported or uncertain Fast Engine behavior must fail over to Moris rather than silently approximating.

Moris is intentionally a detailed simulator. Its normal UI can expose the full 180-second timeline, hit history, buffs, ammo/reload flow, and damage breakdown. The optimizer should not require that full UI-oriented runtime path for every broad-search candidate.

### Build a separate Fast Engine for broad screening

The current preferred architecture is:

```text
account roster/build
        ↓
cheap structural/meta candidate generation
        ↓
Fast Engine — broad static-target screening
        ↓
wide shortlist + diversity/restoration candidates
        ↓
Moris — authoritative re-evaluation
        ↓
exact global five-team allocation over Moris-scored pool
```

The Fast Engine is **not** intended to become a second user-facing Moris calculator. Its job is to score/rank many candidate squads cheaply enough that Moris calls can be concentrated on promising or uncertain teams.

## 3. Fast Engine combat model

### Static 180-second dummy target

The Fast Engine should model character/team interactions over a 180-second fight while deliberately removing boss-pattern time-axis complexity.

Initial static enemy inputs:

- enemy DEF
- enemy element/code
- core availability as a scalar expected exposure

Initially excluded from Fast Engine boss modeling:

- immune/invulnerable windows
- element-restriction windows
- boss attacks and incoming-damage timeline
- stun/cover/destruction/movement patterns
- timed part-break scripts
- boss AI or pattern sequencing

These remain Moris/final-validation concerns.

### Element

Element is a normal static enemy property and should be applied directly using the same advantage semantics/data used by Moris where possible.

### Core

Core timing is intentionally collapsed from a timeline into an expected scalar.

Recommended representation:

```text
effective_core_rate = core_uptime × core_hit_rate_when_open
```

The first implementation may expose only `core_uptime` and assume `core_hit_rate_when_open = 1.0`; the internal representation should still allow the two values to be separated later.

The scalar must affect more than the displayed core damage bonus. Where the character DSL contains core-hit-driven effects, expected core-hit counts/triggers should receive the same weighted core exposure rather than pretending every hit is either always core or never core.

This is an intentional search proxy for the static target. Exact boss timing remains a Moris responsibility.

### RNG

Fast screening should use deterministic expected-value behavior. Random-seed variance is not useful for broad candidate ranking.

## 4. Moris data as the source language

The Fast Engine should not require hand-writing a separate implementation for every character.

Preferred design:

```text
Moris parsed character/skill data
            ↓
       Fast compiler
            ↓
      Fast intermediate representation (IR)
            ↓
       Fast runtime
```

Support is tracked primarily by reusable mechanics/opcodes — trigger, target, condition, stat/effect, state machine — rather than by character name.

A new character should become Fast-compatible automatically when its parsed Moris effects use already-supported primitives. Truly novel mechanics may require one new generic handler or, for rare character-specific mechanics, Moris fallback.

Unknown mechanics must never be silently treated as zero or as a guessed approximation.

## 5. Phase 1 feasibility findings

A local feasibility prototype was built against the analyzed Moris parsed-skill snapshot. **This prototype is not yet committed to this repository.** Its purpose was to decide whether a generic Moris-DSL Fast Engine is viable before investing in a runtime.

Exploratory findings:

- analyzed snapshot: **202 parsed-skill character keys / 1,799 effects**;
- this 202-key inventory is not the same metric as the currently selectable UI roster count (README currently reports 199 supported/selectable characters);
- all observed trigger forms could be grouped into a small set of generic trigger families;
- no separate custom timing family was required by the inventory pass;
- observed conditions were structurally representable as parameterized generic families;
- name-based custom events were generated through common event semantics rather than requiring one hard-coded dispatcher per event name;
- the only effect classified as a true initial character-specific D/fallback case in that pass was `feather_refresh` on Ein (2 effects).

Recent public Solo Raid weighting was also checked as a feasibility signal. In the analyzed S33–S40 dataset, Ein appeared in about **2.44%** of teams, so a Moris fallback for that initial special case would not by itself destroy the hybrid architecture.

These figures are **structural feasibility measurements, not implementation-complete coverage**. A character is not Fast-exact until every required generic subsystem is actually implemented and parity-tested.

## 6. Fast Runtime must start with real generic subsystems

The feasibility pass also showed that implementing only easy ATK/damage buffs first would not produce useful full-team coverage. Recent raid teams commonly depend on C-level stateful mechanics.

The minimum useful Fast Runtime therefore needs the following common core early:

1. event/burst timeline
2. named state, stack, counter, and gauge handling
3. arithmetic buff/debuff operations and target resolution
4. HP/shield state needed by character-owned mechanics
5. damage/additional-damage processing
6. weapon/ammo/charge/reload runtime as required by the parsed effects
7. Moris fallback when any required primitive is unsupported

Boss-caused HP loss is outside the initial static-target model. Character-generated HP/shield changes that affect character mechanics remain part of the runtime.

## 7. Fast vs Moris scoring policy

### During broad search

Fast scores are allowed to rank and screen candidates.

### Before final allocation

Shortlisted candidates must be re-evaluated by Moris. The final candidate pool should use Moris scores for the exact five-team allocation.

This avoids a systematic Fast/Moris scoring bias directly deciding the final answer.

### Candidate recall is more important than absolute Fast damage error

The key Fast Engine quality metric is not only `|Fast damage - Moris damage|`.

The more important question is:

> Of the squads Moris would rank highly, how many survive the Fast shortlist?

Therefore validation should emphasize:

- Moris Top-N recall within Fast Top-K
- final five-team damage after Moris re-evaluation
- per-account/tail failures, not only average performance
- composition diversity lost by screening
- unsupported/fallback frequency
- Fast calls, Moris calls, and wall time

The shortlist should be conservative and diversity-preserving. Fast Top-K alone is not sufficient if it removes structurally different teams that Moris would promote under a real boss.

## 8. Relationship to Meta / Cold search policy

Meta, Cold pools, Priority Review, structural restoration, and investment evidence remain **search-priority tools only**.

They do not change Moris damage.

Earlier transfer work showed two important facts:

1. context/reference instability can create large false Pure-vs-Meta differences;
2. an overly narrow Cold exploration quota can miss useful low-usage fillers or niche characters.

As Fast Engine coverage improves, the project should rely less on aggressive meta pruning because broad cheap squad evaluation becomes more affordable. Meta remains useful for prioritization, fallback, and diversity restoration, but should not be treated as a damage oracle.

## 9. Existing optimizer status on GitHub

Active experimental branch at the start of this consolidation:

`optimizer-debug-localized-ambiguity-20260831`

Pre-documentation HEAD:

`33236352cdaf0a46d8b8b5a4009d4df1bce5d612`

That branch already contains, among other optimizer work:

- bounded Meta input/parser work;
- production auto Worker/Enikk runner support;
- transfer/benchmark harnesses;
- batch-evaluation boundaries;
- score-blind marginal reference coverage fixes;
- exact evaluated-pool global five-team allocation.

`master` must remain untouched by optimizer experiment work unless a separately reviewed change is explicitly intended for the main calculator.

### Local work not represented by that HEAD

At the time of this document, additional correctness work had been validated locally but was not yet represented by the above GitHub HEAD:

- stable marginal assignment context between Pure and Meta;
- shared Pure/Meta reference-team context with candidate-admission separation;
- local optimizer suite reached 372 passing tests after those changes.

Do not assume those local changes exist in a fresh checkout until they are explicitly committed/pushed.

## 10. Why the direction changed toward Fast Engine

The original optimizer plan attempted to save expensive Moris calls mainly through search heuristics and Meta/Cold prioritization.

Measured baseline Moris cost is substantial: an existing benchmark on GitHub Actions measured a representative 180-second `simulate(verbose=False)` call at about **2.675 s**. Object construction was negligible compared with simulation.

Large rosters make a fixed ~240-call budget especially restrictive because marginal/reference probing can consume a large fraction of the budget before many complete squad candidates are evaluated. This raises the possibility that even the Pure 240-call baseline is not fully converged on large accounts.

A separate controlled Crown/Mast research engine was then inspected as a possible high-speed prototype. Exploratory local profiling found:

- original controlled 180-second run: roughly **1.6 s**;
- a simple buff-timeline lookup/cache prototype reduced that controlled case to roughly **0.75–0.82 s** without changing the measured result beyond floating-point noise;
- the engine architecture already separates event/buff/damage concepts more naturally for a score-oriented runtime than the full Moris UI simulator.

These measurements do not prove the eventual generic Fast Engine will run at 0.8 s, but they show enough headroom to justify the separate-runtime approach.

## 11. Moris engine optimization status

Deep Moris optimization is **not the current dependency** for the optimizer plan.

Safe internal Moris optimizations that preserve every observable timeline result may still be valuable upstream, but whether the original maintainer accepts such changes is outside this project's control.

Therefore:

- leave the detailed Moris engine as the authoritative path;
- do not make optimizer completion depend on upstream acceptance;
- keep any future Moris performance proposal independently justified and fully behavior-preserving;
- put aggressive score-only/event-driven design work in the separate Fast Engine instead.

## 12. Roadmap from here

### Phase 1 — feasibility inventory

**Status: completed locally as a prototype.**

- inventory Moris effect/trigger/target/condition forms;
- define Fast IR categories;
- identify generic vs special fallback mechanics;
- verify that per-character hand implementation is not required for the majority of the roster.

### Phase 2 — minimum generic Fast Runtime

**Next implementation phase.**

Build a separate runtime around the Moris-derived IR:

1. deterministic 180-second static-target event/burst scheduler;
2. state/stack/counter/gauge subsystem;
3. target resolver and arithmetic buff subsystem;
4. character-owned HP/shield subsystem;
5. weapon/ammo/charge/reload behavior needed by supported effects;
6. damage/additional-damage execution, reusing Moris formulas/data where practical;
7. static enemy profile: DEF, element, core expected exposure;
8. exact capability router: Fast only when every required primitive is supported, otherwise Moris.

### Phase 3 — parity and correctness harness

Before using Fast ranking for real pruning:

- synthetic primitive-by-primitive parity tests;
- real five-person squad comparisons under equivalent static conditions;
- compare squad/character damage, shot counts, burst timing, state transitions, and major buff windows in debug mode;
- core-off and full-core endpoint tests plus explicit tests for weighted expected-core behavior;
- never promote an unsupported or unexplained mismatch to Exact.

Fast is allowed to intentionally differ from a pattern-aware Moris run because boss patterns are excluded by design. Parity comparisons must use equivalent static conditions.

### Phase 4 — ranking/recall validation

Use public Enikk data and anonymous transfer accounts to measure:

- Moris Top-N recall at increasing Fast shortlist widths;
- final five-team damage after all shortlist candidates are Moris-rescored;
- large-roster and low-investment/high-investment tail behavior;
- special/fallback frequency;
- candidate diversity;
- runtime and Moris calls saved.

Do not choose a production shortlist width before these measurements.

### Phase 5 — hybrid optimizer integration

Target pipeline:

```text
structural candidate generation
        ↓
Fast bulk scoring
        ↓
Fast top band
+ diversity band
+ Priority/Meta/Cold restoration
+ unsupported/pattern-sensitive Moris candidates
        ↓
Moris authoritative scoring
        ↓
exact five-team allocation
        ↓
optional Moris refinement/replacement rounds
```

### Phase 6 — performance engineering

Only after correctness/recall are acceptable:

- compiled buff-state intervals;
- score-only object path inside Fast Engine;
- event scheduling improvements;
- batch evaluation;
- browser/worker parallelism;
- cache/reuse across structurally related squad evaluations where identity is proven safe.

## 13. Project invariants / handoff rules

A new work session should preserve these rules:

1. **Never merge optimizer experiments into `master` implicitly.**
2. **Moris remains final damage authority.**
3. **Fast Engine is a high-recall static-target screening engine, not a full boss simulator.**
4. **Enemy DEF and element are static Fast inputs.**
5. **Core is represented initially by expected exposure (`uptime × hit rate when open`), not by a boss timing script.**
6. **Unknown Fast mechanics fail over to Moris; never silently approximate them as zero.**
7. **Meta/Cold/investment signals affect search attention only, never damage.**
8. **Final five-team allocation uses Moris-scored candidates and exact no-overlap set packing.**
9. **Evaluate tail failures and candidate recall, not only mean score.**
10. **Distinguish committed GitHub state from local experimental artifacts.**

## 14. Historical documents

The following files remain useful research records but may contain decisions that predate this architecture:

- `docs/roster-optimizer-prototype.md`
- `docs/optimizer-performance-deferred.md`
- `docs/meta-guided-cold-pool.md`
- `docs/search-budget-study.md`
- `docs/placement-order-study.md`
- `docs/BENCHMARK.md`
- `docs/DEVLOG.md`

Use them for experiment detail and provenance. Use **this file** for the current project direction.
