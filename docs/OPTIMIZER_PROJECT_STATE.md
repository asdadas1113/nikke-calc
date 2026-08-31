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
- Moris data/formulas may be reused by Fast where useful.
- Fast scores do not directly decide the final five teams.
- Do not require deep Moris performance rewrites before the optimizer can progress.

### Fast Engine

Fast is **not a second detailed calculator**. It is an optimizer-only theoretical comparison engine whose primary question is:

> Under a common 180-second static-target model, which squads are likely to be stronger than which others?

Absolute numerical parity with Moris is not the goal.

## 3. Fast Engine contract

### 3.1 180-second horizon, not a 60 FPS loop

Fast preserves enough internal time structure to distinguish important team interactions:

- burst/full-burst cycles and buff overlap
- named states, stacks, counters, gauges
- ammo/reload/charge/weapon cadence where ranking depends on them
- character-owned HP/shield interactions
- damage/additional-damage timing

The runtime should advance between meaningful boundaries and aggregate unchanged intervals. Do not collapse the whole engine to `DPS × 180`, but also do not inherit Moris's global 1/60-second stepping unless a specific mechanic genuinely requires frame granularity.

### 3.2 Approximation is allowed

Fast is explicitly allowed to trade fine-grained simulation detail for throughput.

Allowed techniques include event aggregation, compiled effect/timeline plans, score-only state, cached/condensed state, expected-value treatment of probabilistic effects, interval integration, and averaged external enemy properties.

The acceptance criterion is ranking usefulness, not byte-for-byte Moris behavior.

### 3.3 Ranking recall matters more than absolute damage error

Validation priority:

1. Moris Top-N recall within Fast Top-K
2. catastrophic miss/tail failure rate
3. systematic bias by weapon/mechanic/team archetype
4. wall-clock throughput
5. absolute Fast-vs-Moris damage error

False negatives are especially expensive: a weak squad ranked too high can be removed by Moris, but a strong squad discarded by Fast cannot be recovered.

### 3.4 Moris owns input/build semantics

Prefer:

```text
profile / account / overrides
        ↓
context.spec.build_squad(...)
        ↓
Moris character dicts
        ↓
Fast compile boundary
        ↓
Fast IR
        ↓
independent Fast runtime
```

Reuse Moris `calc_base_stats()`, active favorite-stage selection, and parsed data semantics where practical. Fast must not call `timeline.simulate()` during a normal Fast evaluation.

### 3.5 Generic mechanics, explicit fallback

Support should be implemented mainly as reusable trigger/condition/target/effect/state primitives, not hand-written ports for every character.

Unknown mechanics must be explicit. If an approximation has not been justified for ranking, route the squad to Moris or protect it from pruning; never silently treat an unknown effect as zero.

The runtime core should be character-name blind.

## 4. Static enemy model

Fast uses a **patternless 180-second target** with static raid-relevant properties:

- enemy DEF
- enemy element/code
- expected core exposure
- duration

Core uses an expected scalar:

```text
effective_core_rate = core_uptime × core_hit_rate_when_open
```

The effective rate should affect both expected core bonus damage and core-hit-driven expected trigger progress where relevant.

Initially excluded boss behavior:

- invulnerable/immune timing windows
- element-restriction timing windows
- boss attacks/incoming-damage scripts
- stun/cover destruction/movement
- timed part-break scripts
- boss AI/pattern sequencing

Those belong to Moris final/boss-specific validation.

## 5. Why Fast is the main development axis

A representative 180-second Moris `simulate(verbose=False)` benchmark was about 2.7 s per squad. On large 150–190 character rosters, a roughly 240-call Moris budget is too small to establish a strong exploration baseline; marginal/reference probing can consume most of the budget before enough full squads are tested.

That risks tuning Meta/Cold/reference heuristics to evaluation scarcity rather than to the real squad-selection problem.

A controlled Crown/Mast research prototype previously demonstrated two useful facts: a lighter score-oriented runtime can be much faster, and repeated buff resolution is a major optimization target. The prototype was intentionally narrow and contained Crown/Maid Mast-specific roster/rotation assumptions, so the production Fast runtime is greenfield instead of a generalization of that code.

**The research prototype source/archive has now been removed from Git.** Only its reusable lessons remain in `fast_engine/research/LESSONS.md`.

The optimizer policy should therefore remain a frozen baseline until Fast increases the evaluation volume enough for a proper algorithm reset audit.

## 6. Algorithm reset audit after Fast

Once Fast can evaluate substantially more squads:

1. build a much stronger Pure baseline;
2. rerun existing Meta/Cold policies without retuning first;
3. ablate Meta, Cold, marginal/reference heuristics, investment tie-breaks, refinement, etc.;
4. delete or simplify heuristics whose apparent benefit disappears when evaluation scarcity is reduced;
5. retain only mechanisms that still protect score/recall or tail behavior.

The goal is to avoid preserving scarcity-era overfitting.

## 7. Phase 1 feasibility result

The committed Phase 1 prototype lives at:

`fast_engine/prototype_phase1/`

It is a compiler/inventory/router prototype, **not a damage runtime** and is separate from the removed user research prototype.

Analyzed Moris snapshot:

- 202 parsed-skill character keys
- 1,799 effects
- 170 distinct stat strings
- about 110 target expressions

Structural analysis showed that nearly all current characters can be represented by shared generic subsystems; actual runtime support still requires those subsystems to be implemented and certified. Unknown/unsupported cases must route explicitly.

## 8. Phase 2 greenfield runtime

Production Fast code lives under `fast_engine/engine/` with tests under `fast_engine/tests/`.

The intended build order is:

1. immutable compiled model + Moris compile boundary
2. continuous-time deterministic scheduler
3. damage-semantics inventory + capability manifest
4. generic state/stack/counter/gauge store + expiry dispatch
5. character-name-blind burst scheduler
6. weapon cadence/ammo/reload/charge interval model
7. Fast damage kernel + derived-state resolver
8. damage-event primitives and accumulators
9. static enemy element/core integration
10. complete five-person score-only vertical slice
11. Moris static-comparison and ranking-recall harness
12. optimizer integration only after recall is measured

The first nominal performance gate is <= 1.0 s per 180-second five-person squad, but this is only a gate. Faster approximations are preferable when shortlist recall remains strong.

## 9. Research-prototype retention policy

The earlier Crown/Mast research engine is **not kept in Git anymore**.

Do not recreate or re-import it as a production dependency. The only retained material is:

`fast_engine/research/LESSONS.md`

That document records reusable profiling/design findings and the research-specific assumptions that must not leak into the generic Fast runtime.

## 10. Git / branch state

Main calculator baseline:

`master`

Optimizer/Fast experiments must **not** be implicitly merged into `master`.

Previous optimizer line:

`optimizer-debug-localized-ambiguity-20260831`

Current Fast development line:

`fast-engine-phase2-20260901`

The Fast branch was forked from optimizer documentation HEAD `da67a1cf40cb281c66abcd85414a56ece00c5985`.

The current committed line contains the greenfield Fast baseline, Phase 1 feasibility prototype, and documentation. Anonymous account/profile data must remain local.

### Local/uncommitted work warning

Some optimizer correctness experiments and some later Fast-runtime vertical-slice work may exist only in local working copies. Never infer that a locally discussed result is committed merely because it was tested. Check the branch HEAD and files before continuing.

## 11. Existing optimizer principles that remain valid

- Moris is the final score authority.
- exact weighted set packing/global allocation is used over the evaluated Moris candidate pool.
- Meta/Cold/investment evidence affects search attention only, never damage.
- Cold filtering is reversible rather than hard legality.
- tail failures and paired-account outcomes matter more than headline averages.
- anonymous account/profile samples remain local and must not be committed.

## 12. Validation before production pruning

Before Fast is allowed to prune production candidates, compare equivalent static conditions against Moris and diagnose discrepancies with debug traces.

Then measure:

- Moris Top-N recall at increasing Fast shortlist widths
- final five-team Moris score after Fast shortlist + Moris re-score
- archetype-specific bias
- fallback/unsupported frequency
- candidate diversity
- large-roster tail failures
- Fast calls, Moris calls, wall time, and peak memory

Do not choose a production shortlist width from intuition.

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
10. After Fast increases compute, re-audit and ablate existing optimizer heuristics for scarcity-era overfitting.
11. Distinguish committed Git state from local experimental artifacts.
12. Never commit anonymous account/profile data.
13. Do not restore the removed Crown/Mast research prototype as a production dependency; use `fast_engine/research/LESSONS.md` for the retained lessons.

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
