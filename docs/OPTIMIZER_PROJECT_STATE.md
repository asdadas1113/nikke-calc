# Roster Optimizer / Fast Engine — Current Project State

> **Canonical project handoff.** Read this file first when continuing optimizer/Fast Engine work. Older optimizer documents are experiment history; when they conflict with this file, this file is the current direction.
>
> Last consolidated: **2026-09-01**.

## 1. Goal

Given a NIKKE account roster/build, discover five strong non-overlapping Solo Raid teams without brute-forcing every five-person squad through the full Moris simulator.

The project separates two jobs:

1. **Candidate discovery/ranking:** examine enough squads that strong combinations are unlikely to be missed.
2. **Authoritative scoring/allocation:** Moris scores the shortlisted squads, then exact no-overlap set packing chooses the best five teams inside the Moris-scored pool.

The current bottleneck is candidate discovery throughput, not the final allocation solver.

## 2. Current architecture

```text
account roster/build
        ↓
structural candidate generation
        ↓
Fast Engine — broad 180 s theoretical ranking
        ↓
wide shortlist + diversity/protected candidates
        ↓
Moris — authoritative scoring / boss-specific validation
        ↓
exact global five-team allocation
        ↓
optional Moris refinement/replacement
```

### Moris

Moris remains the final damage authority.

- Keep the detailed Moris calculator intact for final evaluation.
- Do not make optimizer completion depend on upstream acceptance of deep Moris performance changes.
- Moris data/formulas may be reused by Fast where useful.
- Fast scores do not directly decide the final five teams.

### Fast Engine

Fast is **not a second detailed calculator**. It is an optimizer-only theoretical comparison engine whose primary question is:

> Under a common 180-second static-target model, which squads are likely to be stronger than which others?

Absolute numerical parity with Moris is not the goal.

## 3. Fast Engine contract

The following rules are deliberate design constraints.

### 3.1 Keep the 180-second time basis

Fast must preserve enough internal time structure to distinguish important team interactions:

- burst/full-burst cycles and buff overlap
- named states, stacks, counters, gauges
- ammo/reload/charge/weapon cadence where ranking depends on them
- character-owned HP/shield interactions
- damage/additional-damage timing

Do **not** collapse the engine to a simple `DPS × 180` formula if that destroys team-synergy ordering.

### 3.2 Approximation is allowed

Fast is explicitly allowed to trade fine-grained simulation detail for throughput.

Possible techniques include:

- event aggregation
- event-driven scheduling rather than frame-by-frame work
- compiled effect/timeline plans
- score-only production state
- cached/condensed state
- expected-value treatment of probabilistic effects
- averaged external enemy properties
- other approximations that materially improve throughput

The acceptance criterion is ranking usefulness, not byte-for-byte Moris behavior.

### 3.3 Ranking recall matters more than absolute damage error

Validation priority:

1. Moris Top-N recall within Fast Top-K
2. catastrophic miss/tail failure rate
3. systematic bias by weapon/mechanic/team archetype
4. wall-clock throughput
5. absolute Fast-vs-Moris damage error

False negatives are especially expensive: a weak squad ranked too high can be removed by Moris, but a strong squad discarded by Fast cannot be recovered.

### 3.4 Moris parsed data is the source language

Prefer:

```text
Moris parsed skills/data
        ↓
Fast compiler
        ↓
Fast IR
        ↓
Fast runtime
```

Support should be implemented mainly as reusable trigger/condition/target/effect/state primitives, not 200 hand-written character ports.

Unknown mechanics must be explicit. If an approximation has not been justified for ranking, route the squad to Moris or protect it from pruning; never silently treat an unknown effect as zero.

## 4. Static enemy model

Fast uses a **patternless 180-second target**.

Static inputs to support:

- enemy DEF
- enemy element/code
- expected core exposure

### Element

Element is a normal static property and should use Moris/game semantics where practical.

### Core

Exact core-open timing is intentionally discarded. Use an expected exposure scalar:

```text
effective_core_rate = core_uptime × core_hit_rate_when_open
```

The initial external interface may expose only `core_uptime` and assume `core_hit_rate_when_open = 1.0`.

The effective rate should affect not only core bonus damage but also expected core-hit-driven triggers/counts where relevant.

### Initially excluded boss behavior

- invulnerable/immune timing windows
- element-restriction timing windows
- boss attacks/incoming-damage scripts
- stun/cover destruction/movement
- timed part-break scripts
- boss AI/pattern sequencing

Those belong to Moris final/boss-specific validation.

## 5. Why Fast is now the main development axis

A representative 180-second Moris `simulate(verbose=False)` benchmark on GitHub Actions was about **2.675 s per squad**. On large 150–190 character rosters, a ~240-call budget is so small that marginal/reference probing can consume most of the budget before enough complete squads are tested.

That creates two risks:

1. even the Pure baseline may be underexplored;
2. Meta/Cold/reference heuristics can be tuned to the artificial scarcity of a 240-call environment rather than to the real squad-selection problem.

A controlled Crown/Mast research engine was also profiled locally. A representative run was roughly 1.6 s, and a simple buff-timeline lookup/cache experiment reduced that controlled case to roughly 0.75–0.82 s. This does not predict production Fast speed, but it supports the feasibility of a separate score-oriented runtime.

Therefore the optimizer policy is temporarily treated as a **frozen baseline** while Fast increases the available evaluation volume.

## 6. Algorithm reset audit after Fast

Once Fast can evaluate substantially more squads, do not assume the current search heuristics remain desirable.

Re-evaluate them under the higher-compute environment:

1. build a much stronger Pure baseline;
2. rerun existing Meta/Cold policies without retuning first;
3. perform ablations: remove Meta, Cold, marginal/reference heuristics, investment tie-breaks, refinement, etc.;
4. delete or simplify heuristics whose apparent benefit disappears when evaluation scarcity is reduced;
5. retain only mechanisms that still protect score/recall or tail behavior.

The goal is to avoid preserving algorithms that were only compensating for an unrealistically tiny Moris call budget.

## 7. Phase 1 feasibility result

The committed Phase 1 prototype lives at:

`fast_engine/prototype_phase1/`

It is a compiler/inventory/router prototype, **not a damage runtime**.

Analyzed Moris snapshot:

- 202 parsed-skill character keys
- 1,799 effects
- 170 distinct stat strings
- about 110 target expressions

Structural readiness inventory:

- N: 159 effects — Moris itself NOP/unimplemented for score parity
- A: 515 — existing/simple core primitive
- B: 304 — straightforward generic primitive
- C: 819 — reusable stateful subsystem
- D: 2 — current special/fallback surface

The two D effects were Ain `feather_refresh` effects.

All observed trigger/condition forms could be grouped into generic families in this pass. Named custom events also followed common event semantics rather than requiring one dispatcher per event name.

Recent public S33–S40 weighting found Ain in about 2.44% of teams, so an initial Moris fallback for that special mechanism does not by itself invalidate the hybrid design.

**Important:** structural expressibility is not runtime support. A/B-only support covers essentially no realistic recent top team; stateful C subsystems are nearly universal.

The portable committed routing tests currently cover five safety cases and passed before import.

## 8. Phase 2 runtime priority

Build a real vertical slice that can execute one five-person team from Moris-derived data to a 180-second Fast squad score.

Recommended order:

1. chronological event/burst scheduler
2. named state / stack / counter / gauge store and event broadcasting
3. target resolver + arithmetic buff/debuff operations
4. weapon cadence / ammo / reload / charge runtime needed for ranking
5. character-owned HP/shield state
6. damage/additional-damage path, reusing Moris formulas/data where useful
7. static enemy DEF/element/core model
8. capability/fallback routing
9. debug trace for mismatch diagnosis; score-only production path

The first nominal performance gate is **<= 1.0 s per 180-second five-person squad**, with 0.5–0.7 s as an initial practical target. Faster approximations are acceptable if Top-K recall remains strong.

## 9. Research-engine reference snapshot

The user-provided Crown/Mast controlled research engine is preserved separately at:

`fast_engine/research/crown_mast_reference/`

It is a sanitized architecture reference, not the production Fast runtime. Anonymous account material, the separate research-document bundle, caches, and unrelated generated artifacts were excluded before import. The README in that directory contains reconstruction and SHA-256 verification instructions.

Do not judge or refactor the research engine as though it were intended to be a general-purpose NIKKE simulator; it was built for a controlled Crown/Mast research task.

## 10. Git / branch state

Main calculator baseline:

`master`

Optimizer experiments must **not** be implicitly merged into `master`.

Previous optimizer line:

`optimizer-debug-localized-ambiguity-20260831`

Current Fast development line:

`fast-engine-phase2-20260901`

This Fast branch was forked from optimizer documentation HEAD:

`da67a1cf40cb281c66abcd85414a56ece00c5985`

The current Fast branch contains the Phase 1 prototype and sanitized research-engine reference alongside the existing optimizer work inherited from that parent.

### Still local / not represented by the inherited optimizer code

Additional optimizer correctness changes previously validated locally were not part of the inherited Git HEAD:

- stable marginal assignment context between Pure and Meta
- shared Pure/Meta reference-team context with candidate-admission separation
- local optimizer suite reached 372 passing tests after those changes

Do not assume those fixes exist in a fresh checkout unless they are separately committed.

## 11. Existing optimizer principles that remain valid

- Moris is the final score authority.
- exact weighted set packing/global allocation is used over the evaluated Moris candidate pool.
- Meta/Cold/investment evidence affects search attention only, never damage.
- Cold filtering is reversible rather than hard legality.
- tail failures and paired-account outcomes matter more than headline averages.
- anonymous account/profile samples remain local and must not be committed.

## 12. Next validation after minimum runtime

Before Fast is allowed to prune production candidates, compare equivalent static conditions against Moris and diagnose discrepancies with debug traces.

Then measure on public/anonymous test cohorts:

- Moris Top-N recall at increasing Fast shortlist widths
- final five-team Moris score after Fast shortlist + Moris re-score
- archetype-specific bias
- fallback/unsupported frequency
- candidate diversity
- large-roster tail failures
- Fast calls, Moris calls, wall time, and peak memory

Do not select a production shortlist width from intuition.

## 13. Handoff invariants

1. Never merge optimizer/Fast experiments into `master` implicitly.
2. Moris remains final damage authority.
3. Fast is a 180-second theoretical ranking engine, not a detailed boss simulator.
4. Fast numerical parity with Moris is not required; ranking recall is the primary quality target.
5. Aggressive optimization/approximation is allowed when recall remains acceptable.
6. Keep internal character/team timing where it materially affects synergy ordering.
7. Enemy DEF/element are static Fast inputs; core uses expected exposure.
8. Boss pattern time scripts stay out of the initial Fast model.
9. Unknown/unjustified mechanics must not silently become zero.
10. After Fast increases compute, re-audit and ablate the existing optimizer heuristics for scarcity-era overfitting.
11. Distinguish committed Git state from local experimental artifacts.
12. Never commit anonymous account/profile data.

## 14. Historical research docs

Useful experiment history includes:

- `docs/roster-optimizer-prototype.md`
- `docs/optimizer-performance-deferred.md`
- `docs/meta-guided-cold-pool.md`
- `docs/search-budget-study.md`
- `docs/placement-order-study.md`
- `docs/BENCHMARK.md`
- `docs/DEVLOG.md`

Use those for provenance and individual experiments. Use **this file** for current direction.
