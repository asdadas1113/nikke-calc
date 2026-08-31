# Fast Engine capability manifest

Generated from the current Moris parsed-skill snapshot and the **certified current Fast runtime profile**.
Structural representability is not the same as runtime support: a generic effect remains `planned` until its primitive is implemented and parity/recall-tested.

- characters: **202**
- effects: **1799**

## Runtime dispositions

| disposition | effects |
| --- | ---: |
| `fallback` | 3 |
| `mirror_moris_nop` | 159 |
| `planned` | 1598 |
| `ready` | 39 |

## Semantic categories

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

## Explicit fallback surface

- `신데렐라 : 크리스탈 웨이브` — `squad_ammo_consume_as` — 저격 모드 탄 소비 집계 (special:squad_ammo_consume_as)
- `아인` — `feather_refresh` — 페더 스탠바이 (special:feather_refresh)
- `아인` — `feather_refresh` — 페더 올레인지 (special:feather_refresh)

## Interpretation

- `ready`: primitive is certified in the current runtime revision.
- `planned`: structurally understood but not yet certified in production Fast.
- `mirror_moris_nop`: Moris authority currently ignores the effect; Fast mirrors that behavior and it does not block routing.
- `model_excluded`: intentionally omitted by the patternless Fast enemy contract.
- `fallback`: explicit special subsystem/Moris route until implemented.
- `unknown`: audit failure; never silently approximate it.

Only primitives with direct runtime tests are marked `ready`. A structurally expressible effect remains `planned` until its timing, conditions, targets and operation are certified together.
