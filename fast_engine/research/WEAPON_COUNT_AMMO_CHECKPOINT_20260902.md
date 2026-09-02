# Reducible weapon-count ammo refill checkpoint — 2026-09-02

## Scope

This checkpoint extends Fast runtime execution only for a narrow class of
weapon-hit-timed ammo refill effects that the existing rapid runtime can already
materialize exactly.

A PLANNED `timing:weapon_hit` effect is bridged only when all of the following
hold:

- effect type is `instant`
- stat is `ammo_charge_pct` or `ammo_charge_flat`
- value is non-negative
- target spec is runtime-supported
- there are no condition rules
- there is exactly one trigger
- trigger mode is `MODULO`
- trigger is marked `trigger_count_reducible`
- trigger event is `hit_count` or `pellet_hit`
- threshold is positive

This is a mechanic-level bridge. There is no character-name whitelist.

The existing ammo recipient safety contract remains in force, including dynamic
weapon ownership, unsupported clip/control rejection, live max-ammo mutation
checks, and named-event consumer safety.

## Ludmilla : Winter Owner diagnosis

`여왕의 시선 3` is:

- `instant`
- self target
- `ammo_charge_flat = 20`
- trigger `hit_count:60`
- reducible modulo count
- no conditions

The blocker was not the ammo primitive or recipient cadence safety. Diagnostics
showed the recipient was already rapid-safe and ammo-recipient-safe; the effect
was rejected because its capability remained PLANNED with the sole blocker
`timing:weapon_hit`.

No dynamic core-count runtime was added for this checkpoint. Ludmilla's separate
`core_hit_count:60` damage effect does not justify widening this ammo slice.

## Regression coverage

Focused regression covers:

- reducible `hit_count` ammo refill re-planning rapid cadence
- actual effect activation count at the modulo boundary
- non-reducible weapon-count refill remaining fail-closed
- public `레이드_아스카루드밀라` losing only the Ludmilla ammo blocker
- existing Little Mermaid ammo-charge behavior remaining supported
- existing dynamic weapon/reload scoring tests
- the full `test_damage*.py` suite

Implementation commit:

`3f8ae3ffa6bc7aba48eaf6b4a040cb3d1f8f9fdc`

The pre-existing Winter Ludmilla safety assertion was updated to the new certified
contract in:

`f9b97e4c01088358b304ea3abc731dd00d75f0ab`

## Standard public 24-team frontier

Standardized candidate-generation-bypassed audit:

- workflow run: `33573540148`
- job: `100072438492`
- result: success
- teams: 24
- certified: 1
- coverage gaps: 23

`레이드_아스카루드밀라` changed from:

- raw blockers: 7 -> 6
- conceptual blockers: 4 -> 3

The removed conceptual blocker is exactly:

`Ludmilla : Winter Owner / 여왕의 시선 3 / ammo_charge_flat`

Remaining conceptual blockers are:

1. Naga `우정의 가드 2:core_dmg_pct`
2. Naga `친구들과 함께라면! 3:atk_caster_based_pct`
3. Crown `로얄 에타이어 4:atk_dmg_pct`

`레이드_델타` and `스쿼드1` remain one conceptual blocker away from
certification, both because of Crown `로얄 에타이어 4`.

Because only one public team is still certified, pairwise/ranking validation is
not yet measurable and was not run.

## Explicitly unchanged / deferred

- Crown `heal_received` remains deferred. This checkpoint does not add HP/heal/
  lifesteal chronology to Fast.
- arbitrary `timing:weapon_hit` buffs or damage effects are not opened
- non-reducible weapon-hit ammo refill remains fail-closed
- unsupported named-event chains remain fail-closed
- no Moris `calculator/` semantics were changed for parity
- `master` was not modified or merged

## Next reasonable coverage direction

With Crown healing still deferred, the next independent frontier candidate is to
inspect the two Naga damage-delivery mechanisms in `레이드_아스카루드밀라` and
only implement them if they admit similarly small generic contracts. Ranking
validation should begin immediately once at least two public teams are certified.
