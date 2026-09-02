# Fast Engine — Glaring Eyes checkpoint (2026-09-02)

Branch: `fast-engine-phase2-20260901`

## Scope

This checkpoint expands Fast only for the Red Hood `글레링 아이즈` conceptual pair. It does not add a generic global on-attack/per-shot scheduler and does not change Moris calculator semantics.

## Moris source semantics

`글레링 아이즈`
- buff `charge_speed_pct`
- +3.81%
- self
- duration 5s
- max 10 stacks
- trigger `on_attack`

`글레링 아이즈 2`
- buff `charge_speed_overflow_conversion_pct`
- 240%
- self
- permanent battle-start state

Moris computes charge-speed overflow as:

`overflow = max(0, charge_speed_pct - 100)`

and adds:

`overflow * conversion_pct / 100`

to `charge_dmg_pct`.

## Fast contract added

Fast now certifies only a narrow self-targeting charge-speed stack shape:
- beneficial buff
- `charge_speed_pct`
- one raw `on_attack` EVENT trigger
- finite positive duration
- finite stack cap >= 1
- no conditions or advanced parameters
- capability otherwise blocked only by `timing:weapon_hit`

For charge weapons that own this shape, the dynamic charge runtime makes physical shots observable and emits `on_attack` after the consuming shot has been scored. This preserves Moris' damage-before-post-shot-notify ordering without introducing a global frame loop.

Fast also certifies only a narrow overflow-conversion shape:
- self buff
- `charge_speed_overflow_conversion_pct`
- permanent battle-start activation
- one stack
- no conditions or advanced parameters

`DamageTermResolver` mirrors the Moris overflow formula and includes caster-based charge-speed contribution in the total used for the threshold.

Other `on_attack` consumers remain fail-closed. Non-charge raw `on_attack` delivery is not opened by this checkpoint.

## Tests

Focused Glaring Eyes + named-event regression bundle: 11/11 passed.

Full Fast suite after the change: 191/191 passed.

Structural performance sample from that run:
- Fast static 180s median: 48.53 ms
- samples: 48.53 / 49.27 / 48.38 ms
- events: 368

## Standard 24-team public audit

Candidate generation remained bypassed; `context.snapshot.SQUADS` was audited directly.

- public teams: 24
- certified teams: 1
- certified: `컨트롤_미란다미하라`

`레이드_레드후드퀀시` now has exactly one Fast certification blocker:

`cadence:민트:다 함께 불러주세요! 2:max_ammo_pct`

Therefore ranking validation does not start yet; the hard trigger remains at two real certified public teams.

## Next blocker diagnosis: Mint

`다 함께 불러주세요! 2`
- effect type: buff
- stat: `max_ammo_pct`
- value: +40%
- duration: 10s
- max stack: 1
- target: all allies
- trigger: `burst_cast`
- conditions: none
- advanced parameters: none
- capability disposition: READY
- dispatcher executable: yes

So this is not a missing trigger/runtime-capability primitive. The remaining issue is the score-side safety contract for live maximum-ammo mutation and its dynamic weapon magazine/reload semantics. The next checkpoint should inspect and, if safe, implement that generic dynamic max-ammo scoring contract. If doing so certifies `레이드_레드후드퀀시`, coverage expansion must stop immediately and Fast-vs-Moris ranking/pairwise validation begins.
