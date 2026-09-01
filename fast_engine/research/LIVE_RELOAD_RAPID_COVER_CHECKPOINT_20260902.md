# Fast Engine — live reload / rapid cover checkpoint (2026-09-02)

## Scope

This checkpoint closes the first compressed rapid-weapon slice that composes:

- live `reload_speed_pct` for non-clip auto/MG weapons,
- reducible `hit_count` / `pellet_hit` boundaries,
- `cover.policy == own_full_burst`,
- dynamic `duration_bullets` consumption on a rapid actor,
- dynamic-target bullet-lifetime delivery such as Miranda's top-ATK one-shot buff.

The goal remains relative Fast-vs-Moris comparison under controlled conditions, not a frame-by-frame rewrite of Moris.

Candidate generation is still bypassed. Public audits use fixed five-person memberships from `context.snapshot.SQUADS`.

## Moris semantics preserved

### Reload speed

For ordinary non-clip reloads Moris applies reload speed as follows:

1. empty-magazine `reload_start_delay` and reload action snapshot speed at reload start;
2. a reload already in progress keeps that duration if the buff changes;
3. `post_reload_delay` re-reads speed at reload completion;
4. MG warmup cools according to the actual no-shot interval.

The rapid runtime mirrors those rules without a frame loop.

### `own_full_burst` cover

The certified control shape is deliberately narrow:

```python
{"cover": {"policy": "own_full_burst", "extend": optional_non_negative_seconds}}
```

Only non-clip `auto` / `auto_warmup` actors without `cover_during_delay` are certified in this slice.

Moris behavior mirrored by Fast:

- the actor must have cast a burst in the current cycle;
- cover starts after full-burst-start effects have been delivered;
- firing is suppressed until `full_burst_end + extend`;
- a partial magazine starts a manual reload immediately on cover entry;
- manual cover reload does not pay empty-magazine `reload_start_delay`;
- an already-running reload is not restarted;
- reload may complete while still covered;
- missed shots are not replayed after cover ends;
- a shot may occur on the exact cover-end boundary;
- MG warmup cools once against the complete idle interval before the next real shot.

### Dynamic `duration_bullets`

Static recipients keep the old zero-overhead model: Fast schedules one post-shot expiry at the precomputed Nth shot.

A registered dynamic rapid recipient instead stores a live remaining-shot count in `ActiveEffectStore`:

- no stale static expiry is scheduled;
- reactivation resets the remaining count with a new generation;
- every physical shot is temporarily materialized while a bullet-lifetime state is active;
- score is calculated while the consuming shot still sees the buff;
- reducible pellet/hit signals are delivered;
- only then is the bullet lifetime decremented/removed.

This matches Moris' `damage -> hit notifications -> consume_bullet_buffs` ordering for the certified slice.

## Fail-closed exclusions

The rapid control/reload path remains blocked when any of these apply:

- clip reload,
- `cover_during_delay`,
- another control shape (`tap_fire`, hold, reload-control, explicit sequence, etc.),
- weapon change that may target the actor,
- executable core-hit-count consumer,
- raw/non-reducible `hit_count` or `pellet_hit`,
- `last_bullet_fire`, `last_bullet`, `on_attack`, `event:full_reload` / `full_reload`,
- executable `event:cover` consumer,
- executable global `squad_body_hit` consumer.

These are coverage gaps, not ranking errors.

## Regression coverage

Added/updated tests cover:

- live reload duration fixed at reload start,
- reload-completion `post_reload_delay` speed snapshot,
- compressed MG reload cadence,
- reducible count ownership without static duplicate triggers,
- manual cover reload skipping empty-magazine start delay,
- same-boundary cover exit shot,
- unsupported mixed control remaining fail-closed,
- dynamic top-ATK bullet-lifetime target failing atomically without a live owner,
- live rapid bullet-lifetime consumption after the consuming shot,
- real Miranda / Bride : Silent Track / Helm / Rouge / Mihara : Bonding Chain squad becoming scoreable.

## Standardized 24-team public audit

One-shot audit:

- workflow run: `33558360807`
- audit job: `100024625942`
- source commit: `d4528d96f5cbb8c88919b0463055d61f3ed9cc4d`

Scenario contract:

- 24 unique real five-person public memberships,
- 180 s,
- first burst 3.0 s,
- expected RNG,
- defense 31,784,
- no core / parts / immune / element windows,
- optimizer candidate generation bypassed.

Results:

- teams: 24
- Fast certified: **1**
- coverage gaps: **23**
- Moris total wall time: **79.602 s**
- Fast certified-or-attempted score time: **0.265 s**
- blocker families: `skill_state_delivery 99`, `normal_delivery 93`, `cadence 92`, `control 8`, `normal_state 8`
- unsupported families: none

First certified public team:

`미란다 / 브리드 : 사일런트 트랙 / 헬름 / 루주 / 미하라 : 본딩 체인`

- Moris: **2,826,025,741**
- Fast: **2,805,183,141.976**
- relative error: **-0.737523%**

With only one certified team there are zero comparable pairs. Therefore:

- single-team score error is observable;
- pairwise/ranking accuracy is **still unobservable**;
- blocked public Top-N teams remain coverage gaps, not Fast ranking false negatives.

## Control-on/off parity probe

A follow-up one-shot probe compared the same five-person team with Mihara's recommended cover control enabled and manually disabled.

### Control ON

- Moris: 2,826,025,741
- Fast: 2,805,183,141.976
- error: **-0.7375%**

### Control OFF

- Moris: 2,432,024,766
- Fast: 2,410,068,628.693
- error: **-0.9028%**

The new cover runtime does not create the aggregate discrepancy; enabling it slightly reduces the pre-existing Fast-vs-Moris approximation error.

Per-character control-ON errors were:

- Miranda: -0.981%
- Bride : Silent Track: -1.371%
- Helm: +1.974%
- Rouge: -5.313%
- Mihara : Bonding Chain: -1.247%

The aggregate remains below 1%, but these character-level offsets are retained as future baseline diagnostics rather than silently attributed to the new control slice.

## Frontier after this checkpoint

The nearest remaining public membership is `스쿼드1`:

`리틀 머메이드 / 크라운 / 라피 : 레드 후드 / 미하라 : 본딩 체인 / 헬름`

It has six raw blockers / four conceptual mechanisms:

1. Little Mermaid `세이렌 송 2:ammo_charge_pct`
2. Crown `원 포 올 2:reload_speed_pct`
3. Crown `로얄 에타이어 4:atk_dmg_pct`
4. Helm `이지스 캐논 3:charge_dmg_mag_pct`

Cause decomposition:

- Crown Royal Attire is triggered by `event:heal_received`; broad HP/heal/lifesteal delivery remains intentionally deferred.
- Crown reload is otherwise safe for the four rapid recipients; Helm is the sole unsafe recipient because the current charge-reload gate still treats `cover_during_delay` / related charge-side events conservatively.
- Helm's 10-shot buff is self-targeted but cannot use the static Nth-shot lifetime while its cadence may become dynamic.
- Little Mermaid ammo refill is an instant all-allies cadence mutation and is not implemented by the rapid runtime; it should not be generalized merely because it is frequent.

The next small independent slice is therefore charge-side live bullet-lifetime ownership for Helm-like `duration_bullets`, followed by a separate decision on the exact `cover_during_delay` threshold needed for live reload composition.
