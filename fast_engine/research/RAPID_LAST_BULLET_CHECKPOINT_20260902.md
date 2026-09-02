# Fast Engine rapid last-bullet boundary checkpoint — 2026-09-02

## Scope

This checkpoint adds a narrow post-shot `last_bullet` boundary for dynamic rapid weapons.
It does not add per-shot scheduling, pre-shot `last_bullet_fire`, dynamic max-ammo support,
or new control semantics.

Implementation commit:

`4c5e9854963afc0705f7ac6868c7d5e832985c00`

## Runtime contract

For non-clip auto/MG actors already owned by the dynamic rapid runtime:

- ordinary physical shots remain compressed;
- when an executable post-shot `last_bullet` consumer exists, only the magazine-final physical shot is materialized as a `WEAPON_BOUNDARY`;
- the final shot is scored first;
- existing count/bullet-lifetime handling remains in the boundary path;
- BurstRuntime then dispatches post-shot `last_bullet`;
- `last_bullet_fire` remains fail-closed because it is a pre-shot event and the current phase-30 boundary cannot preserve that ordering safely.

The existing `BurstRuntime._schedule_static_last_bullets()` certification gate is reused. `MultiSignalChargeCadenceRuntime.supports_dynamic_last_bullet()` now certifies a rapid actor only when the rapid runtime explicitly registered an executable post-shot `last_bullet` consumer.

## Score certification

`_rapid_actor_score_safe()` no longer rejects post-shot `last_bullet` by itself. It continues to reject:

- `last_bullet_fire`
- `on_attack`
- full-reload consumers
- unsupported cover-event consumers
- the other pre-existing rapid ownership conflicts.

This is a generic mechanic contract; there is no character-name special case.

## Regression coverage

`fast_engine/tests/test_dynamic_last_bullet_boundary.py` verifies:

1. an executable post-shot `last_bullet` consumer no longer blocks an otherwise-safe dynamic reload owner;
2. `last_bullet_fire` remains fail-closed;
3. a two-round synthetic rapid magazine materializes its final shot and dispatches `last_bullet` exactly once;
4. the public Privaty all-allies reload effect remains blocked in `레이드_라피앨리스` because other recipient constraints (notably Alice control) still exist, and `EX 매거진 3:max_ammo_pct` remains unsupported.

Validation in the implementation workflow:

- new focused tests: 4/4 pass
- existing dynamic reload scoring tests: 9/9 pass
- full `fast_engine/tests` discovery: 183/183 pass
- structural performance probe printed median 61.99 ms for the standard 180 s Fast score sample in that run.

## Public coverage interpretation

This checkpoint is not expected to create a second certified public team by itself. In particular, removing the Privaty self `last_bullet` conflict does not prove the `all_allies` reload-speed effect safe when another recipient is outside Fast's current cadence/control ownership.

Therefore ranking validation is still gated on obtaining at least two certified real public teams. Candidate generation remains bypassed for coverage work.

## Deferred boundaries

Still deferred:

- `max_ammo_pct` live mutation (`EX 매거진 3` and similar)
- pre-shot `last_bullet_fire`
- unsupported manual control shapes
- Crown `heal_received` / HP-heal-lifesteal chronology

The next coverage step should be selected independently from the refreshed non-Crown frontier rather than treating this checkpoint as permission to widen those deferred systems.