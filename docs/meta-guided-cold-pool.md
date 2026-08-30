# Meta-guided cold-pool design draft

Status: design candidate only. This document supplements `docs/roster-optimizer-prototype.md`. Numeric usage thresholds, restoration batch sizes, exploration budgets, promotion thresholds, and mode presets remain **TBD pending data and benchmarks**.

## Purpose

Meta-guided search may defer characters with strong evidence of both low Solo Raid usage and no permanent Overload investment so that expensive Moris `simulate()` calls can be spent where they are more likely to improve the final five-team allocation. Cold filtering is a reversible search-budget policy, not hard legality, and external meta data must not alter Moris damage scores.

The conservative cold-eligibility rule remains:

`cold_eligible = low_usage AND overload_piece_count == 0`

If Overload state is `unknown`, `uncertain`, or otherwise not proven to be zero by account-sync provenance, it must **not** be treated as zero. Usage-based cold filtering fails open for that character.

## Primary and cold pools

`Primary` means the characters receiving normal candidate-discovery budget at the start of a run. `Cold` means characters temporarily deferred by the meta-guided filter. Neither label is a statement that a character is objectively strong or weak.

Characters protected by explicit user intent (`Priority review` or `Force include`) bypass the cold filter. Current displayed level, Synchro Device membership, and combat power remain forbidden as pruning evidence.

## Incremental cold restoration

If the Primary pool cannot support five non-overlapping structurally legal teams, do not restore the entire Cold pool at once. Restore a small deterministic batch, rerun the cheap feasibility check, and repeat until structural feasibility is recovered or the Cold pool is exhausted.

The first restoration policy should stay auditable rather than hide a guessed composite score. Candidate evidence may be ordered lexicographically by:

1. **structural role deficit** — restore characters that can repair the currently scarce burst/support structure first;
2. **usage-boundary proximity** — among otherwise comparable cold characters, prefer those closest to the eventual low-usage boundary rather than the deepest tail;
3. **recent or boss-specific evidence** — prefer characters with credible recent/niche Solo Raid evidence over equally cold characters with no such signal;
4. stable canonical/input order as the final tie-break.

Exact role definitions, usage cutoffs, recent/boss evidence rules, and restoration batch size are TBD and require empirical validation. Do not introduce a weighted restoration score until evidence shows that the simpler ordered policy fails.

## Cold exploration even when Primary is feasible

Primary structural feasibility is not proof that every useful cold character has been safely deferred. If the Cold pool is non-empty, reserve a small explicit **cold exploration budget** inside the same whole-search `SearchBudget`, even when Primary alone can already form five teams.

The exploration budget must be bounded and caller-owned; its exact size is TBD. It should sample only a small number of cold characters/contexts, with selection biased toward boundary, niche, scarce-role, or diversity evidence rather than exhaustive cold search.

A cold character that produces strong **actual Moris evidence** during exploration may be promoted into the Primary search for the remainder of that run. Because marginal contribution is context-sensitive, one high marginal observation is a trigger for additional candidate evaluation, not a permanent global character classification and not a guarantee of final selection. Promotion should be run-local unless later repeated evidence justifies a separate durable policy.

## Reinvest saved simulation budget

Cold filtering is useful only if the saved evaluator budget improves solution quality or latency. Saved calls should remain available inside the same total search budget instead of being silently discarded.

Initial reinvestment priority should be conservative:

1. broader candidate diversity / multi-view candidate preservation;
2. bounded one-swap refinement and re-global-allocation;
3. scarce-support or structural-bottleneck variants when the current allocation exposes them;
4. selective context-specific pair probes only when a measured failure or concrete hypothesis justifies them;
5. restricted two-swap refinement only after one-swap/candidate-diversity evidence shows a remaining miss, with an explicit small cap.

This does **not** authorize all-pairs synergy, unrestricted two-swap enumeration, or automatic spending on every listed mechanism. Pair and two-swap work remain failure-driven extensions.

## Same-budget evaluation against Pure Sim

The main comparison between Meta-guided and Pure Sim must use the **same total number of new Moris `simulate()` calls** (and the same engine/account/boss/cache identity). Comparing a cheaper Meta-guided run against a larger Pure Sim run would not answer whether cold filtering improves budget allocation.

Primary quality metric:

`same-budget damage delta = final Meta-guided five-team damage - final Pure-Sim five-team damage`

Also record runtime and stage-level call allocation, but do not replace the same-budget final five-team comparison with proxy recall alone. Exact global set packing remains exact only inside each evaluated candidate pool.

## Benchmark and diagnostic metrics

At minimum record:

- owned roster size;
- initial Primary count;
- initial Cold count;
- cold characters restored for structural feasibility;
- cold characters actually explored;
- cold characters promoted for further search;
- `simulate()` calls by marginal / candidate / cold-exploration / refinement / selective-extra stage;
- final five-team damage;
- same-budget damage delta versus Pure Sim;
- provenance/version of the Solo Raid usage snapshot and account build snapshot.

`false_deferred` must not be reported as known on a production-sized roster without a suitable oracle or stronger reference search. On tractable exhaustive fixtures it may mean a cold-deferred character that belongs to the known optimum or whose deferral causes a measured optimum/Top-N loss. On large non-exhaustive runs, report narrower observable quantities such as `restored`, `explored`, `promoted`, and `recovered-deferred` instead of pretending the true false-deferred count is known.

A priority-review or cold-exploration case that promotes a previously deferred character into a better final allocation is valuable regression evidence, but it is evidence of a search miss under that configuration, not proof of a universal character rule.

## Non-goals for the first implementation

- No fixed low-usage percentage until multi-season Enikk distribution/coverage work is complete.
- No level/Synchro/combat-power pruning.
- No unknown Overload => zero coercion.
- No meta bonus added to Moris damage.
- No permanent promotion from one favorable marginal context.
- No all-pairs synergy search.
- No unrestricted two-swap search.
- No claim of global optimality outside exhaustive small fixtures.
