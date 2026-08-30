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

## Exhaustive validation

- synthetic exhaustive harness: TBD
- true optimum survival: TBD
- Top-N recall: TBD
- final allocation / exhaustive optimum: TBD
- optimizer evaluator calls: TBD
- runtime: TBD
