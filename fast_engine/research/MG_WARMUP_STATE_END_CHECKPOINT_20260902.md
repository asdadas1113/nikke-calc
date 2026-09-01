# Fast Engine — MG warmup / timed state-end checkpoint (2026-09-02)

## Scope

This checkpoint extends the compressed rapid-weapon runtime with the cadence bundle needed by timed MG state endings:

- live `mg_warmup_speed_pct`,
- timed self-buff `event:state_end:<name>` delivery,
- instant `force_reload`,
- dynamic `reload_speed_pct` with positive integer `duration_bullets` on an already-owned rapid recipient.

The implementation remains mechanics-based. No character-name whitelist is used.

Candidate generation is still bypassed in the public audit. Fixed public five-person memberships are used only to measure Fast coverage and, once multiple teams are certified, ranking quality.

## Moris semantics preserved

### MG warmup speed

For `auto_warmup` weapons Moris does not retroactively shorten the interval already scheduled by the previous shot. After a physical MG shot it reads the live warmup-speed state and advances warmup by:

```python
increment = max(0.0, 1.0 + mg_warmup_speed_pct / 100.0)
warmup = min(warmup + increment, warmup_bullets)
```

The next shot interval then uses the resulting warmup level. Fast mirrors that ordering. A state change between two shots therefore changes the increment earned by the later shot, not the interval that was already committed by the earlier one.

MG cooldown across real idle time continues to use the existing compressed warmup-cooling path.

### Timed named-state ending

Moris timed buff expiry ordering is:

1. collect/remove expired active buffs;
2. for each named expired buff, emit `event:state_end:<name>` using the original caster as event owner;
3. continue with later same-frame periodic/burst/weapon work.

Fast now has a separate `STATE_END_NOTIFY` scheduler boundary after ordinary state expiry and before periodic/burst/weapon phases.

The first certified bridge is intentionally narrow. It emits state-end only for an ordinary finite-duration, self-targeted named buff with no `duration_bullets` lifetime. Explicit removal, group-target lifetime aggregation, weapon-change ending, and bullet-consumption-driven state-end remain outside this bridge until they have independent ordering contracts.

### `force_reload`

Moris `force_reload` semantics are:

- if the target is already reloading, do nothing;
- otherwise set current ammo to zero;
- start an ordinary reload immediately at the effect timestamp.

The reload therefore snapshots live reload speed at that timestamp and uses the ordinary reload-start-delay/reload-duration rules. Fast mirrors this in the dynamic rapid runtime and invalidates/replans the actor's future compressed cadence.

### One-shot reload-speed state

A positive integer `duration_bullets` reload-speed buff is now allowed when the recipient already has dynamic rapid shot ownership. It is activated at its event boundary and consumed by the next physical shot through the existing dynamic bullet-lifetime owner. Static recipients are not generalized by this change.

## Why the state-end bundle was implemented atomically

The initial target, Asuka : WILLE `긴급 수복 2`, is not an isolated MG modifier. Its trigger is `event:state_end:섬멸 태세`, and that same state-end also contains cadence-changing effects including:

- `긴급 수복 2`: `mg_warmup_speed_pct -100%` for 3 s,
- `긴급 수복 3`: `force_reload`,
- `긴급 수복 5`: `reload_speed_pct +60%`, `duration_bullets: 1`.

Opening only MG warmup speed would therefore have certified an incomplete timeline. The state-end, forced reload, and one-shot reload-speed paths were implemented and tested together.

This investigation also exposed a coverage-audit hole: `force_reload` changes cadence but was not included in `_CADENCE_OR_SHAPE_STATS`. It is now explicitly comparison-critical and is skipped as a blocker only when the dynamic force-reload path is certified.

## Fail-closed boundaries

This checkpoint does **not** generalize arbitrary named events or all state-end sources.

Still fail-closed unless separately supported:

- explicit named-buff removal state-end,
- bullet-lifetime-driven state-end outside the registered dynamic owner contract,
- weapon-change state-end,
- group/multi-target state-end aggregation whose one-notify semantics are not proven,
- unsupported controls, clip reload, `cover_during_delay` unsafe shapes,
- unsupported last-bullet/full-reload/on-attack/core-count consumers,
- HP/heal/lifesteal state propagation.

In particular, Crown `heal_received` remains deliberately deferred.

## Regression coverage

New focused regressions cover:

- live MG warmup speed changing compressed MG cadence without changing an already-scheduled interval;
- timed self-state expiry delivering state-end before the same-time weapon shot;
- `force_reload` ignoring an already-running reload and otherwise starting an immediate ordinary reload;
- same state-end activation of a one-shot reload-speed buff;
- bullet-lifetime consumption after the next physical shot;
- real Asuka public membership losing the MG warmup / forced-reload / one-shot reload-speed cadence blockers without a character whitelist.

Targeted patch workflow passed before the implementation commit was pushed.

Implementation commit:

`008efafacc54ae93faa97057343c47745031f38c`

## Public blocker frontier

One-shot frontier audit:

- workflow run: `33564804956`
- job: `100045416665`
- audit commit: `5baa44583631d0f43e0890aca79b513d9d78a570`
- teams: 24
- certified: 1
- coverage gaps: 23

### `레이드_델타`

Before this checkpoint:

- raw blockers: 4
- conceptual blockers: 3

After:

- raw blockers: **2**
- conceptual blockers: **1**

Remaining mechanism:

`크라운 / 로얄 에타이어 4 / atk_dmg_pct`, represented once in normal delivery and once in skill-state delivery. Its trigger path depends on `heal_received`.

The following Asuka cadence blockers are gone:

- `긴급 수복 2:mg_warmup_speed_pct`
- `긴급 수복 5:reload_speed_pct`

`force_reload` is also implemented and therefore does not appear as a newly exposed blocker.

### `레이드_아스카루드밀라`

Before:

- raw blockers: 9
- conceptual blockers: 6

After:

- raw blockers: **7**
- conceptual blockers: **4**

The Asuka cadence pair is removed there as well. Remaining mechanisms are Naga/Crown damage delivery and Ludmilla Winter Owner `ammo_charge_flat` coverage.

### Current nearest unresolved teams

Two real memberships now sit at raw 2 / conceptual 1:

1. `레이드_델타`
2. `스쿼드1`

Both are blocked only by Crown `로얄 에타이어 4` through the deferred `heal_received` path.

## State-end source safety hardening

A follow-up review found that timing certification alone was not sufficient. A consumer of `event:state_end:<name>` could be syntactically executable even when the corresponding state ended through a source Fast does not emit, such as explicit removal, a bullet lifetime, or an unsupported group lifetime. That would create a fail-open coverage result even though the Asuka path itself was safe.

The score gate now proves the source state for every state-end cadence consumer. Every matching provider must be:

- owned by the same actor,
- a `buff`,
- self-targeted,
- finite-duration with duration `>= 0`,
- free of `duration_bullets`,
- runtime executable.

If the provider is missing, ambiguous, group-targeted, bullet-lifetime-driven, or otherwise unsupported, the consumer remains fail-closed.

Safety implementation commit:

`f1640611e0981f502405d648ee1f27d05725e954`

Additional regressions verify that:

- a state-end consumer backed by an unsupported provider remains a cadence blocker;
- `force_reload` while a rapid actor is already reloading leaves the existing reload end time unchanged.

The targeted safety workflow passed before the safety commit was pushed.

### Frontier re-audit after the safety gate

- workflow run: `33565485221`
- job: `100047586948`
- audit commit: `d4fe96f27b882cc4843fc67eb3722d88bdb181a1`
- teams: 24
- certified: 1
- coverage gaps: 23

The intended frontier is unchanged after closing the fail-open path:

- `레이드_델타`: raw **2**, conceptual **1**, only Crown `로얄 에타이어 4`;
- `스쿼드1`: raw **2**, conceptual **1**, only Crown `로얄 에타이어 4`;
- `레이드_아스카루드밀라`: raw **7**, conceptual **4**; Asuka MG/state-end cadence blockers remain removed.

This confirms that the coverage gain came from the certified timed-self state-end path rather than an overly broad named-event allowance.

## Ranking interpretation

Certified public team count remains **1**. Therefore:

- Fast coverage improved;
- no new ranking pair exists;
- pairwise/ranking accuracy remains unobservable;
- blocked Top-N teams remain coverage gaps, not Fast ranking false negatives.

The latest measured Fast score-call time remains about **0.226 s for one certified 180 s squad** from the previous standardized public ranking probe. This is not a 24-team Fast runtime measurement because blocked teams exit before scoring.
