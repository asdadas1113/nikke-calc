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

The runtime numbers above only verify that the harness ran; they are too small and synthetic to predict Moris optimizer wall time. Real-roster exhaustive and Moris-call measurements remain TBD.
