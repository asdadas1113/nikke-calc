# Fast Engine named Moris-NOP marker checkpoint — 2026-09-02

## Scope

This checkpoint adds a narrow generic bridge for named buffs whose numeric stat is intentionally a Moris NOP but whose activation name is still semantically observable by another effect.

It does **not** make arbitrary Moris-NOP mechanics executable and does not add character-name special cases.

## Runtime contract

A `MIRROR_MORIS_NOP` effect may act only as a named-event marker when all of the following hold:

- effect type is `buff`
- the effect has a non-empty name that is actually consumed by a named event
- max stack is absent or 1
- no advanced parameters
- target scope is runtime-supported
- no conditions
- every trigger is a simple controller/burst `EVENT` already owned by Fast

The underlying NOP stat remains ignored. The marker state is activated first, then the existing generic `event:{name}` broadcast path runs.

## Public case

Red Hood `와일드 투스 4:atk_pct` consumes `event:레드 울프`.

The concrete producer is the named `레드 울프` buff (`pierce_range`), which Moris marks as NOP numerically but activates on `squad_burst_cast:3`. Fast can therefore preserve only its marker/event role without implementing `pierce_range` or Red Hood's unsupported weapon change.

Implementation commit: `42e73c7e0fde93b8b20eb022b3d76efd4bfd9fa8`.

## Validation

Focused named-event tests: 5/5 passed.

Full Fast tests: 188/188 passed.

Standard public audit, candidate generation bypassed:

- public fixed teams: 24
- certified: 1/24
- certified team: `컨트롤_미란다미하라`
- ranking validation remains gated because fewer than 2 real public teams are certified

`레이드_레드후드퀀시` no longer reports either normal or skill-state delivery blockers for `와일드 투스 4:atk_pct`.

Remaining blockers for that team:

1. `cadence:레드 후드:글레링 아이즈:charge_speed_pct`
2. `normal_state:레드 후드:글레링 아이즈 2:charge_speed_overflow_conversion_pct`
3. `cadence:민트:다 함께 불러주세요! 2:max_ammo_pct`

Crown `heal_received` remains deliberately deferred.
