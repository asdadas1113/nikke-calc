# Fast Engine

Fast Engine is the optimizer-only high-throughput ranking engine for Solo Raid candidate discovery.

## Contract

Fast Engine is **not** a second Moris calculator and is not expected to reproduce Moris damage exactly.

Its purpose is narrower:

> Run a 180-second theoretical static-target fight cheaply enough to compare many squads and preserve the squads that are likely to rank highly when Moris evaluates them later.

The design priorities are:

1. **180-second battle horizon, no fixed frame loop.** Preserve enough internal timing to distinguish burst alignment, buff windows, stacks/gauges, ammo/reload/charge behavior, and other team interactions. The runtime advances between meaningful events and aggregates unchanged spans rather than stepping at 1/60 s.
2. **Ranking over precision.** Absolute damage error is secondary to relative ordering and Moris Top-K recall.
3. **False negatives are expensive.** A false positive can be removed by Moris re-evaluation; a strong squad discarded by Fast cannot be recovered. Screening should therefore be conservative.
4. **Speed-first approximation is allowed.** Fast may use event aggregation, compiled timelines, score-only state, cached/condensed state, expected-value approximations, interval integration, or other optimizations when ranking recall remains acceptable.
5. **Moris remains final authority.** Fast scores may rank/screen candidates, but shortlisted squads are re-evaluated by Moris before exact five-team allocation.
6. **Moris owns input/build semantics.** Prefer `context.spec.build_squad()` for account/build assembly, `calc_base_stats()` for compile-time base stats, and Moris active-effect/favorite selection as the source semantics. Fast then compiles those results into its own runtime representation.
7. **Moris parsed data is the source language.** Prefer reusable mechanics/opcodes over hand-maintained per-character implementations.
8. **Unsupported mechanics are explicit.** Do not silently convert an unknown mechanic to zero. Route uncertain/unsupported squads to Moris or mark them for protected review.
9. **Runtime core is character-name blind.** Character-specific behavior should compile into generic primitives; named branches in burst/scheduler code are a last resort and must be capability-routed.

## Static enemy model

The initial Fast target is patternless but may have static raid-relevant properties:

- enemy DEF
- enemy element/code
- expected core exposure
- battle duration (default 180 s)

Core is represented initially as:

```text
effective_core_rate = core_uptime × core_hit_rate_when_open
```

The expected rate should influence both core damage contribution and core-hit-driven expected triggers where relevant.

Not modeled in the initial Fast target:

- immune/invulnerable timing windows
- element-restriction timing windows
- boss attacks
- stun, cover destruction, movement
- timed part-break scripts
- boss AI/pattern order

Those are Moris/final-validation concerns.

## Greenfield runtime

The production runtime is built from scratch under `engine/`. The earlier Crown/Mast research engine is **not stored in the repository anymore** and is not a code dependency.

Reusable findings from that experiment are retained only in `research/LESSONS.md`.

Current production baseline includes the greenfield compiled model, continuous-time scheduler, capability/state infrastructure, and the Phase 1 structural prototype remains separately under `prototype_phase1/` as feasibility history.

## Quality gates

Primary validation metrics, in order:

1. Moris Top-N recall within increasing Fast Top-K shortlist widths
2. catastrophic miss/tail failure rate by account and composition archetype
3. systematic ranking bias by weapon/mechanic/team type
4. wall-clock throughput
5. absolute Fast-vs-Moris damage error

The first full runtime milestone is a complete 5-person score-only vertical slice under the static 180-second contract. A nominal first performance gate is <= 1.0 s per squad; substantially faster approximations are preferred when recall remains strong.

## Repository layout

- `engine/`: production greenfield Fast runtime/compiler.
- `tests/`: production Fast tests.
- `prototype_phase1/`: feasibility compiler/router snapshot. Structural proof only; not the production runtime.
- `research/LESSONS.md`: reusable findings and rejected assumptions from the removed controlled research engine.

The original Crown/Mast research prototype and its sanitized archive are intentionally not kept in Git.

See `docs/FAST_ENGINE_ARCHITECTURE.md` for the greenfield contract and `docs/OPTIMIZER_PROJECT_STATE.md` for the broader optimizer handoff state.
