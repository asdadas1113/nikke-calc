# Meta-guided cold-pool design draft

Status: implementation/design candidate. This document supplements `docs/roster-optimizer-prototype.md`. A first **benchmark candidate** for low-usage classification exists from public Enikk backtesting. Structural restoration and a score-blind bounded Cold-exploration planner are implemented, but the usage preset, restoration batch size, exploration quota, promotion threshold, and final mode presets remain **caller-owned/TBD pending same-budget Moris benchmarks**.

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

The implemented restoration policy stays auditable rather than hiding a guessed composite score. Candidate evidence is ordered lexicographically by:

1. **structural role deficit** — restore characters that improve complete-team/required-role coverage first;
2. **member deficit repair** — prefer additions that repair total team-member supply;
3. **usage-boundary proximity** — among otherwise comparable Cold characters, prefer those closest to the supplied low-usage boundary rather than the deepest tail;
4. **recent or boss-specific evidence** — prefer characters with credible niche evidence over otherwise equal Cold characters;
5. stable Cold/input order as the final tie-break.

The restoration batch size remains a required caller input. No weighted restoration score is used.

## Public Enikk usage evidence and provisional boundary candidate

Public Enikk `SRRankings` data for Solo Raid seasons 21–40 was inspected with no private account/profile data. Ranking coverage was 298–300 players per season, so one observed player corresponds to roughly 0.33% usage. Character names are joined through resource id; ambiguous external labels such as `Rei` and `Sakura` are excluded rather than guessed.

The historical study originally used first-positive observations as a conservative proof that a character existed by a season. The implementation now records that evidence separately from production meta-epoch evidence: a first positive can establish historical availability for later backtest windows, but it cannot prove that no later favorite-item/balance/operation-changing event reset the character's usage history. Production Cold classification still requires an independently validated meta epoch and fails open when that epoch is missing or uncertain.

Rolling lower-tail inspection showed that a short six-season window forgets old niche/rework evidence quickly, while ten seasons is substantially stickier. A one-step historical backtest then asked: if a character's **maximum** usage over the previous 6/8/10 seasons had stayed below a candidate boundary, how much was that same established character used in the next Solo Raid season?

Key usage-only backtest results across S21–S40:

| lookback | historical peak boundary | candidate-season cases | next season >=5% | next season >=10% | max next-season usage |
| --- | ---: | ---: | ---: | ---: | ---: |
| 6 seasons | <=0.35% | 250 | 6 | 6 | 85.0% |
| 6 seasons | <=1.00% | 277 | 9 | 8 | 99.7% |
| 8 seasons | <=0.35% | 171 | 0 | 0 | 1.0% |
| 8 seasons | <=1.00% | 190 | 0 | 0 | 1.0% |
| 8 seasons | <=2.00% | 209 | 2 | 2 | 99.7% |
| 10 seasons | <=1.00% | 135 | 0 | 0 | 0.0% |
| 10 seasons | <=2.00% | 147 | 0 | 0 | 1.0% |

This rejects six seasons as the first production candidate: even the 0.35% lower tail contained large next-season breakouts. It also shows a sharp observed difference around the 8-season 1–2% boundary: `<=1%` had no >=5% next-season breakout in 190 candidate-season observations, while `<=2%` included two very large breakouts. Ten seasons is safer in this sample but retains historical evidence longer and therefore reduces pruning headroom.

The first benchmark candidate is therefore:

`low_usage_candidate = complete 8-season post-epoch window AND peak_usage <= 1%`

This is **not a locked production default**. `LowUsagePolicy` is a required caller input; the primitive does not silently instantiate 8/1. The public backtest measures usage-only breakout risk, while the real Cold rule is stricter because a character must also have **proven OL0**. Missing season coverage, uncertain meta epoch, ambiguous name mapping, or other missing evidence must fail open and protect the character.

Do not infer that 1% is an intrinsic game-strength boundary. It is an empirical search-budget candidate for this Enikk interval and must be versioned with the usage snapshot. Re-run the study as more seasons accumulate or if the Enikk sampling population changes materially.

## Cold exploration even when Primary is feasible

Primary structural feasibility is not proof that every useful Cold character has been safely deferred. `plan_cold_exploration()` now provides a bounded, score-blind selection step for still-deferred Cold members even when Primary alone can already form the required teams.

The exploration quota is required caller policy and may be zero. For a positive quota the planner greedily orders only **where to look**, not expected damage:

1. cover the currently scarcest required structural role first;
2. then prefer smaller distance from the supplied low-usage boundary;
3. then recent/boss-specific evidence;
4. then stable Cold/input order.

Role supply is updated after each pick, which spreads a small quota across scarce roles instead of repeatedly selecting the same structural niche. The output is only a temporary `search_roster = restored_active + selected_cold`; original Cold classification is retained.

`prepare_meta_guided_search_roster()` now wires the full pre-search path:

`meta epoch usage -> OL evidence -> Primary/Cold -> structural restoration -> bounded Cold exploration`

It performs no Moris evaluation and gives selected Cold members no bonus. A caller can pass the resulting temporary search roster into the existing budgeted anytime search while the remaining Cold members stay deferred.

A Cold character that later produces strong **actual Moris evidence** may justify additional run-local attention, but the promotion trigger/threshold is intentionally not implemented yet. One favorable marginal context must not become a permanent global classification or a forced final selection.

## Reinvest saved simulation budget

Cold filtering is useful only if the saved evaluator budget improves solution quality or latency. Saved calls should remain available inside the same total search budget instead of being silently discarded.

Initial reinvestment priority should remain conservative:

1. broader candidate diversity / multi-view candidate preservation;
2. bounded one-swap refinement and re-global-allocation;
3. scarce-support or structural-bottleneck variants when the current allocation exposes them;
4. selective context-specific pair probes only when a measured failure or concrete hypothesis justifies them;
5. restricted two-swap refinement only after one-swap/candidate-diversity evidence shows a remaining miss, with an explicit small cap.

This does **not** authorize all-pairs synergy, unrestricted two-swap enumeration, or automatic spending on every listed mechanism. Pair and two-swap work remain failure-driven extensions.

## Same-budget evaluation against Pure Sim

The main comparison between Meta-guided and Pure Sim must use the **same total number of new Moris `simulate()` calls** (and the same engine/account/boss/cache identity). Comparing a cheaper Meta-guided run against a larger Pure Sim run would not answer whether Cold filtering improves budget allocation.

Primary quality metric:

`same-budget damage delta = final Meta-guided five-team damage - final Pure-Sim five-team damage`

Also record runtime and stage-level call allocation, but do not replace the same-budget final five-team comparison with proxy recall alone. Exact global set packing remains exact only inside each evaluated candidate pool.

## Benchmark and diagnostic metrics

At minimum record:

- owned roster size;
- initial Primary count;
- initial Cold count;
- Cold characters restored for structural feasibility;
- Cold characters selected for bounded exploration;
- Cold characters actually Moris-evaluated through the exploration path;
- Cold characters given additional run-local attention after actual evidence;
- `simulate()` calls by marginal / candidate / Cold-exploration / refinement / selective-extra stage;
- final five-team damage;
- same-budget damage delta versus Pure Sim;
- provenance/version of the Solo Raid usage snapshot and account build snapshot.

`false_deferred` must not be reported as known on a production-sized roster without a suitable oracle or stronger reference search. On tractable exhaustive fixtures it may mean a Cold-deferred character that belongs to the known optimum or whose deferral causes a measured optimum/Top-N loss. On large non-exhaustive runs, report narrower observable quantities such as `restored`, `selected-for-exploration`, `actually-evaluated`, and `recovered-deferred` instead of pretending the true false-deferred count is known.

A priority-review or Cold-exploration case that recovers a previously deferred character into a better final allocation is valuable regression evidence, but it is evidence of a search miss under that configuration, not proof of a universal character rule.

## Non-goals for the first implementation

- No declaration that the provisional 8-season / 1% boundary is final before same-budget Moris/account validation.
- No hidden default for restoration batch size or Cold exploration quota.
- No level/Synchro/combat-power pruning.
- No unknown Overload => zero coercion.
- No meta bonus added to Moris damage.
- No permanent promotion from one favorable marginal context.
- No all-pairs synergy search.
- No unrestricted two-swap search.
- No claim of global optimality outside exhaustive small fixtures.
