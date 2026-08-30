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

### Failure interpretation and next experiment

The failure is consistent with two distinct proxy limitations that should be tested separately:

1. additive marginal values can over-rank teams whose individual members look valuable but whose cheap burst-role structure is inefficient;
2. additive marginals cannot represent pair/core interaction by construction.

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

Do **not** promote this RoleFit into production optimizer scoring yet. It is useful as a diagnostic of structural false positives, but the observed recall failure remains after those teams are demoted. The next experiment should target context-sensitive pair/core interaction implicated by the saved failure case, without measuring all character pairs.
