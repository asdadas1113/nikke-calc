# Deferred optimizer performance options

Status: optimizer-layer raw-result retention measured and addressed; calculator-engine performance changes remain deferred.

## Why this exists

The Moris combat engine is intentionally detailed and relatively expensive. The roster optimizer may eventually require hundreds or thousands of squad evaluations, so evaluator cost can become a practical bottleneck even if the search policy itself is good.

Performance work should be driven by measured end-to-end optimizer benchmarks, not done preemptively while the search algorithm is still changing.

## Resolved optimizer-layer cache issue

`MorisEvaluator` previously cached the complete `SimResult` for every evaluated squad through `Evaluation.raw`. A representative 180-second result contains about 19,195 `HitEvent` objects, so retaining hundreds of results can dominate process memory even though optimizer search only needs `squad_total`.

A fresh-process synthetic-retention benchmark using the real `SimResult` and `HitEvent` classes measured the following at 500 unique cached evaluations with 19,195 hits per result:

| evaluator policy | RSS start | RSS end | RSS growth | growth / evaluation |
| --- | ---: | ---: | ---: | ---: |
| production `retain_raw=False` | 22,492 KiB | 27,060 KiB | 4,568 KiB | 9.136 KiB |
| diagnostic `retain_raw=True` | 22,484 KiB | 1,908,632 KiB | 1,886,148 KiB | 3,772.296 KiB |

Earlier 50/100/200-point measurements showed the raw-retention cost was essentially linear at about 3,770 KiB per cached evaluation. The score-only-retention process stayed roughly flat after allocator warm-up.

Decision:

- optimizer `MorisEvaluator` defaults to `retain_raw=False`;
- fresh and cached `Evaluation.raw` are both `None` under that default;
- `retain_raw=True` is an explicit diagnostics-only opt-in that preserves the former full-result behavior;
- Moris still executes the normal simulator and constructs its normal result transiently, so this changes optimizer retention only, not combat math or simulation semantics;
- no calculator-engine score-only path is authorized by this measurement.

The production-policy benchmark and the full optimizer test suite were rerun after the change. 353 optimizer tests passed, and the production 500-entry RSS result above reproduced the expected flat-retention behavior.

## Preferred order of further investigation

1. **Finish the optimizer algorithm and transfer validation.**
   - establish candidate discovery, seeds, reversible Cold handling, refinement, and strict same-budget Pure-vs-Meta comparison;
   - measure actual Moris call counts, wall time, memory, and final five-team quality across the transfer account set.

2. **If Moris call cost is still the bottleneck, test a score-only Moris path.**
   - keep the same combat semantics and damage calculations;
   - optimizer already uses `verbose=False`, so SimLog/buff timeline logging is normally absent;
   - first optimization target is work that the optimizer does not need after damage is known, especially the full `SimResult.hits` history and final hit sorting;
   - preserve transient combat information when it is required for gating, lifesteal, damage accumulation, triggers, or other mechanics;
   - require score-only and full Moris to reproduce identical `squad_total` (and preferably `char_total`) across broad regression fixtures before using the path for search.

3. **Only if score-only Moris is still too expensive, consider a separate lightweight prefilter engine.**
   - lightweight engine purpose: cheap candidate ranking / elimination only;
   - Moris remains the authoritative evaluator for shortlisted candidates and final refinement;
   - conceptual pipeline:

     `cheap engine -> broad candidate selection -> Moris precise evaluation/refinement -> exact evaluated-pool allocation`

   - the lightweight engine must never become the final damage authority;
   - benchmark candidate recall aggressively, because approximation error at this stage can remove teams that exact Moris allocation can no longer recover;
   - prefer conservative/high-recall filtering over aggressive pruning.

4. **Other later options**
   - batch evaluation rounds;
   - parallel/browser `CalculatorPool` workers;
   - additional cache/reuse improvements where identity remains safe;
   - only after profiling shows the relevant bottleneck.

## Decision rule

Do not choose an optimization path from intuition alone. After the search algorithm is stable enough, profile the real workload and compare alternatives on:

- final five-team damage under an equal Moris-call budget;
- wall-clock runtime;
- peak memory;
- Moris calls saved or accelerated;
- candidate/optimum survival on tractable oracle fixtures;
- reproducibility versus the full Moris path.

If the normal Moris evaluator is already fast enough for the intended search budget, leave the engine untouched.

## Boundary

The measured cache-retention change is intentionally confined to the optimizer evaluator. This document does not authorize calculator-engine changes. Deeper performance escape hatches remain deferred until account-scale transfer benchmarks show that evaluator CPU cost, rather than search policy, is the practical limiting factor.
