# Fast Engine damage-semantics inventory

Generated from the current Moris `parsed_skills.json` plus documented implementation status.
This is a design audit, not a claim that Fast already supports these effects.

- characters: **202**
- effects: **1799**

## Category counts

| category | effects |
| --- | ---: |
| `cadence_timeline` | 207 |
| `control` | 45 |
| `damage_event` | 248 |
| `derived_state` | 252 |
| `hit_formula` | 521 |
| `hp_shield` | 159 |
| `moris_nop` | 159 |
| `special` | 3 |
| `state_trigger` | 205 |

## Unknown stats

None.

## Special / fallback surface

- `신데렐라 : 크리스탈 웨이브` — `squad_ammo_consume_as` — 저격 모드 탄 소비 집계
- `아인` — `feather_refresh` — 페더 스탠바이
- `아인` — `feather_refresh` — 페더 올레인지

## Interpretation

- `hit_formula`: state consumed directly by the single-hit damage kernel after activation/target resolution.
- `derived_state`: runtime value must be derived from ATK/HP/ammo/gauge/etc. before damage can be evaluated.
- `damage_event`: creates or releases damage and therefore needs event semantics, not only a buff scalar.
- `cadence_timeline`: changes how many attacks/bursts occur or when they occur.
- `state_trigger`: named state/stack/gauge/event plumbing that can change future effects.
- `hp_shield`: character-owned HP/shield semantics. Boss incoming-damage chronology remains outside initial Fast scope.
- `control`: control/debuff mechanics; only the subset affecting theoretical static ranking will eventually need Fast implementation.
- `moris_nop`: Moris authority currently does not implement the documented stat; Fast should initially mirror that NOP unless authority changes.
- `fast_pattern_excluded`: deliberately outside the initial patternless Fast target model.
- `special`: explicit generic/special subsystem work or Moris fallback until implemented.
- `unknown`: audit blocker. Do not silently compile to zero.

## Next gate

The current snapshot has no unknown rows. Use these categories to build the capability manifest and state/trigger store before implementing the damage kernel.
