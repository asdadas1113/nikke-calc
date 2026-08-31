# Roster optimizer prototype

## Scope

This branch keeps the Moris calculator engine unchanged.  The optimizer is a separate Python package and treats Moris as an expensive evaluator.

The browser bridge establishes the canonical call path:

1. `context.spec.build_squad(names, character_overrides)`
2. `context.spec.build_config(squad, config)`
3. `calculator.timeline.simulate(squad, config=..., enemy=..., seed=..., verbose=...)`

`optimizer/evaluator.py` is the only optimizer module that binds to those callables.  Search modules can therefore be reviewed or moved without importing browser/Pyodide code.

### Branch boundary

`master` remains the Moris-fork baseline. Optimizer experiments and policy work stay on `roster-optimizer-prototype`; this branch is not intended to be merged into `master` as a whole. Keep optimizer behavior inside the isolated `optimizer/` package and use evaluator/adapter boundaries for Moris integration. Changes to calculator/site/scraper source should be avoided unless a separately justified compatibility fix requires them.

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

## Proposed meta-guided roster filtering and user review controls

This section records a candidate design only.  It is not yet an implemented optimizer policy, and numeric low-usage thresholds remain **TBD pending data inspection and benchmarks**.

### Motivation

The main runtime bottleneck is expensive Moris `simulate()` calls.  Large accounts can own far more characters than they have permanently invested in, so spending equal marginal/search budget on every owned character may be wasteful.  The proposed default experience is therefore a **meta-guided search** that may temporarily move very unlikely candidates into a reversible cold pool before expensive evaluation.  Moris simulation remains the truth for teams that are actually evaluated.

Because external raid usage affects which characters receive search budget, this is explicitly meta-guided behavior rather than pure simulation.  A pure-simulation path must remain available, and meta-guided filtering must relax or fall back when it prevents a viable five-team search.

### Initial external data scope

For the MVP, external usage evidence should be limited to **Solo Raid** data, with Enikk as the current leading source candidate.  Union Raid data is deliberately excluded from the initial rule so that a Solo Raid optimizer is not biased by a different mode.  Union Raid may be investigated later only if real false-negative cases show that it adds useful protection or diagnostic evidence.

The exact definition of `low_usage` is intentionally unresolved.  Do **not** hard-code an arbitrary percentage threshold yet.  Before choosing a rule, inspect multiple recent Solo Raid seasons, coverage, character release timing, observed usage distribution, and niche characters that spike on specific bosses.  Missing or insufficient data should fail open rather than being treated as low usage.

### Draft usage-evidence window and refresh policy

The first data study should compare **6-, 8-, and 10-completed-season windows**, with eight seasons only as the initial experiment center, not a production rule.  The goal is to identify characters that stay near the usage floor across different bosses while preserving niche characters that show a meaningful spike in at least one season.  Prefer peak/recency/coverage evidence over a single average usage number.

A tentative per-character evidence record may include `eligible_seasons`, `observed_seasons`, `peak_usage`, `meaningful_seasons`, `seasons_since_meaningful_use`, reporting-floor/missing observations, and a final `used / low / insufficient` classification.  Exact thresholds for meaningful usage, minimum eligible seasons, and the reporting-floor interpretation are all **TBD**.

Refresh the stable meta snapshot after a Solo Raid season is complete and its external aggregate is considered stable.  Runs during an active season should keep using the previous stable snapshot rather than allowing live usage to move the pruning boundary.  Meta snapshot/version provenance should record the latest incorporated completed Solo Raid season.  Fetch/update failure must retain the last known-good snapshot or fall back to Pure Sim; it must never turn missing source data into zero usage.

Usage eligibility must be **meta-epoch aware**, not release-date-only.  For each character, the valid history starts at the most recent clearly material change that can make older usage evidence stale: initial release is one epoch event, and major favorite-item/skill revisions or other clearly identified operation-changing changes may start a new epoch.  Only completed Solo Raid seasons for which the character was fully eligible after that epoch may enter the low-usage window.  If the epoch is unknown/uncertain, the raid schedule is incomplete, or fewer than the required completed seasons exist after the epoch, classify the character as `insufficient` and keep it in Primary.  This is an evidence-validity gate only; epoch information must never add or subtract Moris damage.

### Cold-pool eligibility

The proposed conservative eligibility rule is:

`cold_eligible = low_usage AND overload_piece_count == 0`

Both conditions are required.

- Any character with **at least one Overload equipment piece** is protected from this usage-based cold filter.  Overload is treated as a strong signal of permanent account investment.
- `overload_piece_count == 0` does **not** itself mean that a character is weak or unused; it only makes the character eligible for the separate low-usage check.
- A low-usage character with account investment remains searchable.
- A zero-Overload character with meaningful Solo Raid usage remains searchable.

The first implementation should prefer this simple, auditable rule over a guessed composite investment score.  Additional protection signals such as unusually high skill/favorite investment may be considered later only after measured false-negative cases justify them.

### Signals that must not be used for pruning

Current displayed character level, Synchro Device membership, and current combat power must **not** be pruning evidence.

A character can appear as level 1 simply because it is not currently assigned to the Synchro Device and can become usable immediately when assigned.  Combat power also inherits level effects and would reintroduce the same bias indirectly.  Solo Raid evaluation should continue to use the explicit level policy already owned by the calculator/profile layer rather than treating current UI level as account investment.

### Reversible relaxation and beginner accounts

Cold filtering is a search-budget policy, not hard legality.  Characters moved to the cold pool must remain recoverable.

After initial filtering, perform a cheap structural check before expensive simulation.  If the active pool cannot support five non-overlapping structurally legal teams, restore cold characters until the requirement can be met.  Merely reaching 25 characters is not sufficient because burst structure can still make five legal teams impossible.

This naturally weakens filtering for beginner accounts:

- mature/wide roster: potentially substantial cold filtering,
- smaller roster: partial restoration,
- very small roster: filtering may effectively disappear,
- fewer than 25 owned characters: five complete non-overlapping teams are mathematically impossible and should be reported as such rather than blamed on filtering.

If meta filtering must be relaxed until it is effectively absent, record the run as a pure-simulation fallback (or equivalent provenance) rather than pretending that meaningful meta filtering occurred.

### Search modes and provenance

Current proposed user-facing/default behavior:

- **Meta-guided**: default; may use Solo Raid usage evidence plus the zero-Overload condition to cold-filter candidates.
- **Meta-guided / relaxed**: meta filtering started active but cold candidates had to be restored for structural viability or search coverage.
- **Pure Sim**: external usage data does not remove candidates from the search space; should remain available as an advanced/manual choice and as an automatic fallback when required.

External usage data should affect candidate search allocation only.  It must not silently add damage bonuses or otherwise alter Moris scores.  Final allocation among actually simulated candidates remains based on Moris evaluation and exact set packing over the evaluated pool.

### User candidate controls

Keep explicit user intent above meta filtering.  Proposed states are:

- **Normal**: use the ordinary search policy.
- **Priority review**: do not force the character into the final allocation, but guarantee meaningful search/evaluation attention.  This state bypasses cold filtering.
- **Force include**: final result must include the requested character subject to the explicit hard constraint semantics.
- **Force exclude**: character is excluded from search by explicit user request.

`Priority review` exists to answer a question that force-inclusion cannot answer: “I think this character should be strong; did the optimizer simply fail to examine it?”  It should guarantee evaluation opportunity without giving the character a score bonus.  Candidate-generation details and exact review budget remain TBD and should be benchmarked rather than guessed.

A useful diagnostic is to compare, within the already evaluated candidate pool, the best unrestricted global allocation against the best allocation requiring the priority-reviewed character.  This can distinguish “examined but not selected” from “additional review exposed a missed strong candidate,” while still avoiding claims of global optimality outside the evaluated pool.

### Optional diagnostic logging

If a user explicitly opts in, priority-review outcomes could become valuable optimizer-quality data.  In particular, a character absent from the normal search result but entering the final five teams after priority review is a concrete candidate-generation false-negative worth preserving as a regression case.

Logging should be opt-in, minimize collected data, avoid account identifiers/raw profiles by default, and record both successful and unsuccessful priority reviews to avoid selection bias.  Useful aggregate/provenance fields may include optimizer/engine version, search budget, active/cold counts, whether the reviewed character had been cold-filtered, additional simulation calls, final-selection outcome, score delta, and search-stage provenance.  Any expansion into detailed build data should require a demonstrated analytical need and a separate privacy review.
