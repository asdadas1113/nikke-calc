# Roster optimizer devlog

## 2026-08-30 — development baseline

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- start HEAD: `5fb57f98123b0ecdac13726c0dbc81bf183c8a31`
- Moris upstream: `Moris-kr/nikke-calc` `master` @ `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- engine relation: prototype is based on the same Moris upstream engine commit; optimizer-only changes are one commit above it at the start of this session.

### Current state

- isolated `optimizer/` package exists.
- evaluator path is `build_squad -> build_config -> simulate`.
- default optimizer evaluation is expected mode with `verbose=False`.
- global allocation is exact only within the evaluated candidate pool; candidate discovery remains heuristic.

### Measured benchmark

See `docs/BENCHMARK.md` and `docs/roster-optimizer-prototype.md` for measured evaluator and synthetic exhaustive results.

---

## 2026-08-30 — cache identity + exhaustive validation harness

- implementation HEAD before benchmark-doc update: `19c4def7fd9c8e896ebab1f75085cae44d06523a`
- Moris upstream remains: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- calculator/site files changed: none

### Implemented

1. Added `CacheIdentity(engine_commit, account_snapshot)` to the evaluator.
   - cached evaluators now require an explicit identity.
   - cache keys retain ordered squad members, character/build overrides, config, enemy, seed, and verbose state, and now also include engine/account identities.
   - `MorisEvaluator.from_moris()` requires engine commit and account snapshot when caching is enabled.
2. Added `optimizer/validation.py`.
   - tiny ordered or unordered legal-team enumeration.
   - exhaustive ground-truth evaluation.
   - candidate-pool evaluation separated from ground-truth evaluation so Moris cache reuse cannot fake a cheap optimizer budget.
   - optional call counters can record actual `MorisEvaluator.stats.simulate_calls` deltas later.
   - metrics: optimum-team survival, Top-N recall, final/exhaustive score ratio, evaluator calls, runtime.
3. Added a synthetic global-allocation regression fixture.
   - strongest single team is deliberately not part of the global optimum.
   - verifies candidate survival and global allocation rather than proxy Top-1 accuracy.

### Tests / measured result

Local optimizer unit tests: 9/9 passed.

Synthetic fixture:

- 8 members, 28 legal 2-person teams.
- exhaustive evaluator calls: 28.
- optimizer evaluator calls: 6.
- exhaustive optimum: 184.
- final allocation: 184 (100% of optimum).
- true-optimum team survival: 100% (2/2).
- Top-5 individual-team recall: 60% (3/5).
- measured local CPython 3.13.5 runtimes are recorded in `docs/BENCHMARK.md`.

### Failure cases

No new optimizer failure was observed in this milestone. The synthetic fixture confirms the existing global-allocation design avoids the sequential-greedy trap, so no additional heuristic was added.

### Next work

1. connect cheap NIKKE-specific legal-team checks without duplicating simulator logic.
2. establish a first marginal-value experiment on a deliberately small roster/reference-team set.
3. run exhaustive comparison on that small space and only then decide whether pair synergy or stronger diversity buckets are necessary.
