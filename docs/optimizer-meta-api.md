# Optimizer Meta API boundary

The package-level Meta/Cold API is fail-open and production-oriented.

## Production path

Use the package-level unqualified functions or their explicit `*_bounded` names:

- `optimizer.classify_meta_epoch_usage`
- `optimizer.classify_roster_meta_usage`
- `optimizer.build_meta_guided_partition`
- `optimizer.prepare_meta_guided_roster`
- `optimizer.prepare_meta_guided_search_roster`

These names resolve to the bounded implementations and require certified usage evidence built from:

- `RankingCoverageContract`
- `CertifiedEnikkSeasonUsageSnapshot`
- `certify_enikk_rankings(...)`
- `aggregate_bounded_character_window(...)`

Missing rows, malformed rows, unknown external labels, and known ambiguous labels remain uncertainty. A character is eligible for `LOW` only when the conservative upper bound stays within the configured threshold. Known ambiguous labels are localized to their canonical candidates rather than spreading uncertainty across the whole roster.

The resulting usage decision is still only one input to Cold eligibility. Account-specific OL evidence, protected names, structural restoration, and bounded Cold exploration remain downstream safeguards. Moris simulation remains authoritative for final damage and final team selection.

## Research/descriptive path

Historical point-estimate helpers remain available only under explicit research names at package level:

- `ResearchEnikkSeasonUsageSnapshot`
- `ResearchCharacterUsageWindow`
- `ResearchSeasonUsageObservation`
- `research_summarize_enikk_rankings(...)`
- `research_aggregate_character_window(...)`
- `research_classify_meta_epoch_usage(...)`
- `research_classify_roster_meta_usage(...)`
- `research_build_meta_guided_partition(...)`
- `research_prepare_meta_guided_roster(...)`
- `research_prepare_meta_guided_search_roster(...)`

These APIs are retained for historical benchmark replay and descriptive analysis. They are not valid production evidence for deferring a character into the Cold pool.

## Compatibility rule

New production code must not import the descriptive `meta_usage` / unbounded `meta_policy` path through the package root. Historical benchmark files that still consume the old evidence schema must use the explicit `Research*` / `research_*` names so the distinction is visible in code review.
