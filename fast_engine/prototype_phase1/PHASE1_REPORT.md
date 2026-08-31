# Fast Engine Phase 1 — Moris DSL feasibility

## Scope

This phase asks whether an optimizer-specific Fast Engine can consume Moris character/skill data instead of reimplementing every character manually. It does **not** claim numerical parity or a completed runtime.

## Source inventory

Current Moris `parsed_skills.json` contains:

- 202 character keys
- 1,799 effects
- 170 distinct stat strings
- about 110 raw target expressions

Effect readiness classification (implementation-difficulty heuristic):

- N (Moris itself NOP/unimplemented for score parity): 159 effects
- A (existing research-engine primitive + adapter): 515
- B (straightforward generic primitive): 304
- C (reusable stateful generic subsystem): 819
- D (special/fallback): 2

The two D effects are both Ain (`아인`) `feather_refresh` effects. They share one reusable-but-currently-special feather subsystem and are deliberately routed to Moris for the initial Fast Engine.

**Important:** C means structurally reusable, not implemented. 201/202 character keys being structurally expressible through C is not runtime coverage.

## Trigger / condition findings

All current parsed trigger timings collapse into generic families; no unmatched custom timing family was found.

Families include burst, weapon-hit, lifecycle, named-event, periodic, state-counter, incoming-HP, encounter-event, and ammo.

All current conditions likewise collapse into generic families; no unmatched custom condition family was found.

Named `event:<name>` triggers do not imply per-character code by themselves. Current non-system named events have a generic producer rule in Moris: activating an effect/state broadcasts its named event.

## Public Solo Raid relevance

Using the public Enikk S21–S40 dataset and resource-id based mapping into Moris names:

- 29,975 teams total
- 599 teams contain Ain and therefore hit the current D fallback surface: 2.00%
- 1,778 teams contain an externally ambiguous label (`Rei` or `Sakura`) and are not guessed
- zero unknown resource IDs

Recent S33–S40:

- 11,985 teams total
- 292 Ain/fallback teams: 2.44%
- 450 ambiguous-label teams (`Rei`)
- zero unknown resource IDs

Ain usage is highly season-specific in this window: the fallback appears almost entirely in S30 and S36 rather than continuously.

## What actual top teams require

A/B alone is not sufficient for realistic teams. Among unambiguous recent S33–S40 teams, essentially every team contains at least one C-class stateful mechanic.

For recent non-D teams, C-subsystem team incidence is approximately:

- arithmetic: 100.0%
- timeline: 100.0%
- hp/shield: 98.8%
- state: 97.9%
- damage: 85.5%
- weapon change: 47.9%
- control: 40.4%
- weapon runtime: 11.9%
- generic special (excluding Ain): negligible in S33–S40

Therefore Phase 2 must build a real generic state/timeline core rather than only simple scalar buffs.

## Prototype code produced

The prototype currently provides:

- lossless Moris effect IR compilation
- explicit N/A/B/C/D readiness classification
- generic subsystem-aware team routing
- no silent approximation: D or unknown characters route the whole team to Moris
- structural-full profile currently routes an Ain-containing team to Moris and ordinary non-D teams to Fast

This router is only a **capability gate**. A subsystem must not be enabled in production until its runtime implementation has been tested for the intended ranking proxy.

## Phase 1 conclusion

The architecture is feasible enough to proceed.

The main positive result is not the raw 201/202 figure. The important result is that the current Moris dataset does not expose a large character-specific trigger/condition long-tail. Most complexity belongs to reusable shared subsystems. That makes `Moris data -> Fast compiler -> Fast runtime -> Moris final validation` materially more promising than manually porting characters.

## Phase 2 priority

1. Generic chronological event queue and burst/full-burst timeline state
2. Named state / stack / gauge state store and event broadcasting
3. Arithmetic buff resolver and target resolver
4. HP/shield state sufficient to reproduce conditions and target selection
5. Damage-request path using Moris damage/base-stat formulas initially
6. Weapon cadence / ammo / charge / reload runtime
7. Weapon-change runtime
8. Moris comparison harness (trace/debug mode, score-only production mode)
9. Ain feather remains Moris fallback until the generic core is stable
