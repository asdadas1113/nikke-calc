# Fast Engine — dynamic ammo charge checkpoint (2026-09-02)

## Scope

This checkpoint adds conservative live support for `ammo_charge_pct` and `ammo_charge_flat` without changing the fail-closed policy for unsupported reload/control or named-event chains.

Candidate generation remains bypassed. Public validation continues to use the fixed 24 real five-person memberships from `context.snapshot.SQUADS`.

## Moris semantics mirrored

For an instant ammo refill at time `t`:

- `ammo_charge_pct` adds `round(effective_max_ammo * value / 100)`;
- `ammo_charge_flat` adds `int(value)`;
- current ammo is capped at effective maximum ammo;
- refill may occur while reloading;
- ordinary refill does **not** cancel an already-started reload;
- the separate `reload.cancel_on_full` control is required for reload cancellation when ammo reaches full.

The Fast implementation uses Python `round()` for percent refill, matching Moris.

## Runtime architecture

Ammo cannot be implemented as a `StateStore`-only mutation because the source of truth for future cadence is the dynamic weapon runtime's internal ammo state.

The dispatcher therefore exposes an ammo-charge sink. During score setup it is connected to `MultiSignalChargeCadenceRuntime.apply_ammo_charge()`.

The callback:

1. validates every recipient before mutation;
2. advances selected dynamic weapon state to immediately before the instant event;
3. mutates the rapid or charge runtime's internal ammo count;
4. caps at the actor's certified effective maximum ammo;
5. repairs the empty-magazine transition when refill arrives before reload start;
6. keeps an already-started reload running;
7. invalidates stale scheduled weapon boundaries and replans them;
8. writes the resulting ammo value back to `StateStore`.

### Rapid weapons

If refill arrives during `reload_wait` and creates positive ammo, the actor returns to `firing` while preserving the pending next-fire probe.

If refill arrives during `reloading`, the reload remains active.

### Charge weapons

If refill arrives during `post_fire_reload` and creates positive ammo, the actor changes to `post_fire`, so the existing post-fire delay completes and charging resumes instead of starting a reload.

If refill arrives during `reloading`, the reload remains active.

## Conservative certification gate

The first slice accepts only effects whose complete recipient set is safe for dynamic weapon ownership.

It remains fail-closed when any recipient has:

- unsupported weapon/control shape;
- clip reload;
- unsupported last-bullet/full-reload/core/count dependency under the relevant weapon path;
- possible weapon change;
- live non-folded maximum-ammo mutation;
- `reload.cancel_on_full` or other unsupported control;
- a named `event:<effect name>` consumer that Fast would otherwise fail to emit correctly.

`battle_start` ammo refill is also left unsupported in this slice because BurstRuntime initializes dynamic weapon state after battle-start notifications.

This intentionally leaves several public ammo effects blocked even though the primitive refill operation itself is implemented.

## Tests

Targeted regression run:

- workflow run `33561880427`
- job `100036047010`
- result: success
- 29 focused tests passed

Added coverage includes:

- refill after empty magazine but before reload start preserves the next fire probe;
- refill during active reload does not cancel reload;
- percent refill uses Python `round()` and caps at full magazine;
- named-event consumers keep the source ammo effect fail-closed;
- real public `스쿼드1` no longer reports Little Mermaid `세이렌 송 2:ammo_charge_pct` as a blocker.

Implementation commit:

- `230c2acb8d240dc6c6111722c755e9f048ea7c7a` — `impl: dynamic ammo charge runtime`

## Public frontier result

Frontier audit:

- run `33561944592`
- job `100036254361`
- result: success

Before this slice, public `스쿼드1` had:

- raw blockers: 3
- conceptual blockers: 2

After this slice:

- raw blockers: **2**
- conceptual blockers: **1**

The only remaining conceptual blocker for `스쿼드1` is now:

- Crown `로얄 에타이어 4:atk_dmg_pct` through `event:heal_received`

represented by normal-delivery and skill-state-delivery blocker rows.

Broad HP/heal/lifesteal → `heal_received` remains intentionally deferred, so this squad is not yet certified.

The public audit still has one certified squad total; ranking pairwise accuracy therefore remains unobservable.

## Current measured Fast call time

The latest standardized timing run before this ammo slice measured the one fully certified 180 s squad at:

- **0.225979 s ≈ 0.226 s per Fast score call**

That certified squad contains no ammo-charge mechanic, so this slice does not change its executed runtime path. A new full timing probe is not required to reinterpret the measured figure.

For reference, that timing audit also measured:

- certified team Moris score: 2,826,025,741
- Fast score: 2,806,756,837.590
- relative error: -0.68184%

Do not interpret the 24-team Moris wall time as a direct 24-team Fast speed ratio while 23 teams still fail coverage before numeric scoring.

## Next frontier

With `heal_received` deferred, the next nearest independent public mechanics are in `레이드_델타`:

- Asuka : WILLE `긴급 수복 2:mg_warmup_speed_pct`
- Asuka : WILLE `긴급 수복 5:reload_speed_pct`

plus the same deferred Crown `heal_received` delivery.

The next useful independent investigation is therefore MG warmup-speed / Asuka reload interaction rather than broad heal-state modeling.
