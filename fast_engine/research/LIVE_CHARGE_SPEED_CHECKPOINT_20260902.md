# Fast Engine live charge-speed scoring checkpoint — 2026-09-02

## Scope

This checkpoint extends Fast normal-attack scoring only for live SR/RL charge-speed cadence that the existing Fast runtime can already deliver safely.

Supported cadence states in this slice:

- `charge_speed_pct`
- `charge_speed_caster_based_pct`

The following remain deliberately outside this checkpoint:

- `reload_speed_pct`
- `max_ammo_pct` / `max_ammo_flat` / `max_ammo_infinite`
- `ammo_charge_flat` / `ammo_charge_pct`
- `charge_time_flat` / `charge_time_fixed`
- `attack_speed_pct`
- `mg_warmup_speed_pct`
- `pellet_count` / `pellet_count_fixed`
- manual-control cadence
- HP/heal/lifesteal -> `heal_received`

No character-name exception was added.

## Scoring architecture

The previous normal-attack observer consumed one precompiled static shot-block stream per actor. That cannot remain correct when a live charge-speed state changes a shot that has not happened yet.

The new path keeps static actors unchanged and promotes only affected charge actors into `MultiSignalChargeCadenceRuntime` every-shot boundaries:

1. the score observer determines whether a certified live charge-speed state exists;
2. affected charge actors receive empty static score cursors, preventing double-counting;
3. before weapon runtime `start()`, the observer registers a physical-shot score sink;
4. the existing dynamic cadence runtime performs its generation-based invalidation/replanning when charge-speed state changes;
5. each resulting physical charge shot is scored from current damage state;
6. the score callback runs before post-shot `full_charge_hit` / `hit_count` delivery, preserving Moris damage-before-hit-notify ordering.

This is still not a frame loop and does not materialize every auto/MG bullet. It expands only charge actors that require the live cadence score path.

Unsupported timing/condition paths remain fail-closed. `duration_bullets` charge-speed effects are also still rejected because their expiry currently depends on the static next-shot helper.

## Regression test

`fast_engine/tests/test_damage_dynamic_charge_scoring.py` is included in the existing `Fast — damage` CI discovery.

The synthetic regression uses a 1.0 s charge weapon and a finite +50% charge-speed state that expires at 1.5 s. The expected physical shots inside `[0, 4)` are:

- 0.5 s
- 1.0 s
- 2.0 s after the stale 1.5 s plan is invalidated and the in-progress charge is replanned
- 3.0 s

The test verifies exactly four scored shots, so the dynamic path cannot silently coexist with the old static shot cursor. A separate negative case verifies that an uncertified raw weapon-hit timing remains a cadence blocker.

## Standardized 24-team public audit

Engine checkpoint before the one-shot audit workflow:

`f2b8f8fa6a386eca45a93f8b45c85b9a2c31b641`

One-shot audit commit:

`45b734081ef751a700ab630b36d90ba19a1a1733`

GitHub Actions run:

`33546825419`

Scenario contract is unchanged:

- fixed 24 unique real five-person memberships from `context.snapshot.SQUADS`;
- optimizer/candidate generation bypassed;
- public `context.spec` default builds;
- 180 s;
- first burst 3 s;
- `rng_mode=expected`;
- patternless enemy, DEF 31784, no element/core/parts/windows.

Measured result:

- public standardized squads: **24**
- Fast certified numeric scores: **0**
- coverage gaps / fail-closed squads: **24**
- Moris simulation wall time: **77.225 s**
- Fast scoring wall time: **0.000 s** because all rows were still rejected before certified scoring
- Moris Top-10: **10 blocked, 0 scored-and-ranked-out**
- `catastrophic_false_negative_rate = 0.0`
- `top_n_coverage_gap_rate = 1.0`
- pairwise ranking accuracy: **not measurable** (`0` comparable pairs)

Blocker-family movement versus the previous post-toggle checkpoint:

| blocker family | post-toggle | live charge-speed | delta |
|---|---:|---:|---:|
| cadence / shot-shape | 109 | 99 | **-10** |
| skill state delivery | 103 | 103 | 0 |
| normal-attack state delivery | 97 | 97 | 0 |
| unresolved normal-damage state | 8 | 8 | 0 |
| manual control | 9 | 9 | 0 |
| **total** | **326** | **316** | **-10** |

The ten removed cadence occurrences are exactly the public effects whose existing Fast delivery path is compatible with this slice:

- Liberalio `차분한 수심 4:charge_speed_caster_based_pct` — 3 occurrences removed;
- Alice `신기하고 이상한 나라:charge_speed_pct` — 3 removed;
- Alice `힘나는 당근:charge_speed_caster_based_pct` — 3 removed;
- Red Hood `레드 울프 2:charge_speed_pct` — 1 removed.

Charge-speed effects that do not pass the existing runtime-delivery certification remain blocked. Examples still present in the audit include:

- Ada `특수 개조:charge_speed_pct` — 3;
- Cinderella `무결한 유리 2:charge_speed_pct` — 2;
- Red Hood `글레링 아이즈:charge_speed_pct` — 1;
- Brady `머물고 싶은 맛:charge_speed_pct` — 1;
- Brady `나누고 싶은 맛:charge_speed_pct` — 1.

This is intentional fail-closed behavior, not a request to whitelist those characters.

## Interpretation

The checkpoint demonstrates a real coverage expansion: total comparison-critical blockers fell by 10 with no blocker-family reclassification elsewhere.

It does **not** establish Fast ranking quality. The correct causal diagnosis remains:

`candidate generation bypassed -> Fast coverage gap -> no ranking diagnosis yet`

There are still zero certified teams and zero comparable certified pairs. In particular, `ranked_out=0` means there is still no evidence here of a Fast ranking error.

The largest remaining cadence pressure points are now reload/ammo families rather than the charge-speed slice just implemented, including Crown reload speed, Little Mermaid ammo charge, Maid Mast reload speed, and Privaty reload/max-ammo. Those should still be decomposed rather than globally whitelisted.
