# Deferred optimizer performance options

Status: memo only. Do not implement before the optimizer search policy and same-budget benchmarks are sufficiently complete.

## Why this exists

The Moris combat engine is intentionally detailed and relatively expensive. The roster optimizer may eventually require hundreds or thousands of squad evaluations, so evaluator cost can become a practical bottleneck even if the search policy itself is good.

Performance work should be driven by measured end-to-end optimizer benchmarks, not done preemptively while the search algorithm is still changing.

## Preferred order of investigation

1. **Finish the optimizer algorithm first.**
   - establish candidate discovery, seeds, reversible Cold handling, refinement, and strict same-budget Pure-vs-Meta comparison;
   - measure actual Moris call counts, wall time, memory, and final five-team quality.

2. **If Moris call cost is the bottleneck, test a score-only Moris path.**
   - keep the same combat semantics and damage calculations;
   - optimizer already uses `verbose=False`, so SimLog/buff timeline logging is normally absent;
   - first optimization target is retaining/ordering analysis output that the optimizer does not need, especially the full `SimResult.hits` history and final hit sorting;
   - preserve transient combat information when it is required for gating, lifesteal, damage accumulation, triggers, or other mechanics;
   - require score-only and full Moris to reproduce identical `squad_total` (and preferably `char_total`) across broad regression fixtures before using the path for search.

3. **Only if score-only Moris is still too expensive, consider a separate lightweight prefilter engine.**
   - lightweight engine purpose: cheap candidate ranking / elimination only;
   - Moris remains the authoritative evaluator for shortlisted candidates and final refinement;
   - conceptual pipeline:

     `cheap engine -> broad candidate selection -> Moris precise evaluation/refinement -> exact evaluated-pool allocation`

   - the lightweight engine must never become the final damage authority.
   - benchmark candidate recall aggressively, because approximation error at this stage can remove teams that exact Moris allocation can no longer recover.
   - prefer conservative/high-recall filtering over aggressive pruning.

4. **Other later options**
   - batch evaluation rounds;
   - parallel/browser `CalculatorPool` workers;
   - cache/reuse improvements where identity remains safe;
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

This memo does not authorize calculator-engine changes now. It records performance escape hatches to revisit only after algorithm construction and benchmarking establish that evaluator cost is a real limiting factor.
