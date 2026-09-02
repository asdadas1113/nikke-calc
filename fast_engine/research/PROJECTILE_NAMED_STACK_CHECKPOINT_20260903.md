# Projectile named-stack / first ranking gate checkpoint — 2026-09-03

## Scope

This checkpoint adds one narrow generic Fast contract for projectile/named-stack chains. It does not encode character-name exceptions, special team pairing, or optimizer composition rules.

The first real public corpus case exercising the full contract is Rapi: Red Hood's grenade sequence, but the implementation is data-driven.

Supported slice:

- source-proven post-damage `weapon_hit:{damage_name}` delivery;
- same-caster named-stack lookup across self and enemy states, matching Moris `self_stack_above` semantics;
- infinite enemy named-stack markers incremented by a proven weapon-hit source;
- deterministic named enemy-state removal on burst/full-burst events;
- direct `scaling: stack_count` damage backed by that named state;
- one exact-name finite self `trigger_count_reduce` affecting a reducible hit-count modulo trigger;
- sparse base/reduced count boundaries rather than unrestricted per-shot scheduling;
- dependency-aware pending-B3 ordering: later general damage modifiers remain fail-closed, while Moris-NOP and provably unrelated family/control buffs do not block the queued hit.

## Rapi: Red Hood chain covered by the generic contract

The public `레이드_레드후드퀀시` case contains these formerly blocked damage effects:

1. `부착형 유탄 4:projectile_attachment_damage`
   - `hit_count:120`
   - trigger-count reducible
   - MG normal-attack damage formula
2. `유탄 폭발:projectile_explosion_damage`
   - full-burst-start damage
   - scales by current `유탄` named-stack count
3. `유탄 즉발 폭발:projectile_explosion_damage`
   - triggered by `weapon_hit:부착형 유탄 4`
4. `계승되는 힘 4:bonus_damage`
   - burst-cast pending B3 damage

Related state/control effects are also covered generically:

- enemy `유탄` named stack +1 after the proven attachment-damage hit;
- `유탄 제거` on full-burst start;
- `계승되는 힘 7:trigger_count_reduce`, reducing the exact-name hit threshold from 120 to 60 while active.

## Safety boundaries

- Cross-actor `weapon_hit` inference remains closed.
- Unproven named weapon-hit chains remain blocked.
- General later `burst_cast` ATK/damage buffs still block pending-B3 scoring when ordering could alter the queued hit.
- Only the narrow exact-name trigger-count reducer contract is opened.
- No global frame loop is introduced.
- No unrestricted per-shot/per-pellet scheduler is introduced; only sparse relevant count boundaries are materialized.
- Crown `heal_received` remains deferred.
- Candidate generation remains bypassed.

## Validation

Focused regressions:

- projectile named-stack chain: 2/2 pass;
- pending-B3 ordering: 2/2 pass;
- dynamic weapon-change regression: 4/4 pass.

Full Fast regression:

- **200/200 pass**;
- structural 180s score median: **81.66 ms**;
- structural sample: `[82.08, 81.66, 81.26] ms`;
- events: 368.

30s public Rapi-chain sanity:

- Moris: `236,373,847`
- Fast: `216,060,799.2581252`
- relative error: `-8.5936%`

Standardized 180s public gate (`지그_*` excluded, fixed 24-team corpus):

- team count: **24**
- certified: **2**

Certified results:

| Team | Moris | Fast | Relative error |
| --- | ---: | ---: | ---: |
| `컨트롤_미란다미하라` | 2,826,025,741 | 2,806,756,837.589521 | -0.6818% |
| `레이드_레드후드퀀시` | 2,009,756,793 | 1,847,113,505.936137 | -8.0927% |

Initial ranking gate:

- pairwise correct: **1/1**
- Moris order: `컨트롤_미란다미하라 > 레이드_레드후드퀀시`
- Fast order: `컨트롤_미란다미하라 > 레이드_레드후드퀀시`

## Phase transition

This is the first checkpoint with at least two real standardized public teams certified. Therefore Fast ranking validation starts here and mechanic coverage expansion must stop for the next checkpoint.

The 1/1 pairwise result is only the minimum gate to begin ranking work. It is **not** evidence that Fast ranking quality, Top-N recall, or production shortlist reliability is established. The next checkpoint must focus on ranking robustness rather than opening another mechanic blocker.

## Commits

- implementation: `5d1bc4a1220b71820d074d3dc8bc4605f42b637c`
