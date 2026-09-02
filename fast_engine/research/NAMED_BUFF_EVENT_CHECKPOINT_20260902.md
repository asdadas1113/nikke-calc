# Fast Engine deterministic named-buff event checkpoint — 2026-09-02

## Scope

This checkpoint adds a narrow, fail-closed bridge for Moris `event:[buff name]` activation semantics.

It does **not** mean arbitrary named events are now supported. A consumer is score-certifiable only when the current compiled squad contains a concrete matching named **buff** provider whose activation path Fast can already execute deterministically.

The purpose of the slice is to preserve Fast's sparse-event architecture while covering named-buff dependency chains such as Mint `떼창` -> Frika `앵콜`.

## Moris semantics confirmed

`calculator/buff_manager.py` establishes the following ordering:

1. The named buff is inserted/refreshed in active state first.
2. On a new activation, `event:{name}` is broadcast.
3. The default audience is the whole squad; `event_scope: recipients` narrows it to recipients.
4. A non-stacking (`max_stack == 1`) refresh while already active does not re-broadcast the named activation event.
5. A stacking activation does broadcast again.

This checkpoint mirrors that ordering. Consumers therefore observe the producer state as already active on the same timestamp.

## Provider proof

Generic named-event consumers remain fail-closed unless all matching providers satisfy the narrow source contract:

- provider type is `buff`;
- provider name exactly matches the `event:{name}` key;
- provider target is runtime-resolvable;
- provider is already executable by Fast under existing timing/condition/stat contracts;
- provider is not itself dependent on another generic named event in this first slice;
- event scope is the normal squad broadcast or explicit recipients scope.

This prevents runtime parsing from becoming score certification by itself.

Examples intentionally still blocked:

- Crown `로얄 에타이어 4` / `event:heal_received`: no deterministic matching named-buff provider exists, and HP/heal chronology remains deferred.
- Nayuta `event:기억 흡수` chain: the matching provider is a periodic stacking state outside this narrow deterministic provider contract.

## Named duration extension

Fast now owns a narrow `named_buff_duration_extend` operation for positive finite time extensions.

Semantics follow Moris:

- `target_effect: X` extends active `X` and `X ...` sibling states;
- infinite states are unchanged;
- bullet-lifetime states remain fail-closed;
- expiry generation is replaced and a new sparse `STATE_EXPIRE` boundary is scheduled;
- the old expiry becomes stale through the existing generation-token contract.

No frame loop was added.

## Frika / Mint chain

The public Frika chain is now represented as one coherent deterministic loop rather than enabling only its damage row:

- Frika `퍼포먼스`: active state dependency.
- Mint `떼창`: already-executable named buff provider.
- Frika `앵콜`: extends `퍼포먼스` family duration by 21 s.
- Frika `앵콜 2`: all-allies `atk_dmg_pct` buff.
- Frika `앵콜 3`: signed burst cooldown adjustment; its negative value correctly extends cooldown through the existing `BurstMachine.adjust_cooldown` contract.
- Frika `무대 파트 : 보컬`: named marker state on Mint.

The implementation is generic and contains no Frika/Mint character-name branches.

## Tests

Implementation commit:

`c87abf6` — `impl: bridge deterministic named buff events`

Focused validation on the implementation runner:

- named-buff runtime tests: 4/4 pass;
- shield runtime regression: 4/4 pass;
- full Fast test discovery: 187/187 pass.

The named-buff tests cover:

1. Frika `앵콜 2` public damage delivery certification.
2. Mint `떼창` broadcast activating the complete supported Encore chain.
3. generation-safe duration extension past the original expiry.
4. Nayuta and Crown examples staying blocked when provider proof fails.

## Standard public coverage audit

The current `context.snapshot.SQUADS` also contains `지그_*` entries, but the established public audit universe remains the fixed non-`지그_*` 24 five-person squads.

Post-implementation audit:

- standard teams: 24;
- certified: 1;
- coverage gaps: 23;
- certified team: `컨트롤_미란다미하라`.

Therefore ranking validation still does **not** start.

For `레이드_레드후드퀀시`, Frika's named-event damage blocker disappeared. The team is now:

- raw blockers: 5;
- conceptual blockers: 4;
- remaining conceptual blockers:
  - Red Hood `글레링 아이즈:charge_speed_pct` cadence;
  - Mint `다 함께 불러주세요! 2:max_ammo_pct` cadence;
  - Red Hood `글레링 아이즈 2:charge_speed_overflow_conversion_pct` normal-state formula;
  - Red Hood `와일드 투스 4:atk_pct` delivery.

The named-event slice improved frontier coverage but did not produce the second certified public team.

## Deferred boundaries remain unchanged

Do not use this checkpoint as justification to open:

- Crown `heal_received` / HP-heal-lifesteal chronology;
- arbitrary external `event:*` keys;
- periodic named-event providers;
- live `max_ammo_pct` semantics;
- unsupported manual charge/control paths;
- candidate generation.

## Next checkpoint

Continue from the refreshed non-Crown frontier. Prefer another small generic contract with measurable public blocker reduction. If any future slice raises certified public teams from 1 to at least 2, stop coverage expansion immediately and begin Fast-vs-Moris pairwise/ranking validation as a separate checkpoint.
