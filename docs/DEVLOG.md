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

---

## 2026-08-30 — first real Moris marginal/proxy failure case

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- session start HEAD: `8d511d2f0835e902138bb94e8fbeffad705a9fec`
- cleaned benchmark fixture commit: `719a4475c9ac162ca24cd55e3199189593de1e43`
- Moris upstream at start/end: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- calculator/site source files changed: none

### Implemented

1. Added `tests/benchmark_optimizer_marginal_real.py` as an explicit, non-unit-test benchmark fixture.
2. The fixture supports two reference variants:
   - `minimal-3`: economical reference coverage.
   - `balanced-6`: at least two marginal observations per roster character.
3. Search scope is deliberately limited to one canonical placement per unordered 5-member combination and one final team. It must not be reported as full ordered or full five-team ground truth.
4. Temporary benchmark workflow commits used to trigger GitHub Actions were removed from branch history. The net benchmark script was rewritten as one clean commit directly on top of the previous optimizer milestone.

### Actual measured results

Common fixture:

- 8 real NIKKE characters.
- 54 legal teams after conservative burst constraints.
- 180 s, enemy DEF 31,784, no special element/core/parts condition.
- expected RNG, seed 42.
- candidate limit 12.
- fixture exhaustive optimum: `리타 / 크라운 / 홍련 / 앨리스 / 모더니아` = `1,785,817,889`.

`minimal-3`, Actions run `33312943457`:

- marginal calls: 46, 123.120402 s.
- exhaustive calls: 54, 147.223756 s.
- selected-candidate calls: 12, 39.900060 s.
- total optimizer calls: 58.
- true optimum survival: 100%.
- Top-5 recall: 60%.
- final / exhaustive optimum: 100%.
- true Top-5 proxy ranks: 1 / 8 / 22 / 6 / 13.

`balanced-6`, Actions run `33313327360`:

- marginal calls: 89, 293.561895 s.
- exhaustive calls: 54, 175.379114 s.
- selected-candidate calls: 12, 41.095275 s.
- total optimizer calls: 101.
- true optimum survival: 100%.
- Top-5 recall: 60%.
- final / exhaustive optimum: 100%.
- true Top-5 proxy ranks: 9 / 18 / 7 / 2 / 19.

Standard CI also completed successfully during both benchmark runs.

### Failure / decision

Increasing reference coverage fixed one severe rank error (true #3: proxy 22 -> 7) but displaced other top teams. Top-5 recall stayed at 60% while marginal calls rose from 46 to 89.

Therefore:

- do not simply increase reference count as the next algorithm change;
- do not add all-pairs synergy;
- first test a cheap soft burst/RoleFit structural signal against this saved failure case;
- 40-second B1/B2 structures remain legal and may only receive a soft search penalty/bucket treatment;
- if significant recall failures remain after that test, measure only the pair/core interactions implicated by those failures.

---

## 2026-08-30 — RoleFit diagnostic and context-sensitive pair probes

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- session start baseline for this work: `8d511d2f0835d6cf7fbadc994a427af434c2bd05`
- Moris upstream remains: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- RoleFit benchmark commit: `ddc1f155492087f433031b44e7555ee382193858`
- pair API commits: `d1a6cb3e03a05c0dfd25ec5b68bfb5f9d5e6bbc4`, `44586abc97ea027ab94e853515d8c310fbc54bac`, `92fd646cb3ee11df27f7d8d83e4768776ff0dd7b`
- pair benchmark fixture: `94edbf558dc1a51583b24f55ea2414dbe18eeab6`
- calculator/site source files changed: none

### RoleFit result

A benchmark-local soft 20-second burst supply diagnostic was tested without changing legality.

Actions run `33314412300`:

- `minimal-3`: RoleFit did not improve Top-5 recall at any tested candidate limit; limit 12 remained 60%.
- `balanced-6`: only limit 8 improved (40% -> 60% with a 75% fit bucket); limits 12 and 16 remained 60%.
- all true Top-5 teams had zero burst-cycle deficit.
- several raw proxy false positives with true ranks 27~32 were correctly recognized as deficit `0.166667` structures.

Decision: keep RoleFit benchmark-local. It diagnoses some false positives but does not solve the important recall miss, so it is not promoted into production proxy scoring.

### Selective pair API

Added `optimizer/synergy.py` with `PairSynergyProbe`, `PairSynergyObservation`, and `measure_pair_probes()`.

The API intentionally has no all-pairs enumeration path. A caller must explicitly provide:

- pair
- reference team
- two replacement slots
- source/reason

It measures the fixed-slot four-point residual:

`D(R+A+B) - D(R+A) - D(R+B) + D(R)`

and preserves exact ordered placement. Hard-illegal probes raise instead of silently disappearing.

### Real pair result

Actions run `33315102493` measured only 3 probes / 2 unique pairs:

- actual Moris `simulate()` calls after cache reuse: 11.
- runtime: 28.327515 s.
- `크라운+나가`: interaction `-242,387,321` in the failure-linked context.
- `볼륨+크라운`: `-35,906,913` in one context and `+577,438,478` in another.

The Volume+Crown sign reversal is decisive: a pair cannot safely be represented by one transferable scalar independent of the surrounding team.

Diagnostic replay using pair means:

- `minimal-3` limit-12 recall stayed 60% for alpha 0.25 / 0.50 / 1.00, and the missed Crown+Naga team moved farther down.
- `balanced-6` reached 80% at alpha 0.50 / 1.00, but the gain did not transfer to the other reference variant and still harmed the Crown+Naga failure.

### Decision / failure case

Reject global additive `Syn(A,B)` as the default proxy model. Pair/core evidence must remain context-specific.

The probe primitive is retained because its paired team is itself an actually simulated candidate. The intended future use is:

1. a failure case, skill relation, meta core, or near-miss nominates a small interaction hypothesis;
2. probe that exact context;
3. add the actually measured paired variants to the candidate pool;
4. rerun global allocation/refinement;
5. do not broadcast the residual to unrelated teams.

### Next task

1. use the saved marginal failure to test whether a small one-person/local-neighborhood refinement around actually simulated strong candidates recovers the missed compositions more efficiently than making the proxy more complicated;
2. keep placement order explicit when generating swaps; membership-level and ordered-placement reachability must not be conflated;
3. add context-specific pair probes only after local refinement or meta/skill evidence identifies a concrete gap;
4. once a candidate-generation/refinement loop is stable, move back to 5-team global-allocation quality rather than optimizing single-team proxy rank indefinitely.

---

## 2026-08-30 — bounded one-swap refinement recovery

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- session start HEAD: `90c7f02dbea951b15bc698ac9aa57f4cc695cba8`
- Moris upstream at start/end: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- refinement implementation: `a4b0797c21263b314984026b3492cd8df34c8837`
- export: `40b304edf2a365283d770cb308c1143be0ba3920`
- unit tests: `aa27663d3a3003bc88989a1cdb33ad018b658809`
- real benchmark fixture: `aa52b2cc9e2139dcc58352eb97afc4b60296b09c`
- benchmark run: `33316454385`
- validation CI run: `33316454356`
- calculator/site source files changed: none

### Implemented

Added `optimizer/refinement.py` with `OneSwapNeighbor` and `generate_one_swap_neighbors()`.

The primitive:

- preserves the replaced slot/order by default;
- treats the final ordered tuple as identity, so same members in different placements are not collapsed;
- accepts an explicit placement resolver only when the caller deliberately wants another placement convention;
- applies hard legality before emitting a neighbor;
- skips previously evaluated ordered teams;
- deduplicates generated ordered teams;
- lets the caller restrict seed order, positions, incoming roster order, and `max_new` instead of hiding a broad brute-force policy inside the primitive.

The real benchmark uses the saved fixture's canonical placement resolver only so its results remain directly comparable to the earlier fixed-placement exhaustive truth. This does not change the production default.

### Actual measured results

Both prior 12-candidate pools started at true Top-5 recall 60%.

`minimal-3`:

- seed 1: 5 new legal unseen neighbors, recall 60%.
- seed 2: 11 neighbors, recall 60%.
- seed 3: 18 neighbors, recall **100%**.
- full benchmark new Moris calls: 18.
- refinement runtime: 55.945311 s.
- recovered true #3 and #5, with exact score reproduction: `1,559,674,086` and `1,435,571,126`.
- prior pipeline + refinement measured call count: 46 marginal + 12 initial candidate + 18 refinement = 76.

`balanced-6`:

- seed 1: 8 new legal unseen neighbors, recall 80%.
- seed 2: 16 neighbors, recall **100%**.
- seed 3: 18 neighbors, recall 100%.
- full benchmark new Moris calls: 18.
- refinement runtime: 58.649881 s.
- recovered true #2 and #5, with exact score reproduction: `1,656,756,068` and `1,435,571,126`.
- a stop-after-seed-2 policy would require 16 new unique evaluations, giving 89 marginal + 12 initial candidate + 16 refinement = 117 calls; separate 16-call wall time was not measured.

The complete actual-score Top-5 after refinement matched the saved fixture true Top-5 exactly in both variants.

### Verification

CI run `33316454356` on the implementation/benchmark head completed successfully:

- calculator engine: 137 tests passed, 1 skipped, 39.061 s.
- optimizer: **29 tests passed in 0.025 s**.
- bridge: 31 tests passed, 1 skipped, 32.948 s.
- browser: 24 files / 385 tests passed.
- golden snapshot: 29/29 passed.
- doclint and damage cross-checks passed.

Temporary draft PR #6 was closed without merge. Its benchmark-only workflow commit was removed from the prototype branch history after the measured run.

### Decision / limitations

The saved failure justifies keeping bounded one-person refinement as a real optimizer primitive. It recovered the misses that extra marginal references, RoleFit reranking, and transferable pair weights did not reliably recover.

Do **not** infer a universal `seed_count=3`: `minimal-3` required three seeds, while `balanced-6` reached full recall with two. Also do not claim call efficiency from this tiny fixture: exhaustive truth costs only 54 calls here, while the experimental marginal pipelines plus refinement cost more. Production value depends on the combinatorial growth of real rosters, where exhaustive search is not feasible.

Known/set-NIKKE and famous-core rescue rules are deliberately deferred until their actual usage patterns are researched; they were not added in this session.

### Next task

1. stop optimizing the single-team fixture as the main target;
2. connect evaluated candidates + one-swap refinement back to the existing exact five-team global allocator;
3. design refinement seed selection around the current five-team allocation and bottleneck/near-miss teams under an explicit simulation-call budget;
4. create a tractable multi-team regression fixture that can measure whether re-global-allocation after refinement improves total non-overlapping damage;
5. only after that, research and add known/set-NIKKE or famous-core rescue candidates as a separate, explicitly sourced candidate channel.

---

## 2026-08-30 — normalized account snapshot and build-propagation E2E

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- session start HEAD: `6c6959ee6a98bb662170fb840c65221af9a9c30a`
- permanent implementation/test head before docs: `ae6bfde39a3091e58dd58ab853aadd7542f26b35`
- Moris upstream at start/end: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- final E2E run: `33318423444`
- final standard CI run before docs: `33318423434`
- calculator/site source files changed: none
- private account/profile data committed: none

### Canonical account-sync path confirmed

The optimizer must not parse raw blablalink account responses independently. `scraper/profile_fetch.py` remains the raw account-sync source of truth and emits the calculator-facing `profiles/<name>.json` format. Existing `context.spec.GrowthProfile` is the correct Moris layer for applying that profile before `build_squad()`.

Important source behavior confirmed:

- profile-sync emits actual breakthrough/core/affinity, skill levels, equipment, overload options, collection/favorite stage, and account console where available;
- absent equipment is represented explicitly rather than left to fixed-build equipment;
- Solo Raid character level is intentionally not an account character field; the default optimizer policy retains fixed level 400;
- cube sync is only an equipped-cube lower bound, so cube choice is not treated as fully observed account build state;
- current profile format may preserve prior console/synchro information when current outpost data is incomplete, so provenance cannot always be called freshly observed.

### Implemented

1. Added `optimizer/account.py` with:
   - `AccountSnapshot`
   - `AccountSyncAdapter`
   - `FieldProvenance`
   - `ProvenanceStatus`
   - `normalize_account_sync()`
2. Normalization statuses are `observed`, `preserved`, `defaulted`, `unknown`, and `uncertain`.
3. Default `unknown_policy="error"` blocks simulation-affecting missing fields instead of silently inheriting Moris fixed-build values. `unknown_policy="moris-default"` is an explicit opt-in fallback and retains unknown provenance.
4. Strict checks cover skill subfields, four equipment parts, overload fields, account console, sync-mode synchro level, and favorite-stage presence for canonical favorite-item characters.
5. Legacy per-character `level` and `cube` fields are rejected so old/noncanonical data cannot bypass the normalized policy.
6. Sensitive `_meta.openid` is not retained in the normalized snapshot.
7. Snapshot fingerprint ignores fetch timestamp but changes when build data changes. It is used automatically as `MorisEvaluator` account cache identity.
8. Snapshot build payload is stored as immutable canonical JSON. Public `profile_payload` returns a detached decoded copy, preventing post-fingerprint mutation from altering subsequent Moris builds.
9. Added `MorisEvaluator.from_moris_snapshot()`; it converts exactly one snapshot through `GrowthProfile` and binds that profile to every evaluator `build_squad()` call.
10. Added `tests/benchmark_optimizer_account_e2e_real.py`. It contains only synthetic profile-sync-shaped build data, not a private account fixture.

### Actual measured E2E result

Fixture:

- roster: `리타 / 크라운 / 홍련 / 앨리스 / 모더니아 / 나가`.
- tested team: `리타 / 크라운 / 홍련 / 앨리스 / 모더니아`.
- one-swap neighbor: `리타 / 크라운 / 홍련 / 앨리스 / 나가`.
- 30 s, enemy DEF 31,784, expected RNG, seed 42.
- snapshots differ only by Alice build: invested vs skills 1/1/1, affinity 1, no equipment, no collection item.

Invested snapshot:

- id: `acct-e46722a42f5968efcabe668b`.
- direct Moris = snapshot evaluator candidate = fresh final evaluator: `141,194,861`.
- Naga marginal mean: `-6,506,586`.
- one-swap neighbor: `113,129,883`.
- optimizer evaluator calls: 5; fresh final evaluator calls: 1.

Weak-Alice snapshot:

- id: `acct-06857f9b028afb6b18a5da44`.
- direct Moris = snapshot evaluator candidate = fresh final evaluator: `135,391,386`.
- Naga marginal mean: `-703,111`.
- one-swap neighbor: `107,326,408`.
- optimizer evaluator calls: 5; fresh final evaluator calls: 1.

Weakening Alice changed candidate/full-team and refinement-neighbor damage by exactly `5,803,475`, and changed the marginal result by the corresponding amount. The immutable-snapshot rerun reproduced every score and snapshot ID exactly.

This verifies account-build propagation through:

`normalized sync payload -> GrowthProfile -> direct Moris / candidate evaluator -> marginal -> 1-swap refinement -> allocation -> fresh final simulation`.

### Verification

Final benchmark run `33318423444`:

- optimizer unit tests: **40/40**, 0.038 s in the benchmark job.
- normalized AccountSnapshot real-Moris E2E: success with the exact values above.

Standard CI run `33318423434`:

- calculator engine: 137 tests passed, 1 skipped, 31.854 s.
- optimizer: 40 tests passed in 0.032 s.
- bridge: 31 tests passed, 1 skipped, 27.348 s.
- browser: 24 files / 385 tests passed, vitest duration 29.07 s.
- golden snapshot: 29/29 passed.
- doclint and calculator damage cross-checks passed.

Temporary draft PRs #8 and #9 were closed without merge. Their temporary account-benchmark workflow commits were removed from the prototype branch history.

### Limitation / next task

A 50–80-character **actual private account** benchmark has not been measured yet. `profiles/` is intentionally gitignored and no private profile was available in GitHub Actions, so this session did not replace it with guessed or maximum build values.

Next:

1. run the optimizer from a gitignored real profile through `AccountSyncAdapter` and record snapshot provenance/unknowns before any search;
2. on the full 50–80 roster measure simulate-call budget, runtime, one-swap refinement gain, five-team allocation gain/stability, and seed sensitivity;
3. do not claim full-roster recall where exhaustive truth is impossible; cut tractable subsets from the same real snapshot and use those subsets for true Top-N recall/optimum-survival measurements;
4. expand context-specific pair/core probes only if a measured failure remains after refinement;
5. keep Meta-Aware scoring deferred until the real-account production-scale path is validated.
