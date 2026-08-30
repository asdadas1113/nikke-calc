# Candidate seeds and meta-epoch validity

Status: optimizer-only design/implementation note for `roster-optimizer-prototype`.

## Invariant

External knowledge may decide **what deserves an evaluator look**. It must not decide **what is strong**.

- Moris `simulate()` remains the score source for every evaluated squad.
- Candidate seeds carry no damage bonus, penalty, or hidden tier value.
- Usage/Overload evidence only allocates search budget; it never changes Moris damage.
- Exact five-team allocation remains exact only inside the actually evaluated candidate pool.

## Candidate-protection channels

### Exact composition seed

`ExactCompSeed` protects one explicitly sourced ordered squad for evaluation when the account owns every member and the squad is hard-legal.

Typical future sources are archived Solo Raid ranking compositions. The interpretation is only:

> this exact composition should receive a real evaluator look if seed budget reaches it.

It is not treated as stronger because a ranker used it.

### Core seed

`CoreSeed` protects a partial member relationship such as a known two- or three-character interaction. It does **not** generate the remaining slots itself. Instead it filters a caller-supplied account-specific candidate universe and protects a bounded number of matching squads.

This is important because copying one ranker's complete five-person squad would also copy that ranker's DPS choices and investment assumptions. A core can preserve the interaction while ordinary account-specific discovery supplies the other members.

Role relationships such as `Crown + healer` should initially be resolved by an external/tag policy into concrete core hypotheses. The optimizer core should not learn healer strength semantics or add role bonuses merely to support a seed.

### External composition order provenance

A five-character array from an external ranking site is **not automatically an ordered squad**. `seed_sources.py` keeps three states explicit:

- `PROVEN_ORDERED`: the source contract independently establishes that serialization/display order is actual NIKKE slot order; only this may become `ExactCompSeed`;
- `MEMBERSHIP_ONLY`: the source intentionally represents only the five members; it becomes a five-member `CoreSeed`;
- `UNKNOWN_ORDER`: the source shows/serializes an array but no reliable contract proves what that order means; it also becomes a five-member `CoreSeed`.

The full-membership CoreSeed is intentional. It protects the observed five-character relationship while allowing the caller's ordinary candidate/placement path to supply an ordered candidate. This layer does not enumerate all 5! placements.

Current Enikk `SRRankings.teams.characters` normalization defaults to `UNKNOWN_ORDER`. The public Enikk Campaign UI explicitly has aggregation modes where identical rosters are grouped with slot order ignored, so array/display order must not be promoted by analogy or assumption. A later source-specific contract can explicitly promote Solo Raid evidence to `PROVEN_ORDERED` if verified.

Likewise, the current public Let's Doro Solo Raid UI clearly exposes ranker squad compositions but no retrieved public contract yet establishes that its five displayed portraits are authoritative in-game slot positions. Treat those compositions as membership evidence until that contract is verified.

Incomplete or ambiguous character mapping is skipped instead of fuzzy-matched. External rank, average damage, use count, or tier information is deliberately absent from the seed-source API and therefore cannot leak into Moris scores or final allocation.

### Cold interaction

A seed may temporarily inspect a Cold character without promoting that character into ordinary Primary search.

`run_anytime_search_round()` therefore allows:

- `roster`: ordinary Primary marginal-search roster;
- `seed_roster`: broader owned roster used only to validate seed ownership;
- `seed_candidate_teams`: small seed-specific candidate stream that may include Cold members.

Actual Moris evidence from the resulting squad is retained like any other evaluated candidate. The character's global Cold/Primary classification is not changed by the seed declaration itself.

## Evaluation ordering

Independent marginal proxy views are preserved separately. Their selected rows are emitted rank-round-robin: every view's rank-1 candidate appears before any view's rank-2 candidate. This avoids consuming a tight downstream Moris budget in view declaration order.

The bounded seed channel and bounded proxy channel are likewise interleaved before full-team evaluation. Duplicate ordered squads are evaluated once. The whole-search `SearchBudget` remains authoritative.

An unfulfilled seed is diagnostic. Examples:

- exact composition contains an unowned member;
- hard legality rejects the exact team;
- no caller-supplied candidate team contains a requested core;
- the whole-search budget ends before a selected seed is evaluated.

None of these cases should silently create a score or an invented replacement composition.

## Meta epoch

Low-usage history is valid only after a character's latest **confirmed history-resetting event**, called its meta epoch.

Initial release is one possible epoch event. A later clearly material favorite-item/skill revision, balance change, or operation-changing fix may establish a newer epoch. The optimizer does not decide whether patch text is "large enough"; that determination belongs to explicit external evidence/policy.

For Cold usage classification, a Solo Raid season counts only when:

1. the meta epoch is known;
2. the raid schedule is trusted/complete for the relevant interval;
3. the character was already post-epoch when that raid started;
4. the raid has completed;
5. the external usage snapshot is complete enough to interpret zero usage safely.

A change after a raid has started conservatively excludes that raid. Active raids are not counted.

## First-positive availability evidence

Historical usage archives may prove that a character existed even when an authoritative release date is unavailable. `meta_availability.py` records this separately from meta epoch evidence.

A mapped positive Solo Raid observation proves only:

> this character existed by this raid.

It does **not** prove that the character was available when that raid started. Therefore the observed raid itself is excluded and the conservative availability floor begins on the day after that raid ends. `completed_raids_after_first_positive()` exposes only later completed raids whose start is after that floor.

Positive observations remain useful even when some ranking rows are incomplete, because at least one actual appearance is still evidence. By contrast, an unmapped/ambiguous label, missing trusted raid period, incomplete schedule provenance, or no positive observation yields UNKNOWN/UNCERTAIN rather than an invented date.

Most importantly, first-positive availability is **not MetaEpochEvidence**. It cannot prove that a later favorite item, skill revision, balance change, or significant bug fix did not reset the character's usage history. Production Cold classification therefore still requires an independently validated meta epoch; a known first-positive observation alone must continue to fail open to Primary.

The intended use is provenance and conservative historical-cohort/backtest eligibility, not production pruning authorization.

## First benchmark policy

The current public Enikk backtest candidate remains:

`8 complete post-epoch Solo Raid seasons AND peak usage <= 1%`

A `10 seasons / 1%` policy remains the conservative comparison. These are caller-owned benchmark policies, not intrinsic character-strength thresholds.

Any of the following yields `INSUFFICIENT`, which fails open to Primary:

- unknown or uncertain meta epoch;
- incomplete raid schedule provenance;
- fewer than the required completed post-epoch raids;
- incomplete external ranking rows or unsafe zero evidence;
- ambiguous/missing external character mapping.

Only after this validity gate can the existing Cold rule apply:

`cold_eligible = LOW usage AND proven OL0`

Unknown OL remains protected exactly as before.

## Validation requirements

Synthetic regressions should keep proving both directions:

1. a pair/core whose members have weak individual marginal evidence can be recovered because a seed guarantees a real look;
2. a famous/registered seed with weak Moris damage loses normally in final allocation;
3. known first-positive availability does not substitute for missing meta epoch evidence;
4. an external five-member array with unverified order cannot become an ExactCompSeed.

Production comparison remains Meta-guided vs Pure Sim under the **same number of new Moris `simulate()` calls**. The primary metric is final non-overlapping five-team damage, not proxy recall alone.

Do not add global pair weights, ranker bonuses, meta damage bonuses, broad pair enumeration, or role-strength scores unless a later measured failure independently justifies a new experiment.
