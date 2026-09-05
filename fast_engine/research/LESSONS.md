# Research-engine lessons for the greenfield Fast runtime

The controlled Crown/Mast research engine is no longer retained in this repository. Only reusable design/profiling lessons are kept here. Production Fast Engine must not depend on the removed prototype.

## Keep the ideas

- Separate **battle event**, **weapon shot**, **damage request**, and **buff window** concepts.
- Treat combat as a timeline of meaningful state changes rather than as one static DPS number.
- Buff/state lookup is a major performance hotspot; compile/cache repeated resolution work instead of recomputing it per shot.
- Unchanged spans can be aggregated. A weapon that fires under identical state for a span does not need one Python object per frame or per bullet unless a trigger boundary falls inside the span.
- A score-oriented runtime does not need Moris UI artifacts such as full hit history, graph timeline, or verbose combat log.
- Reducing repeated buff/damage-state resolution materially improves 180-second runtime, so state-version caching should be natural from the start.
- Expected-value deterministic treatment is preferable to RNG noise for broad candidate ranking when it preserves long-run proc frequency.
- Raw events should be promoted selectively: only actors/effects that actually consume an every-hit/every-charge signal should force those boundaries into the scheduler.

## Accuracy lesson: protect ranking, not cosmetic parity

The project goal is not exact Moris decimal equality. The important distinction is:

- harmless/common approximation error;
- **systematic comparison bias** that favors or suppresses one weapon/mechanic/team archetype.

Examples encountered during development:

- Moris frame quantization can produce small timing differences that should not force a global 1/60 Fast loop.
- A battle-end boundary difference (`180.0 s` included vs excluded) caused an exact extra periodic proc and therefore meaningful comparison error; that semantic boundary had to match.
- Treating SG `hit_count` as pellet count instead of one per trigger pull can make SG count effects activate dramatically too early. This is a ranking-bias bug, not cosmetic damage error.
- Using one common core-hit probability for all weapon types can bias rankings on core-heavy bosses because Moris core probability depends on weapon spread, accuracy and core size.

When choosing where to spend fidelity, prioritize errors that can reorder squads.

## Character anomaly debugging rule

Do **not** change common runtime logic merely because one character disagrees with Moris.

Use this diagnosis hierarchy:

1. same pattern across many characters → common formula/runtime issue;
2. same pattern within one weapon/mechanic cohort → mechanic module issue;
3. exactly one character differs → inspect that character's data/unique mechanic first.

Unique mechanics worth checking before touching shared logic include:

- position/adjacency targeting;
- Top/Lowest ATK or class/element restricted targeting;
- burst-caster/B3-only selection;
- HP/ammo/stack/gauge conditions;
- activation-time snapshot vs continuous re-ranking;
- source order of effects in one skill;
- unusual stacking/refresh behavior;
- caster-based coefficients;
- max-HP scaling;
- charge/core/share damage;
- invulnerability/cover/taunt/pierce/part/summon states.

Preferred layering:

```text
common calculation
  → generic mechanic handler
  → named-character exception only if genuinely unavoidable
```

A character exposing a mechanic first does not make that mechanic character-specific. For example, adjacency/side-slot behavior should be a position-targeting primitive rather than `if Rouge` logic.

## Fail-closed lesson

A numeric stat being understood is not enough to claim support.

For a score to be trustworthy, Fast must also be able to deliver:

- the trigger timing;
- the condition;
- the target selection;
- the state lifetime/refresh semantics.

If an unsupported buff/debuff could change otherwise-supported damage, block that score rather than silently omit the state. Unsupported isolated damage events may be reported separately when the returned subtotal remains interpretable.

Capability labels should therefore be conservative. A narrow auxiliary path (for example, using one ATK buff only to resolve Top-ATK targeting) does not make the full damage mechanic globally READY.

## Core-count authority and cadence lesson

Real parsed cases exposed two separate issues that must not be conflated.

- `루드밀라 : 윈터 오너` (`눈보라`) and `길로틴 : 윈터 슬레이어` (`경험치`) use the canonical `core_hit_count:N` spelling.
- Moris expected-mode `_notify_frac` is designed to feed fractional `core_hit` events for count mechanics, but the current BuffManager timing matcher accepts the older `core_hit:N` spelling and does not match `core_hit_count:N` directly. Until the authority matcher is corrected, Fast parity tests must isolate that spelling gap at the test boundary rather than changing Fast semantics to imitate a silent authority omission.
- Core-count scheduling is not only a probability problem. Ammo refill (`ammo_charge_flat` / `ammo_charge_pct`), reload/max-ammo, attack/charge speed, pellet shape, weapon changes, and live accuracy can all invalidate future precompiled core boundaries.
- The same ammo-refill issue invalidates ordinary static shot blocks, not just core triggers. Fast must fail closed on such squads until dynamic cadence replanning exists; silently scoring the stale timeline is a potential false-negative ranking bug.
- CI must explicitly execute core-probability and core-boundary tests. File-name conventions alone are not a reliable quality gate for a new mechanic family.

## Do not carry the research constraints forward

The following were research-specific and must not define production abstractions:

- `TeamRoster.crown` / `TeamRoster.mast` as structural slots;
- B2 rotation restricted to `crown | mast`;
- Crown/Maid Mast-specific `_on_b2` dispatch;
- `MastState`, Drunken/Hangover handling embedded in the scheduler rather than compiled effects/state primitives;
- fixed Crown/Mast cycle scenarios or a fixed 12-cycle policy;
- any assumption that Burst II is owned by two named characters;
- fixed 1/60-second frame stepping.

The generic runtime must be character-name blind. A burst actor is selected by burst metadata/policy and then its compiled effects are dispatched; the scheduler must not contain `if Crown`, `if Mast`, or equivalent named-character branches.

## What the research engine proved

It proved feasibility, not generality:

1. a much lighter score-oriented runtime can execute a 180-second theoretical fight dramatically faster than the full Moris path;
2. event/buff/damage separation is useful;
3. aggressive caching/aggregation has large headroom;
4. character-specific research assumptions make retrofitting the engine into a general Solo Raid runtime more expensive than starting a greenfield core.

The greenfield Fast runtime has since reinforced that conclusion: 180-second five-person score tests are already in the tens-of-milliseconds range on CI fixtures while preserving increasingly broad Moris semantics.

Therefore the production Fast Engine remains greenfield. These written lessons are the only retained project dependency from the old controlled research prototype.

## 2026-09-05 — periodic direct state는 scheduler보다 grid mutation proof가 중요하다

- 기존 periodic deadline scheduler가 Moris outer-tick 관측과 맞더라도 새 damage-facing stat을 바로 열면 안 된다.
- `effect_interval`/`skill_cooldown_pct`처럼 Moris periodic grid를 바꾸는 상태가 있으면 Fast의 fixed grid는 오답이 될 수 있다.
- 따라서 narrow periodic shape certification과 `_PERIODIC_GRID_INVALIDATORS` fail-closed를 함께 유지한다.
- 실제 Snow White finite self `crit_rate` slice는 새 scheduler 없이 기존 periodic runtime을 재사용했고, Moris successful activation 시각을 직접 대조해 검증했다.

## 2026-09-05 — raw weapon-hit state는 이미 소유한 물리 boundary를 재사용할 때 가장 싸다

- 모든 hit-trigger 상태가 global per-shot scheduler를 요구하는 것은 아니다.
- dynamic charge runtime이 해당 actor의 실제 shot boundary를 이미 소유한다면, 필요한 raw hit signal만 post-shot에 노출하고 state activation 뒤 cadence sync를 수행하는 편이 Fast 설계에 맞다.
- 핵심 ordering은 `shot/score -> hit trigger -> state activation -> cadence sync`다. triggering shot에 새 cadence 상태를 소급 적용하면 안 된다.
- blocker 제거만 보지 말고 Moris/Fast의 실제 activation sequence와 다음 shot interval을 직접 대조하면 ordering proof가 강해진다.

## 2026-09-05 — recipient semantic event는 consumer shape보다 source proof가 우선이다

- `event:stat_applied:*`처럼 provider 적용 결과로 생기는 이벤트는 consumer가 구조적으로 executable이라는 이유만으로 score-safe가 아니다. 실제 recipient에게 도달 가능한 모든 source provider를 증명해야 한다.
- runtime source proof와 score source proof를 같은 conservative helper로 공유하면 한쪽만 broad-enable되는 drift를 줄일 수 있다.
- negative state condition을 고정값으로 취급하려면 반대 state의 source가 해당 recipient에 도달할 수 없음을 증명해야 한다. 반대 source가 하나라도 가능하면 fail closed가 맞다.
- dynamic cadence path도 named-event consumer라면 structural executability 뒤 source certification을 반드시 통과해야 한다.


## 2026-09-05 — fixed periodic enemy state는 broad timing support가 필요하지 않다

- periodic effect 하나가 기존 nominal-grid scheduler와 ActiveEffectStore로 완전히 표현된다면 `damage_policy` 전체에 periodic timing을 열 필요가 없다.
- structural helper에서 stat, polarity, target singleton, finite lifetime, stack shape, static enemy condition, exact capability blockers를 묶고 `_is_score_safe_fixed_periodic()`에만 추가하면 훨씬 좁게 ownership할 수 있다.
- periodic activation 시각만 맞추지 말고 stack/value trace와 condition-negative case까지 Moris와 직접 비교한다.
- 반대로 `effect_interval`처럼 이미 예약된 periodic deadline 자체를 바꾸는 stat은 같은 범주가 아니다. fixed-grid certification과 dynamic grid mutation을 분리해 fail closed해야 한다.
