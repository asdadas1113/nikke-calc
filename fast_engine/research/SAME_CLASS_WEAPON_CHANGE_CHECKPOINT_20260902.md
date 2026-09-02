# Same-class charge weapon-change checkpoint — 2026-09-02

## Scope

This checkpoint adds a narrow generic Fast contract for deterministic temporary self `weapon_change` on an existing SR/RL charge actor when the transformed weapon remains the same weapon class, has finite duration, uses infinite ammo, and is driven by a deterministic burst event.

It does not encode any character pairing, synergy package, or team-construction rule. Cross-class transforms remain fail-closed. Crown `heal_received` remains deferred. Candidate generation remains bypassed.

## Runtime / compiler contract

- Resolve level-mapped `weapon_change.damage_coeff` at the Fast compiler boundary.
- Track the currently active weapon-change effect as sparse runtime state.
- Re-plan dynamic charge cadence at transform entry/expiry through the existing signature/generation mechanism; no global 1/60 loop or unrestricted per-shot scheduler is introduced.
- Use transformed damage coefficient, full-charge multiplier, post-fire delay, ammo semantics and optional charge/reload fields while active.
- Treat negative transformed `max_ammo` as the Moris infinite-magazine contract for this narrow slice.
- Restore the base weapon when the timed state expires.
- Keep cross-class and otherwise non-proven weapon changes blocked.

## Static fail-closed improvement

Unsupported comparison-critical skill-damage effects are now surfaced by `static_score_blockers()` using `SimpleDamageScoreSink`'s compile-time support decision. This prevents a full Fast timeline run from occurring only to discover the same unsupported damage afterward.

The standardized public ranking probe now explicitly excludes `지그_*`, preserving the fixed 24-team public audit universe.

## Validation

Focused weapon-change regression:

- 4/4 passed.
- Same-class Red Hood transform activates and restores correctly.
- Cross-class transform remains blocked.
- Red Hood weapon-change and Mint max-ammo no longer appear as blockers in the public Red Hood team.

Full Fast regression:

- 198/198 passed.
- Structural 180s performance on the finalizer runner: median 94.23 ms, samples 94.23 / 95.24 / 92.62 ms, 368 events.
- This single-run timing is a guardrail result, not a new formal performance baseline.

Standard public audit after static fail-closed:

- standard teams: 24
- certified teams: 1
- ranking validation started: false
- certified team remains `컨트롤_미란다미하라`
  - Moris: 2,826,025,741
  - Fast: 2,806,756,837.589521
  - relative error: -0.6818375%

`레이드_레드후드퀀시` remaining blockers are now exactly the unrelated Rapi: Red Hood skill-damage gaps:

1. `skill_damage:라피 : 레드 후드:부착형 유탄 4:projectile_attachment_damage`
2. `skill_damage:라피 : 레드 후드:유탄 폭발:projectile_explosion_damage`
3. `skill_damage:라피 : 레드 후드:유탄 즉발 폭발:projectile_explosion_damage`
4. `skill_damage:라피 : 레드 후드:계승되는 힘 4:bonus_damage`

The same audit that previously spent roughly six minutes reaching runtime unsupported now completed in about four seconds after these damage gaps became static blockers.

## Ranking gate

Ranking validation still must not start: only one real public team is certified. Coverage work remains the active phase. As soon as a second real public team certifies, stop coverage expansion and measure pairwise/ranking behavior immediately.
