# Documentation index

## Current optimizer direction

For roster-optimizer / Fast Engine work, read this first:

- **[`OPTIMIZER_PROJECT_STATE.md`](OPTIMIZER_PROJECT_STATE.md)** — current architecture, committed-vs-local status, Fast Engine scope, static enemy/core model, Moris fallback policy, validation metrics, and roadmap.

When an older optimizer document conflicts with `OPTIMIZER_PROJECT_STATE.md`, the project-state document is the current decision record.

## Optimizer experiment history

These remain useful for experiment detail and provenance, but some design decisions have since changed:

- [`roster-optimizer-prototype.md`](roster-optimizer-prototype.md) — original optimizer package/evaluator boundary and early search-policy design.
- [`optimizer-performance-deferred.md`](optimizer-performance-deferred.md) — earlier performance decision tree before the separate Fast Engine direction became preferred.
- [`meta-guided-cold-pool.md`](meta-guided-cold-pool.md) — Meta/Cold design and safeguards.
- [`optimizer-meta-api.md`](optimizer-meta-api.md) — Meta API details.
- [`search-budget-study.md`](search-budget-study.md) — search-budget experiments.
- [`placement-order-study.md`](placement-order-study.md) — placement-order experiments.
- [`seed-meta-epoch.md`](seed-meta-epoch.md), [`meta-epoch-date-precision.md`](meta-epoch-date-precision.md) — Meta epoch/provenance research.
- [`BENCHMARK.md`](BENCHMARK.md) — benchmark records.
- [`DEVLOG.md`](DEVLOG.md) — development log.

## Handoff rule

A fresh optimizer work session should use `OPTIMIZER_PROJECT_STATE.md` as the context handoff, then open only the historical documents needed for the specific task.
