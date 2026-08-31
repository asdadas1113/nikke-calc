# Research-engine lessons for the greenfield Fast runtime

The Crown/Mast research engine is frozen as a reference implementation. It is not the base class hierarchy for the production Fast Engine.

## Keep the ideas

- Separate **battle event**, **weapon shot**, **damage request**, and **buff window** concepts.
- Treat combat as a timeline of meaningful state changes rather than as one static DPS number.
- Buff/state lookup is a major performance hotspot; compile/cache repeated resolution work instead of recomputing it per shot.
- Unchanged spans can be aggregated. A weapon that fires under identical state for a span does not need one Python object per frame or per bullet unless a trigger boundary falls inside the span.
- A score-oriented runtime does not need Moris UI artifacts such as the full hit history, graph timeline, or verbose combat log.
- Profiling of the controlled engine demonstrated that reducing repeated buff resolution can materially improve 180-second runtime, so the design should make state-version caching natural from the start.

## Do not carry the research constraints forward

The following are research-specific and must not define production abstractions:

- `TeamRoster.crown` / `TeamRoster.mast` as structural slots.
- B2 rotation restricted to `crown | mast`.
- Crown/Maid Mast-specific `_on_b2` dispatch.
- `MastState`, Drunken/Hangover handling embedded in the scheduler rather than compiled effects/state primitives.
- fixed Crown/Mast cycle scenarios or a fixed 12-cycle policy.
- any assumption that Burst II is owned by two named characters.
- fixed 1/60-second frame stepping.

The generic runtime must be character-name blind. A burst actor is selected by burst metadata/policy and then its compiled effects are dispatched; the scheduler must not contain `if Crown`, `if Mast`, or equivalent named-character branches.

## What the research engine proved

It proved feasibility, not generality:

1. a much lighter score-oriented runtime can execute a 180-second theoretical fight faster than the full Moris path;
2. event/buff/damage separation is useful;
3. aggressive caching/aggregation has large headroom;
4. character-specific research assumptions make retrofitting the engine into a general Solo Raid runtime more expensive than starting a greenfield core.

Therefore the production Fast Engine is greenfield. The research snapshot remains a benchmark/reference source only.
