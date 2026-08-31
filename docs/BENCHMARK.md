# Roster optimizer benchmark log

This file records measured optimizer/evaluator results together with the exact engine baseline. Estimated numbers must not be added here; unmeasured items are marked `TBD`.

## Baseline 2026-08-30

- repository: `asdadas1113/nikke-calc`
- branch at measurement: `roster-optimizer-prototype`
- optimizer start HEAD: `5fb57f98123b0ecdac13726c0dbc81bf183c8a31`
- Moris upstream: `Moris-kr/nikke-calc` `master` @ `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- runner: GitHub Actions `ubuntu-24.04`
- Python: CPython 3.13.15
- squad: `리타 / 크라운 / 홍련 / 앨리스 / 나가`
- fight duration: 180 s
- enemy DEF: 31,784
- RNG: `expected`
- seed: 42
- lazy data caches: warmed before timing

| operation | measured result |
| --- | ---: |
| `build_squad` | median 0.624 ms over 20 runs |
| `build_config` | median 0.003 ms over 20 runs |
| `simulate(verbose=False)` | 2.675102 s |
| `simulate(verbose=True)` | 2.838826 s |
| verbose overhead | +0.163724 s / +6.12% |

Both simulation runs produced squad total `1,428,044,008` and 19,195 hits. `verbose=False` returned no log; `verbose=True` returned a log.

## Synthetic exhaustive validation 2026-08-30

This is a harness smoke/regression measurement, **not a Moris combat benchmark**. It uses a deterministic synthetic score table so the exhaustive optimum is cheap enough to calculate exactly.

- environment: local execution container, CPython 3.13.5
- roster: 8 synthetic members (`A` through `H`)
- team size: 2
- allocation size: 2 teams
- order: ignored for this fixture only (`ordered=False`)
- legal teams: 28
- candidate selector: `select_diverse(..., limit=6, similarity_penalty=0.5)`
- Top-N metric: N=5

| metric | measured result |
| --- | ---: |
| exhaustive evaluator calls | 28 |
| optimizer evaluator calls | 6 |
| true optimum | 184 |
| true-optimum team survival | 100% (2/2) |
| Top-5 individual-team recall | 60% (3/5) |
| final allocation | 184 |
| final / exhaustive optimum | 100% |
| exhaustive runtime | 0.000149486 s |
| selected-pool evaluation + allocation runtime | 0.000210838 s |

The fixture deliberately makes the strongest single team (`AB=100`) a global-allocation trap: `AC + BD = 184` is better than locking `AB` first and taking a disjoint fallback. The current diversity filter retains both globally useful teams in its six-candidate pool, so no new heuristic is justified by this case.

The runtime numbers above only verify that the harness ran; they are too small and synthetic to predict Moris optimizer wall time.

## First real-Moris marginal/proxy fixture 2026-08-30

This is the first optimizer-quality experiment using the real Moris combat evaluator. It is deliberately small and **is not full ordered NIKKE ground truth**.

Common fixture:

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- session start HEAD: `8d511d2f0835d6cf7fbadc994a427af434c2bd05`
- current cleaned benchmark fixture commit: `719a4475c9ac162ca24cd55e3199189593de1e43`
- Moris upstream / engine identity: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- account snapshot identity: `benchmark-default-build-2026-08-30`
- runner: GitHub Actions `ubuntu-24.04`
- Python: CPython 3.13.15
- roster: `리타 / 볼륨 / 크라운 / 나가 / 홍련 / 앨리스 / 모더니아 / 레드 후드`
- team count: 1
- team size: 5
- placement scope: one canonical placement per unordered 5-member combination
- full ordered 5! placement search: **not measured**
- legal teams after conservative burst hard constraints: 54
- duration: 180 s
- enemy DEF: 31,784
- enemy element/core/parts special conditions: none
- RNG: `expected`
- seed: 42
- candidate limit: 12
- Top-N recall metric: N=5

The exhaustive optimum inside this explicitly limited fixture was:

`리타 / 크라운 / 홍련 / 앨리스 / 모더니아` = **1,785,817,889**.

### Variant A — `minimal-3`

GitHub Actions benchmark run: `33312943457`.

Three reference teams were used. Every roster character received at least one marginal observation, but most received only one.

| metric | measured result |
| --- | ---: |
| marginal `simulate()` calls | 46 |
| marginal runtime | 123.120402 s |
| exhaustive `simulate()` calls | 54 |
| exhaustive runtime | 147.223756 s |
| selected-candidate `simulate()` calls | 12 |
| selected-candidate runtime | 39.900060 s |
| total optimizer calls: marginal + selected | 58 |
| true optimum survival | 100% |
| true Top-5 recall | 60% (3/5) |
| final / fixture exhaustive optimum | 100% |
| proxy rank of true optimum | 1 |
| `select_diverse(limit=12, penalty=0.20)` Top-5 recall | 60% |

True Top-5 teams appeared at proxy ranks **1, 8, 22, 6, 13** respectively. The third-strongest real team therefore fell to proxy rank 22, establishing the first concrete recall failure for the additive marginal proxy.

### Variant B — `balanced-6`

GitHub Actions benchmark run: `33313327360`.

Six reference teams were used so every roster character had at least two marginal observations.

| metric | measured result |
| --- | ---: |
| marginal `simulate()` calls | 89 |
| marginal runtime | 293.561895 s |
| exhaustive `simulate()` calls | 54 |
| exhaustive runtime | 175.379114 s |
| selected-candidate `simulate()` calls | 12 |
| selected-candidate runtime | 41.095275 s |
| total optimizer calls: marginal + selected | 101 |
| true optimum survival | 100% |
| true Top-5 recall | 60% (3/5) |
| final / fixture exhaustive optimum | 100% |
| proxy rank of true optimum | 9 |
| `select_diverse(limit=12, penalty=0.20)` Top-5 recall | 60% |

True Top-5 teams appeared at proxy ranks **9, 18, 7, 2, 19** respectively.

Balancing reference coverage improved the previous rank-22 failure to rank 7, but it displaced other real top teams and left Top-5 recall unchanged at 60%. Marginal cost rose from 46 to 89 actual simulations. On this fixture, simply increasing reference count is therefore **not justified as the next fix**.

### Failure interpretation

The failure is consistent with two distinct proxy limitations that should be tested separately:

1. additive marginal values can over-rank teams whose individual members look valuable but whose cheap burst-role structure is inefficient;
2. additive marginals cannot represent context-sensitive pair/core interaction by construction.

No full 5-team real-roster exhaustive optimum, ordered-placement exhaustive optimum, or production-scale candidate budget has been measured yet; those remain `TBD`.

## Soft burst/RoleFit diagnostic 2026-08-30

Benchmark commit: `ddc1f155492087f433031b44e7555ee382193858`. GitHub Actions run: `33314412300`. The temporary workflow and draft PR #4 were used only to execute the benchmark and were removed/closed without merge.

The benchmark-local RoleFit estimates whether static B1/B2/B3 candidates provide enough cooldown supply for a nominal 20-second cycle. A 20 s unit contributes `1.0`, a 40 s unit `0.5`; two 40 s candidates can therefore satisfy the cheap supply estimate. Dynamic/uncertain/explicit-sequence structures receive no penalty. This feature is **soft only** and never changes legality.

### `minimal-3`

Fresh-run timing was 46 marginal calls / 145.455202 s, 54 exhaustive calls / 175.744169 s, and 12 selected-candidate calls / 47.403541 s. The candidate-selection result reproduced the prior 60% Top-5 recall and 100% fixture optimum survival.

| candidate limit | raw marginal | RoleFit bucket 50% | RoleFit bucket 75% |
| ---: | ---: | ---: | ---: |
| 8 | 60% | 60% | 60% |
| 12 | 60% | 60% | 60% |
| 16 | 80% | 80% | 80% |
| 20 | 80% | 80% | 80% |
| 24 | 100% | 100% | 100% |

True Top-5 raw proxy ranks `1 / 8 / 22 / 6 / 13` became RoleFit-first diagnostic ranks `1 / 7 / 19 / 5 / 12`. All true Top-5 teams had zero burst-cycle deficit. The severe true-#3 miss improved only from rank 22 to 19.

### `balanced-6`

Fresh-run timing was 89 marginal calls / 233.153286 s, 54 exhaustive calls / 141.546862 s, and 12 selected-candidate calls / 33.559833 s. The candidate-selection result again reproduced 60% Top-5 recall and 100% fixture optimum survival.

| candidate limit | raw marginal | RoleFit bucket 50% | RoleFit bucket 75% |
| ---: | ---: | ---: | ---: |
| 8 | 40% | 40% | 60% |
| 12 | 60% | 60% | 60% |
| 16 | 60% | 60% | 60% |
| 20 | 100% | 100% | 100% |
| 24 | 100% | 100% | 100% |

True Top-5 raw ranks `9 / 18 / 7 / 2 / 19` became RoleFit-first diagnostic ranks `6 / 14 / 5 / 1 / 15`. All true Top-5 teams again had zero deficit.

The signal correctly identified several obvious false-positive teams as slow-cycle structures: raw proxy ranks 1, 3, 8, and 10 had deficit `0.166667` while their true ranks were 32, 29, 28, and 27 respectively. However this demotion did not improve recall at the relevant 12/16-candidate budgets.

### Decision

Do **not** promote this RoleFit into production optimizer scoring yet. It is useful as a diagnostic of structural false positives, but the observed recall failure remains after those teams are demoted.

## Failure-driven selective pair probes 2026-08-30

Implementation commits introduced `optimizer/synergy.py` as an explicit probe primitive rather than an all-pairs enumerator. Benchmark run: `33315102493`, CPython 3.13.15 / Ubuntu 24.04. Draft PR #5 was closed without merge and its temporary workflow commit was removed from prototype history.

The benchmark reused the already measured marginal proxy and Top-5 truth from the exact same engine/build fixture. It measured only three four-point probes covering two failure-linked pairs, so no 54-team exhaustive rerun was needed.

| metric | measured result |
| --- | ---: |
| explicit probes | 3 |
| unique pairs | 2 |
| actual `simulate()` calls after cache reuse | 11 |
| runtime | 28.327515 s |
| all roster pairs enumerated | no |

Measured four-point interaction residuals:

- `크라운 + 나가`, around the true-#3 failure context: **-242,387,321**.
- `볼륨 + 크라운`, context targeting true #2: **-35,906,913**.
- `볼륨 + 크라운`, context targeting true #5: **+577,438,478**.
- the two-context arithmetic mean for `볼륨 + 크라운` was **+270,765,782**, but the sign reversal is the more important result.

Applying these pair means back to every team containing the pair was tested only as a diagnostic sensitivity check, not as a proposed production rule.

For `minimal-3`, Top-5 recall at candidate limit 12 stayed **60%** for alpha `0.25 / 0.50 / 1.00`; the true-#3 team was pushed from raw rank 22 to ranks 25 / 28 / 34 because the globally applied Crown+Naga residual was negative.

For `balanced-6`, recall at limit 12 rose from **60% to 80%** at alpha `0.50` and `1.00`, but this was not stable across the other reference variant and the Crown+Naga failure team again moved downward. Therefore the apparent gain is not evidence for a transferable global pair weight.

### Decision

Reject a global scalar `Syn(A,B)` as the default proxy representation. The same pair can change sign dramatically with the surrounding three members and replacement baseline. Preserve pair measurements as **context-specific observations**.

The selective probe primitive remains useful because every paired probe team is already an actually simulated candidate. Future pair/core work should therefore use probes to expand/rescue a small set of suspicious compositions and feed their real Moris scores back into the evaluated candidate pool, rather than broadcasting one pair bonus across unrelated teams.

## Bounded one-swap refinement 2026-08-30

Implementation:

- `optimizer/refinement.py`: `OneSwapNeighbor` and `generate_one_swap_neighbors()`.
- implementation commit: `a4b0797c21263b314984026b3492cd8df34c8837`.
- public export commit: `40b304edf2a365283d770cb308c1143be0ba3920`.
- refinement unit tests: `aa27663d3a3003bc88989a1cdb33ad018b658809`.
- real benchmark fixture: `aa52b2cc9e2139dcc58352eb97afc4b60296b09c`.
- GitHub Actions benchmark run: `33316454385`.
- full CI run on the benchmark head: `33316454356`, success.
- temporary draft PR #6 was closed without merge and the temporary workflow commit was removed from prototype history.

The production primitive preserves the replaced slot by default and treats the final ordered tuple as identity. The benchmark passes an explicit canonical roster-order resolver only because the saved exhaustive fixture measured one canonical placement per unordered membership set. Hard constraints are applied before emitting neighbors; already evaluated ordered teams are skipped; seed order, position scope, incoming roster order, and `max_new` can be constrained by the caller.

Common benchmark setup:

- replay the exact 12 already-simulated candidates from the prior real-Moris fixture;
- choose refinement seeds by their **actual Moris score**, not proxy score;
- generate only legal, unseen one-member neighbors;
- initial Top-5 recall: 60% (3/5);
- same engine/build/boss fixture as the prior exhaustive measurement.

### `minimal-3`

The three highest actually simulated seeds were true ranks #1, #2, and #4. The full three-seed neighborhood contained 18 legal unseen teams and cost 18 new Moris simulations / **55.945311 s**.

| refined seed count | new legal unseen neighbors | union Top-5 recall |
| ---: | ---: | ---: |
| 1 | 5 | 60% |
| 2 | 11 | 60% |
| 3 | 18 | **100%** |

At seed count 3 the refinement recovered both previously missed true Top-5 teams:

- `리타 / 크라운 / 나가 / 앨리스 / 레드 후드` = `1,559,674,086`.
- `리타 / 볼륨 / 크라운 / 앨리스 / 레드 후드` = `1,435,571,126`.

Both scores reproduced the saved exhaustive values exactly. The evaluated union was 30 teams and its actual-score Top-5 matched the fixture true Top-5 exactly.

If combined with the earlier measured `minimal-3` pipeline, the observed call count is 46 marginal + 12 initial-candidate + 18 refinement = **76 simulations**. That is larger than the 54-call exhaustive search in this intentionally tiny fixture; this benchmark demonstrates recovery quality, **not production-scale call efficiency**.

### `balanced-6`

The three highest actually simulated seeds were true ranks #1, #3, and #4. The full three-seed neighborhood again contained 18 legal unseen teams and cost 18 new Moris simulations / **58.649881 s**.

| refined seed count | new legal unseen neighbors | union Top-5 recall |
| ---: | ---: | ---: |
| 1 | 8 | 80% |
| 2 | 16 | **100%** |
| 3 | 18 | **100%** |

Seed 1 recovered true #2; seed 2 additionally recovered true #5. Their measured scores were exactly the saved exhaustive values:

- `볼륨 / 크라운 / 홍련 / 앨리스 / 모더니아` = `1,656,756,068`.
- `리타 / 볼륨 / 크라운 / 앨리스 / 레드 후드` = `1,435,571,126`.

A policy that stopped after the second seed would require 16 new unique team evaluations, making the corresponding call count 89 marginal + 12 initial-candidate + 16 refinement = **117 simulations**. Wall time for that 16-call stop point was not separately measured. The benchmark itself evaluated all 18 three-seed neighbors.

### Decision

Bounded one-member local refinement is **justified as an optimizer primitive** by this saved failure case: unlike extra reference coverage, RoleFit reranking, or global pair weights, it recovered all true Top-5 teams in both reference variants without changing the proxy model.

Do not hard-code `seed_count=3` from this fixture. One variant required three seeds while the other required two. Production policy still needs a call-budget rule, bottleneck/near-miss seed selection, and eventually a five-team global-allocation test. The next quality milestone should test refinement around teams relevant to the current five-team allocation rather than continuing to optimize this single-team fixture indefinitely.

## Normalized AccountSnapshot real-Moris E2E 2026-08-30

This milestone validates account-build propagation, **not production-scale search quality**. No private profile/account data is committed. The fixture uses the same calculator-facing shape emitted by `scraper/profile_fetch.py`, but all build values in the committed fixture are synthetic.

Baseline and implementation:

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- session start HEAD: `6c6959ee6a98bb662170fb840c65221af9a9c30a`
- permanent implementation/test head before docs: `ae6bfde39a3091e58dd58ab853aadd7542f26b35`
- Moris upstream / engine identity: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- E2E fixture: `tests/benchmark_optimizer_account_e2e_real.py`
- final E2E Actions run: `33318423444`
- final standard CI run before docs: `33318423434`
- runner: GitHub Actions `ubuntu-24.04`, CPython 3.13.15

`AccountSyncAdapter` consumes the calculator-facing profile-sync artifact rather than reimplementing raw blablalink parsing. `AccountSnapshot` records observed/preserved/defaulted/unknown/uncertain provenance, strips `openid` from its normalized payload, computes a stable build fingerprint, and stores its canonical profile as immutable JSON so callers cannot mutate the build after the fingerprint is established.

Default policy is `unknown_policy="error"`: a missing simulation-affecting field blocks `GrowthProfile` creation instead of silently inheriting Moris fixed-build values. `unknown_policy="moris-default"` is an explicit opt-in fallback and still retains unknown provenance. Solo Raid level 400 is recorded as an intentional policy default. Cube data from sync is treated as an equipped-cube lower-bound observation and cube choice remains a separate case/default axis.

The strict normalization specifically checks missing skill subfields, all four equipment parts, overload fields, account console, sync-mode synchro level, and `favorite_stage` for characters whose current canonical data has favorite-item skill revisions. Legacy per-character `level`/`cube` fields are rejected so they cannot bypass the normalized policy.

`MorisEvaluator.from_moris_snapshot()` binds one snapshot through the existing `GrowthProfile → build_squad → build_config → simulate` path and uses `snapshot_id` as evaluator cache identity.

### Synthetic profile-sync E2E fixture

- roster: `리타 / 크라운 / 홍련 / 앨리스 / 모더니아 / 나가`
- tested team: `리타 / 크라운 / 홍련 / 앨리스 / 모더니아`
- refinement neighbor: `리타 / 크라운 / 홍련 / 앨리스 / 나가`
- duration: 30 s
- enemy DEF: 31,784
- RNG: `expected`
- seed: 42
- two snapshots: synthetic invested build vs the same fixture with only Alice reduced to skills 1/1/1, affinity 1, no equipment, and no collection item

| measurement | invested snapshot | weak-Alice snapshot |
| --- | ---: | ---: |
| snapshot id | `acct-e46722a42f5968efcabe668b` | `acct-06857f9b028afb6b18a5da44` |
| direct Moris team score | 141,194,861 | 135,391,386 |
| snapshot-bound candidate score | 141,194,861 | 135,391,386 |
| Naga marginal mean | -6,506,586 | -703,111 |
| one-swap neighbor score | 113,129,883 | 107,326,408 |
| fresh final evaluator score | 141,194,861 | 135,391,386 |
| optimizer evaluator `simulate()` calls | 5 | 5 |
| fresh final evaluator calls | 1 | 1 |

Measured propagation deltas after weakening Alice:

- candidate/full-team score: **-5,803,475**.
- one-swap neighbor score: **-5,803,475**.
- marginal mean changes by **+5,803,475** (equivalently invested-minus-weak marginal delta `-5,803,475`).

Direct Moris and the snapshot-bound evaluator matched exactly in both cases. The fresh final evaluator, created separately with cache disabled, also matched the selected candidate score exactly. Therefore the same normalized account build is verified to propagate through direct Moris, candidate evaluation, marginal measurement, one-swap refinement, allocation selection, and fresh final re-evaluation.

The immutable-snapshot rerun reproduced every E2E number above exactly. Optimizer unit tests were **40/40** in the final benchmark run.

### Standard CI on immutable-snapshot head

Actions run `33318423434` completed successfully:

- calculator engine: 137 tests passed, 1 skipped, 31.854 s.
- optimizer: 40 tests passed in 0.032 s.
- bridge: 31 tests passed, 1 skipped, 27.348 s.
- browser: 24 files / 385 tests passed, 29.07 s total vitest duration.
- golden snapshot: 29/29 passed.
- doclint and calculator damage cross-checks passed.

Temporary draft PRs #8 and #9 were closed without merge. Their temporary benchmark workflow commits were removed from `roster-optimizer-prototype` history after the measured runs.

### Remaining production-scale measurement

A true 50–80-character **actual account** benchmark is still `TBD`. The repository intentionally excludes private `profiles/`, and no private account profile was committed or substituted with a guessed/max build for this measurement.

When a gitignored real profile is available, large-roster metrics should be simulate-call count, runtime, refinement gain, five-team allocation gain/stability, and seed sensitivity. True recall cannot be claimed for the full 50–80 roster because exhaustive truth is intractable; retain exhaustive recall on tractable real-build subsets cut from that same account snapshot. Expand pair/core probing only if those measurements expose a concrete failure. Meta-Aware scoring remains deferred until this production-scale account validation is complete.

## Audited profile-scale preparation 2026-08-30

This milestone prepares the real 50–80-character measurement path. It deliberately adds **no new search heuristic** and records no fabricated/max-build production result.

Baseline:

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- session start HEAD: `32dcbeb3e13c7135317a5e9524b10bf05378176b`
- implementation/test head before these docs: `ac4177420254f0d540972933b7c5079485f75976`
- Moris upstream / merge base: `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- private profile/raw account data committed: none
- calculator/site/scraper source changed in this milestone: none

### Raw-sidecar audit gap found

Inspection of canonical `scraper/profile_fetch.py` found information that a calculator-facing profile alone cannot prove. Examples include an equipped overload `function_type` unknown to `FUNC_TO_EQUIP`, an equipped option id missing from the returned `state_effects` dictionary, unknown collection/favorite mapping, owned-character name mapping loss, and console freshness/preservation. Some of these are currently reported only through sync-time warnings, while the normalized profile may otherwise look numerically complete.

`optimizer/account_bundle.py` therefore adds a read-only `profile + raw sidecar` audit layer without changing the profile format or duplicating raw API parsing. It reuses `profile_fetch.py`'s canonical overload mapping/table helpers. `AuditedAccountSnapshot` keeps the calculator-facing profile as the only build payload sent to Moris while raw data contributes provenance and fail-closed checks.

Strict audit records/blocking behavior includes:

- raw characters/details/profile roster-count and `name_code` consistency;
- profile/raw account-area identity mismatch;
- missing raw `state_effects` dictionary for equipped overload option ids;
- unmapped equipped overload function types as `unknown`;
- known overload values outside the local option-level table as `uncertain` rather than silently observed;
- raw non-empty collection count that disagrees with normalized collection stages;
- raw affinity 0 → calculator affinity 1 as an explicit policy default;
- legacy console values without a freshness marker as `uncertain`, not freshly `observed`.

The audited snapshot identity includes simulation-affecting audit provenance while excluding non-simulation bookkeeping such as `_unsynced`, so cache identity changes for meaningful uncertainty but not for an explanatory sync-slot flag.

### Five-team allocation/refinement orchestration

`optimizer/pipeline.py` adds orchestration around existing primitives only:

1. rebuild every supplied candidate score through the current snapshot-bound evaluator, ignoring stale `simulated_score` values;
2. run the existing exact candidate-pool global allocator;
3. use the currently selected allocation teams as one-swap seeds;
4. generate only the caller-specified incoming/position/budget neighborhood;
5. evaluate those neighbors with the same evaluator;
6. merge them into the evaluated pool and rerun exact global allocation.

No roster-wide candidate discovery rule, pair score, RoleFit score, or meta rule was added. `tests/benchmark_optimizer_account_scale.py` is a local-only driver that accepts gitignored `profile`, `raw`, and an explicit plan. It reports marginal/candidate/refinement simulate calls, cache hits, timings, initial/refined five-team totals, refinement gain, and a fresh cache-disabled final re-evaluation. Its dry-run reports audit state without combat simulation. Full-roster recall is explicitly `null` because no exhaustive oracle exists at production scale.

### Verification

CI run `33320142542` on `ac417742...`:

- first attempt: engine, optimizer and bridge passed; one pre-existing `site/src/ui.test.ts` timing-sensitive assertion failed (`simulateCalls` 1 vs 0) while its validation error text was correct;
- no site/runtime/calculator source differed from upstream because of this milestone;
- the same job was rerun with no code change and completed successfully.

Successful rerun measurements:

- calculator engine: **137 passed, 1 skipped**, 28.858 s;
- optimizer: **59 passed**, 0.121 s;
- bridge: **31 passed, 1 skipped**, 24.816 s;
- browser: **24 files / 385 tests passed**, vitest duration 21.73 s;
- golden snapshot: **29/29 passed**;
- doclint and calculator damage cross-checks passed.

The first browser failure is therefore recorded as a non-reproducing flaky test event, not hidden or treated as an optimizer regression.

### Production-scale values still TBD

No actual private 50–80-character account was available inside GitHub/Actions, so the following remain **TBD**:

- real roster count used for benchmark;
- marginal/candidate/refinement `simulate()` call budget;
- wall-clock runtime;
- initial five-team total;
- one-swap refinement gain;
- re-global-allocation gain/stability;
- tractable real-build subset recall/optimum survival.

The next measurement must use the real gitignored `profiles/<name>.json` and matching `.raw.json`; it must not substitute maximum/default build values for missing sync data. Pair/core expansion remains failure-driven, and Meta-Aware scoring remains deferred.