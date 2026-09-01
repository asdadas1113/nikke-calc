# Fast Engine — charge bullet lifetime checkpoint (2026-09-02)

## Scope

This checkpoint extends the existing dynamic charge runtime so charge weapons can own live `duration_bullets` state and safely compose selected live reload-speed effects.

Candidate generation remains bypassed. Public validation still uses the fixed 24 five-person memberships from `context.snapshot.SQUADS` under the common 180 s / first burst 3.0 s / expected-RNG scenario.

## Implemented runtime semantics

### Charge-side `duration_bullets`

Selected charge actors are registered as live bullet-lifetime owners before battle-start activation.

While a live bullet-count effect targets such an actor:

1. the physical charge shot is materialized as a weapon boundary;
2. normal-attack score is evaluated while the buff is still active;
3. post-shot `full_charge_hit` / reducible count signals are delivered;
4. the live bullet lifetime is decremented;
5. `last_bullet` is delivered after that consumption point.

The existing Moris semantic invariant is preserved:

- raw `full_charge` is pre-shot;
- `full_charge_hit` is post-shot;
- they are never aliased.

Rapid and charge live bullet-lifetime registrations are additive, so both weapon families can coexist in the same squad.

### `cover_during_delay` reload certification

`cover_during_delay` is no longer rejected unconditionally for a charge recipient.

Fast computes a conservative upper bound for all positive `reload_speed_pct` buffs that could target the actor. The charge path is certified only when that upper bound remains below 100%, making Moris' special 100%-reload cover behavior unreachable.

The gate remains fail-closed for:

- charge control,
- clip reload,
- reachable `cover_during_delay` special behavior,
- possible weapon change,
- executable core-hit count,
- `last_bullet_fire`, `on_attack`, `event:full_reload`, `full_reload`,
- pellet-hit consumers,
- non-reducible/raw hit-count consumers.

Post-shot `last_bullet` is allowed because selected charge score actors materialize every physical shot.

## Helm / Crown proof for public squad1

Public `스쿼드1`:

`리틀 머메이드 / 크라운 / 라피 : 레드 후드 / 미하라 : 본딩 체인 / 헬름`

Helm has `cover_during_delay=True`, but its conservative positive reload-speed upper bound is:

- Crown `원 포 올 2`: +44.35%
- Helm Relic Bear Cube: +29.69%
- total: **74.04%**

Therefore the 100% special branch cannot occur in this squad.

Helm `이지스 캐논 3` is a self-targeted `charge_dmg_mag_pct` buff with `duration_bullets=10`. Its lifetime is now consumed by Helm's actual dynamic charge shots rather than a stale static Nth-shot timestamp.

## Regression coverage

Targeted regression suite after the implementation passed 24 tests, including:

- charge-side live 10-shot lifetime consumption,
- correct effect-specific expiry rather than aggregate-stat expiry,
- existing dynamic charge scoring,
- existing dynamic reload scoring,
- existing rapid cover/control behavior,
- real Miranda/Mihara certified-squad behavior,
- public squad1 Crown reload and Helm 10-shot delivery blocker removal.

The full normal CI subsequently passed all Fast, engine, optimizer, browser, bridge, and golden-snapshot checks.

Implementation commit:

- `88ab8b5d01e9accf81c4259e67ed16be2ee80129` — `impl: charge bullet lifetime runtime`

Full CI:

- run `33560851620`
- job `100032786084`
- result: success

## Frontier delta

Frontier audit:

- run `33560851615`
- job `100032695567`

`스쿼드1` changed from:

- raw blockers: 6
- conceptual blockers: 4

to:

- raw blockers: **3**
- conceptual blockers: **2**

Removed:

- Crown `원 포 올 2:reload_speed_pct`
- Helm `이지스 캐논 3:charge_dmg_mag_pct` normal delivery
- Helm `이지스 캐논 3:charge_dmg_mag_pct` skill-state delivery

Remaining:

1. Little Mermaid `세이렌 송 2:ammo_charge_pct`
2. Crown `로얄 에타이어 4:atk_dmg_pct` through `event:heal_received` (normal + skill-state delivery)

Broad HP/heal/lifesteal → `heal_received` remains intentionally deferred.

## Latest standardized timing / parity audit

Audit:

- run `33561207208`
- job `100033858795`
- source commit `075f557cc89f3818ce35461d4f472c3ac36d2b71`

Results:

- teams: 24
- certified: 1
- coverage gaps: 23
- Moris 24-team wall time: 59.944 s
- Fast certified-or-attempted score time: **0.225979 s**
- current practical Fast call time for the one certified 180 s squad: **about 0.226 s**
- certified team Moris score: 2,826,025,741
- certified team Fast score: 2,806,756,837.590
- relative error: **-0.68184%**

The Moris total wall time varies substantially by CI runner and must not be interpreted as a stable speed ratio. The Fast figure is likewise a single-run wall measurement, but it is the current direct measurement for one fully scored 180 s squad.

Blocker families after this slice:

- `skill_state_delivery`: 96
- `normal_delivery`: 90
- `cadence`: 87
- `control`: 8
- `normal_state`: 8

Only one public squad is certified, so pairwise/ranking accuracy remains unobservable. Blocked Top-N squads are coverage gaps, not ranking false negatives.

## Next independent slice

The nearest independent blocker is `ammo_charge_pct` / `ammo_charge_flat`.

Moris semantics confirmed before implementation:

- percent refill adds `round(effective_max_ammo * pct / 100)`;
- flat refill adds `int(value)`;
- current ammo is capped at effective maximum ammo;
- refill can occur while reloading;
- reloading is cancelled only when the separate `reload.cancel_on_full` control is enabled and ammo reaches full;
- named ammo-charge effects emit their `event:<effect name>` event after refill.

Therefore the first Fast ammo-refill slice should keep reload-cancel control and unsupported named-event consumers fail-closed rather than treating refill as a simple `StateStore` mutation.
