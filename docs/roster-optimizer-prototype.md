# Roster optimizer prototype

## Scope

This branch keeps the Moris calculator engine unchanged.  The optimizer is a separate Python package and treats Moris as an expensive evaluator.

The browser bridge establishes the canonical call path:

1. `context.spec.build_squad(names, character_overrides)`
2. `context.spec.build_config(squad, config)`
3. `calculator.timeline.simulate(squad, config=..., enemy=..., seed=..., verbose=...)`

`optimizer/evaluator.py` is the only optimizer module that binds to those callables.  Search modules can therefore be reviewed or moved without importing browser/Pyodide code.

## Evaluator defaults

- `rng_mode`: `expected`
- `immune_blocks_burst`: `True` when not supplied (matching the browser bridge)
- `verbose`: `False`
- exact-request cache: enabled
- squad order is part of the cache key because it can affect burst priority/operation

The adapter counts `simulate()` calls and separately records build/simulate wall time.  This lets later experiments optimize for both solution quality and evaluator budget.

## Benchmark

Baseline branch HEAD before optimizer work: `fb2fd9157aa14499daf6b9f185beb685d4393f90`.

Measured on GitHub Actions `ubuntu-24.04`, CPython 3.13.15, with lazy data caches warmed.  Representative 5-person squad: `리타 / 크라운 / 홍련 / 앨리스 / 나가`; 180 s fight; enemy DEF 31,784; RNG mode `expected`; seed 42.

| operation | result |
| --- | ---: |
| `build_squad` | median 0.624 ms (20 runs) |
| `build_config` | median 0.003 ms (20 runs) |
| `simulate(verbose=False)` | 2.675102 s |
| `simulate(verbose=True)` | 2.838826 s |
| verbose overhead | +0.163724 s / +6.12% |

Both simulation runs produced the same squad total (`1,428,044,008`) and 19,195 hits.  `verbose=False` returned no log; `verbose=True` returned a log.

Implication: optimizer runtime is dominated by `simulate()`.  Building objects is negligible at this scale, and optimizer evaluation should stay on `verbose=False` unless diagnostics require logs.


## Existing optimizer-related code

The repository already has `.agent/skills/report-squad/scripts/optimize_solo_raid.py`. It exactly solves weighted set packing over **already calculated report candidates**, but its optimization mode does not discover or simulate new squads. The new `optimizer/` package therefore focuses on the missing upstream problem: roster-aware candidate discovery under a strict `simulate()` budget, then global allocation over the evaluated pool.

## Skeleton responsibilities

- `constraints.py`: cheap structural hard constraints plus pluggable Moris-backed validators.  Burst/cooldown semantics are deliberately not duplicated yet.
- `marginal.py`: reference-team one-member substitution measurements for proxy features.
- `candidates.py`: candidate representation and diversity-preserving proxy filtering.
- `global_search.py`: exact weighted set packing **within the evaluated candidate pool**, with no character overlap.

The last point is the intended difference from sequential team-1-to-team-5 greedy locking.  Candidate generation may be heuristic, but once teams have been evaluated their five-team allocation is solved globally over that pool.

## Next experiment gate

Do not add more heuristics until a small synthetic/exhaustive harness exposes a concrete failure.  The next stage should measure:

- optimal-team survival rate after proxy filtering
- Top-N recall
- final 5-team damage / exhaustive optimum
- actual `simulate()` calls
- wall time

Any fix should be tied to an observed failure and the failing roster should become a regression case.
