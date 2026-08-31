# Fast Engine

Fast Engine is the optimizer-only high-throughput ranking engine for Solo Raid candidate discovery.

## Contract

Fast Engine is **not** a second Moris calculator and is not expected to reproduce Moris damage exactly.

Its purpose is narrower:

> Run a 180-second theoretical static-target fight cheaply enough to compare many squads and preserve the squads that are likely to rank highly when Moris evaluates them later.

The design priorities are:

1. **180-second time basis.** Preserve enough internal timing to distinguish burst alignment, buff windows, stacks/gauges, ammo/reload/charge behavior, and other team interactions. Do not reduce the engine to `DPS × 180`.
2. **Ranking over precision.** Absolute damage error is secondary to relative ordering and Moris Top-K recall.
3. **False negatives are expensive.** A false positive can be removed by Moris re-evaluation; a strong squad discarded by Fast cannot be recovered. Screening should therefore be conservative.
4. **Aggressive optimization is allowed.** Unlike the detailed Moris UI path, Fast may use event aggregation, compiled timelines, score-only state, cached/condensed state, event-driven scheduling, expected-value approximations, or other optimizations when ranking recall remains acceptable.
5. **Moris remains final authority.** Fast scores may rank/screen candidates, but shortlisted squads are re-evaluated by Moris before exact five-team allocation.
6. **Moris parsed data is the source language.** Prefer reusable mechanics/opcodes over hand-maintained per-character implementations.
7. **Unsupported mechanics are explicit.** Do not silently convert an unknown mechanic to zero. Route uncertain/unsupported squads to Moris or mark them for protected review.

## Static enemy model

The initial Fast target is patternless but may have static raid-relevant properties:

- enemy DEF
- enemy element/code
- expected core exposure

Core is represented initially as:

```text
effective_core_rate = core_uptime × core_hit_rate_when_open
```

The first external interface may expose only `core_uptime` and assume `core_hit_rate_when_open = 1.0`. The expected rate should influence both core damage contribution and core-hit-driven expected triggers where relevant.

Not modeled in the initial Fast target:

- immune/invulnerable timing windows
- element-restriction timing windows
- boss attacks
- stun, cover destruction, movement
- timed part-break scripts
- boss AI/pattern order

Those are Moris/final-validation concerns.

## Quality gates

Primary validation metrics, in order:

1. Moris Top-N recall within increasing Fast Top-K shortlist widths
2. catastrophic miss/tail failure rate by account and composition archetype
3. systematic ranking bias by weapon/mechanic/team type
4. wall-clock throughput
5. absolute Fast-vs-Moris damage error

The first runtime milestone is a complete 5-person vertical slice under the static 180-second contract, then real-squad ranking/recall validation. A nominal first performance gate is <= 1.0 s per 180-second squad, with 0.5-0.7 s as an initial practical target; faster approximations are welcome if recall remains strong.

## Repository layout

- `prototype_phase1/`: committed feasibility compiler/router snapshot. It proves structural viability; it is not the production runtime.
- `research/crown_mast_reference/`: sanitized reference snapshot of the user-provided controlled Crown/Mast research engine. It is architecture reference only and must not be treated as a general engine.
- future production runtime/compiler code should live directly under `fast_engine/` in clearly named packages rather than mutating the historical snapshots in place.

See `docs/OPTIMIZER_PROJECT_STATE.md` for the canonical project status and handoff rules.
