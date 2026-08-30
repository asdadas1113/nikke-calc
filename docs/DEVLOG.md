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

---

## 2026-08-30 — conservative Moris burst hard constraints

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- session start HEAD: `60113cb4d985e902138bb94e8fbeffad705a9fec`
- Moris upstream at start/end: `Moris-kr/nikke-calc` `master` @ `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- implementation commit: `09521b89a1eb48fb14a09f6b5184f735c83eb0dd`
- CI wiring commit: `7f4d3a1225a99d7fb6a8a3b85c14336702ff3ced`
- calculator/site source files changed: none

### Canonical behavior confirmed

`calculator.timeline.BurstController` permanently blocks only when the current burst stage has no candidates. If candidates exist but all are on cooldown, Moris waits for the earliest cooldown instead of treating the squad as illegal. Stage `A` participates in stages 1, 2, and 3. In auto mode `no_burst_char` / `no_burst_chars` are removed from burst candidates; explicit `burst_sequence` changes those semantics.

### Implemented

1. Added `BurstMetadata`, `BurstStructureReport`, and `BurstStructureValidator` in `optimizer/constraints.py`.
2. `BurstStructureValidator.from_moris()` reads Moris canonical parsed metadata through `context.spec.burst_stage()` plus `data/parsed_nikke.json` cooldowns.
3. Static stage coverage mirrors Moris `1` / `2` / `3` / `A` behavior and character-level `burst_stage` overrides.
4. Cooldown is exposed only as diagnostic `min_cooldown_by_stage`; no cooldown threshold hard-prunes a squad.
5. Runtime `burst_stage_override:*` effects are detected from `parsed_skills.json`. A statically missing stage that a runtime override may reach is marked uncertain and survives pruning.
6. Explicit `burst_sequence` is conservatively deferred to Moris rather than partially reimplementing its cycle semantics.
7. Added an optimizer unit-test step to `.github/workflows/ci.yml` so prototype tests are exercised on future PR validation.

### Verification

GitHub Actions CI run `33311227170` on CPython 3.13.15 / Ubuntu 24.04 completed successfully:

- optimizer: 18 tests passed in 0.026 s.
- calculator engine: 137 tests passed, 1 skipped.
- bridge: 31 tests passed, 1 skipped.
- browser: 385 tests passed.
- golden damage snapshot: 29/29 passed.
- doclint and calculator damage cross-checks passed.

The optimizer integration test loads real Moris metadata and verifies `네온` / `아니스` / `라피` as a valid B1/B2/B3 structure with 20 s / 20 s / 40 s minimum cooldown diagnostics. No new Moris combat `simulate()` benchmark was run in this milestone.

Temporary draft PR #2 was used only to trigger CI and was closed without merge.

### Failure cases / limitations

No regression or hard-constraint failure was observed. Because false-negative pruning is more damaging than leaving an impossible team for the simulator, dynamic burst-stage cases and explicit burst sequences intentionally remain conservative. This milestone does not attempt to infer whether a 40-second burst structure is weak; that belongs to proxy/simulator scoring, not legality.

### Next work

1. run the first small real-Moris marginal-value experiment with an explicit fixed build snapshot and boss config.
2. compare marginal/proxy candidate survival against exhaustive truth in that deliberately small search space.
3. only add pair synergy or stronger diversity buckets if that experiment produces a concrete recall failure.
