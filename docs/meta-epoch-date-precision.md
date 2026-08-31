# Meta-epoch date precision

Status: optimizer-only implementation note for `roster-optimizer-prototype`.

## Rule

`MetaEpochEvidence.valid_from` and `SoloRaidPeriod.start_on` currently store calendar dates, not timestamps.

A normal Solo Raid season is therefore considered fully post-epoch only when:

```text
epoch.valid_from < raid.start_on
```

Equality is intentionally not enough.

If a release, Favorite Item, skill revision, or other confirmed history-resetting event occurs on the same calendar day as the raid start, the date-only model cannot prove whether the event happened before or after the raid opened. That season is conservatively excluded from the low-usage evidence window.

This is a fail-open search-budget rule. It can only protect a character from premature Cold classification; it never changes Moris damage, hard legality, or final allocation score.

## Why not infer the order?

Do not infer same-day ordering from character ids, resource ids, patch ordering, or typical maintenance/recruit times. If exact timestamps are not represented by the evidence model, the optimizer must not manufacture them.

A future timestamp-aware evidence type may safely recover a same-day season when both the epoch event and raid opening time are explicitly sourced and comparable in one timezone. Until then, same-day remains ineligible.

## Regression fixture

`tests/fixtures/optimizer_recent_first_availability_2026.json` contains a small public-provenance 2026 fixture used only for eligibility regression testing. It is not a strength tier or a production-complete release registry.

The fixture deliberately includes a same-day boundary case: a first-availability date and Solo Raid start date both on `2026-08-20`. The date-only model excludes that raid, even if an external page may separately expose intra-day times that would establish the real-world order. This keeps the current data model honest rather than smuggling timestamp knowledge into a `date` comparison.

The companion regression verifies that recent characters with fewer than eight fully post-epoch completed seasons remain `INSUFFICIENT` under the current 8-season benchmark policy even when the available usage snapshots appear to contain zero usage.

## Invariant

The epoch gate answers only whether historical usage is valid enough to support search deferral.

It does not answer whether a character is strong, weak, meta, or worth selecting. Actual evaluated squad strength still comes only from Moris `simulate()`.
