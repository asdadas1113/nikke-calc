# Fast Engine timed shield runtime checkpoint — 2026-09-02

## Scope

This checkpoint adds a deliberately narrow shield slice for Fast static scoring.
It does **not** add ally-hit chronology, shield damage consumption, healing, HP simulation,
or boss attack patterns.

The supported model is presence-only ordinary timed shield state:

- `shield_from_max_hp_pct`
- positive value
- finite ordinary duration
- static runtime-supported ally target set
- no condition rules
- simple controller-event timing only
- no explicit removal/control parameters

`shared_shield_from_max_hp_pct` and other shield shapes remain fail-closed.

## Moris semantics preserved

The Moris runtime currently has no ally-hit model in this path, so an ordinary shield that is
created is retained until its owning ActiveBuff expires. Independent shield sources can overlap,
and same-effect reapplication refreshes the active instance/expiry.

Equal-time ordering is important:

1. establish shield state for recipients
2. emit `event:shield_applied`
3. consumers on that event may evaluate `during_shield`

Fast mirrors that ordering.

## Runtime implementation

Implementation commit:

`431d948b3d9377a03f7d3f9591d2680cecfec12a`

Key points:

- supported shield buffs reuse `ActiveEffectStore` lifetime/generation handling;
- no separate shield timer is introduced;
- stale expiry after refresh is rejected by existing generation checks;
- recipient `StateStore.shield` tracks presence (`> 0`) for the supported slice;
- shield expiry recomputes presence from remaining active supported shield sources;
- `event:shield_applied` is dispatched only after recipient shield state exists.

## Live `during_shield` condition

`during_shield` cannot be treated as activation-only. A damage-state buff that was activated
while shielded must stop contributing if the shield disappears before the buff duration ends,
and may become effective again if another supported shield appears while the buff itself remains
active.

`DamageTermResolver` therefore rechecks `ConditionMode.DURING_SHIELD` when reading active damage
states. Its cache token also observes the HEALTH domain so cross-ally shield changes invalidate
cached damage terms.

This live recheck is intentionally limited to the shield condition added in this checkpoint.

## Score certification

Allowing the runtime primitive alone is insufficient. A shield-dependent direct-damage effect is
certified only when:

- at least one possible shield source can reach the effect owner;
- every possible shield source for that owner is inside the narrow supported timed-shield shape;
- no source is a shared-shield shape;
- no effect explicitly removes/controls the certified shield source through `target_effect`.

Otherwise the score path remains fail-closed.

## Regression coverage

`fast_engine/tests/test_damage_shield_runtime.py` verifies:

1. public Naga shield-dependent blockers are removed while Crown remains blocked;
2. shield state exists before the same-time `shield_applied` consumer fires;
3. `during_shield` caster-based ATK stops contributing when shield expires;
4. shield refresh invalidates the old expiry instead of dropping state early.

Focused validation before commit:

- new shield runtime tests: 4/4 pass
- existing `test_damage*.py`: 103/103 pass

## Public 24-team frontier

Standard audit:

- workflow run: `33576914275`
- job: `100082798337`
- candidate generation bypassed
- same standardized 24 public five-person squads and static scenario as the prior frontier audit

Result:

- teams: 24
- certified: **1**
- coverage gaps: **23**

`레이드_아스카루드밀라` changed from:

- raw blockers: 6 -> **2**
- conceptual blockers: 3 -> **1**

Both Naga mechanisms are removed:

- `우정의 가드 2:core_dmg_pct`
- `친구들과 함께라면! 3:atk_caster_based_pct`

The only remaining conceptual blocker for that team is:

- Crown `로얄 에타이어 4:atk_dmg_pct` via `heal_received`

The other two nearest teams, `레이드_델타` and `스쿼드1`, are also Crown-only at one conceptual
blocker each.

Because certified public team count is still 1, pairwise/ranking validation is still not
measurable and was not run.

## Deferred boundary

Crown `heal_received` remains deliberately deferred. This shield checkpoint is not justification
to add HP/heal/lifesteal chronology to Fast.

The next independent coverage work should be selected from the refreshed non-Crown frontier rather
than opening `heal_received` merely to increase the certified count.
