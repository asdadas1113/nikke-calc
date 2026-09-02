# Fast Engine live max-ammo / weapon-change safety checkpoint — 2026-09-02

## Scope

This checkpoint covers the next standardized public-audit slice after the Red Hood `글레링 아이즈` work:

1. support a narrow, comparison-safe runtime for live `max_ammo_pct` / `max_ammo_flat`,
2. preserve Fast throughput by leaving permanent battle-start self modifiers in the static cadence compiler,
3. close a certification hole where unsupported `weapon_change` effects with `stat=None` could disappear from blocker reporting,
4. rerun the fixed 24-team public audit with candidate generation bypassed.

`master` was not modified or merged.

## Moris contract confirmed for live maximum ammo

The Fast implementation follows the existing Moris timeline semantics:

- activating a max-ammo buff does **not** retroactively add rounds to the current magazine,
- expiring a max-ammo buff does **not** clamp current ammo to the new lower cap,
- reload completion samples the then-current effective maximum ammo and refills to it,
- if current ammo remains above the lowered cap after expiry, the actor may fire those rounds down normally,
- ammo-charge capping uses the current effective maximum ammo.

This means Fast does not need a global ammo correction event when max-ammo state changes. It only needs to invalidate cadence planning and sample the live cap at the places Moris samples it.

## Fast implementation

Implementation commit:

- `f3e18aa7a6f1724d2a5f3a368acc273ad6157943`
- `impl: support performance-safe live max ammo and fail closed weapon changes`

### Score certification

`fast_engine/engine/score.py` now recognizes a narrow dynamic maximum-ammo slice for:

- `max_ammo_pct`
- `max_ammo_flat`

Requirements include:

- buff effect,
- static ally target scope,
- runtime-executable delivery,
- no unsupported parameters or runtime conditions,
- every possible recipient must already be cadence-safe for its weapon mode,
- permanent unconditional battle-start self modifiers are explicitly excluded from dynamic promotion because they are already folded into static cadence.

Safe charge recipients are routed through the existing dynamic charge runtime. Safe auto/MG recipients are routed through the compressed dynamic rapid runtime.

### Rapid weapon runtime

`fast_engine/engine/dynamic_reload.py` now resolves live full ammo while preserving the statically compiled baseline. Only non-folded live maximum-ammo effects are added at runtime.

The effective full-magazine size is part of the rapid runtime signature, so activation or expiry invalidates future planning without mutating current ammo.

Reload completion samples the live maximum at that instant.

`fast_engine/engine/dynamic_rapid.py` and `fast_engine/engine/dynamic_weapon.py` use the same live cap for reload completion / applicable refill capping.

The existing dynamic charge runtime already sampled `max_ammo_pct` and `max_ammo_flat` live, so no parallel charge implementation was added.

## Performance regression caught and fixed

The first implementation accidentally promoted permanent battle-start max-ammo modifiers into dynamic weapon simulation.

That caused the 180-second performance contract to regress from the Fast-scale range to roughly 2.15 seconds.

The fix was to exclude `_is_folded_static_self_modifier(effect)` from dynamic max-ammo certification. Static modifiers remain static; only truly time-varying maximum-ammo effects can promote an actor.

Final focused performance result:

- median `91.03 ms`
- samples `[91.03, 91.08, 89.27] ms`
- 368 events
- contract `< 250 ms`: PASS

Full Fast suite repeat:

- median `90.38 ms`
- samples `[90.38, 90.41, 90.11] ms`

## Critical certification safety fix: unsupported weapon changes

While diagnosing why Mint's all-allies max-ammo effect still failed recipient certification, Red Hood was found to be unsafe because of:

- `레드 후드: 레드 울프 무기변경`

This is a real comparison-critical weapon transformation. It changes multiple weapon properties, including the transformed weapon's coefficient, infinite magazine, full-charge multiplier, and post-fire delay.

Fast did not execute this effect. However, the previous blocker collector had no explicit `weapon_change` branch, so unsupported weapon changes with `stat=None` could silently fall through and disappear from certification blockers.

This checkpoint fixes that hole:

- unsupported `weapon_change` now emits an explicit `weapon_change:<owner>:<effect>` blocker,
- no score can be certified merely because an unmodeled weapon transformation has no ordinary stat name.

This is intentionally fail-closed. No Red Hood or character-name exception was added.

## Tests

Added/updated focused tests cover:

1. live max-ammo activation does not grant current ammo,
2. the next reload uses the new live cap,
3. max-ammo expiry does not clamp an over-cap current magazine,
4. Red Hood's unsupported `레드 울프 무기변경` appears as an explicit score blocker,
5. Fast's 180-second throughput contract remains below 250 ms.

Verification:

- focused + performance tests: PASS
- full Fast suite: **194/194 PASS**

## Standard public audit

Contract unchanged:

- fixed real five-person memberships from `context.snapshot.SQUADS`,
- candidate generation bypassed,
- 180 s,
- first burst 3.0 s,
- expected RNG,
- enemy DEF 31,784,
- no core / parts / immunity / element-window chronology.

Latest result:

- teams: 24
- certified: **1**
- coverage gaps: 23
- Moris total probe time: `90.937 s`
- Fast attempted/certified probe time: `0.695 s`

Only certified public team remains:

- `컨트롤_미란다미하라`
- Moris: `2,826,025,741`
- Fast: `2,806,756,837.589521`
- relative error: `-0.681837505%`

Because there is still only one certified real public team, pairwise/ranking validation is **not yet statistically meaningful and was not started**.

## Red Hood / Mint frontier correction

Before this checkpoint, `레이드_레드후드퀀시` appeared to have only Mint's max-ammo blocker after the Glaring Eyes work.

That was incomplete because unsupported Red Wolf weapon transformation had been missing from blocker reporting.

The correct current blockers are:

1. `weapon_change:레드 후드:레드 울프 무기변경`
2. `cadence:민트:다 함께 불러주세요! 2:max_ammo_pct`

Mint itself is a simple READY/runtime-executable effect:

- `max_ammo_pct +40%`
- 10 s
- all allies
- `burst_cast`
- no conditions or special parameters.

It remains blocked in this team because an all-allies cadence effect can only be certified if **every** recipient is cadence-safe. Red Hood is not safe while his burst weapon transformation is unmodeled.

## New blocker visibility

Explicit weapon-change blockers now expose previously hidden comparison-critical work.

Public audit family counts:

- `skill_state_delivery`: 91
- `normal_delivery`: 85
- `cadence`: 73
- `weapon_change`: **15**
- `control`: 8
- `normal_state`: 7

Notable weapon-change pressure includes:

- 목단 `정정당당 승부다!`: 6
- 나유타 `기억 연소`: 3
- Red Hood `레드 울프 무기변경`: 1
- plus Modernia, Velvet, Snow White, Zwei, Takina transformation rows.

This makes generic weapon-change support potentially high-leverage, but it is a larger mechanic than the live max-ammo slice and should not be implemented as a Red Hood-only exception.

## Next decision point

The ranking trigger remains unchanged:

- as soon as a second real public team becomes certified, stop coverage expansion and run Fast↔Moris pairwise/ranking validation immediately.

Until then, continue coverage work while keeping unsupported transformations and other comparison-critical mechanics fail-closed.
