# Patternless `squad_part_hit` checkpoint — 2026-09-05

## 결론

표준 Fast static score의 patternless enemy에서는 `squad_part_hit` consumer를 비교-critical blocker로 세지 않는다.

이번 변경은 **part-hit runtime 구현이 아니다**. `TriggerDispatcher`와 weapon runtime은 그대로 두고, 기존 patternless-unreachable blocker hygiene에 `squad_part_hit` 한 key만 추가했다.

`global squad_body_hit` ownership은 이번 범위에 포함하지 않았고 계속 fail closed다.

## 근거

표준 Moris enemy는 `has_parts=False`다. D : 킬러 와이프가 포함된 `레이드_미하라에이다`를 30초 expected mode로 직접 비교했다.

- 기본 enemy (`has_parts=False`): D `타겟 섬멸 코어` activation **0회**
- 동일 enemy에 `has_parts=True`만 적용: D `타겟 섬멸 코어` activation **349회**

따라서 `squad_part_hit`은 실제 존재하는 event지만 현재 표준 patternless comparison domain에서는 도달 불가능하다.

A/B diagnostic:

- run `33942161302`
- job `101241562693`
- Moris reachability boundary success
- local checkout-only patch 뒤 public blocker delta가 정확히 아래 2개뿐임을 확인
  - `normal_delivery:D : 킬러 와이프:타겟 섬멸 코어:core_dmg_pct`
  - `skill_state_delivery:D : 킬러 와이프:타겟 섬멸 코어:core_dmg_pct`
- added blocker 없음
- certified universe 변화 없음
- Fast damage `158/158`

## Production

production semantic commit:

- `745d9f1afcf10d092bb58bf9e0235724a5c41946` — `Fast: ignore patternless squad part hit`

변경 파일:

- `fast_engine/engine/score.py`
  - `_PATTERNLESS_UNREACHABLE_EVENT_KEYS`에 `squad_part_hit` 추가
- `fast_engine/tests/test_damage_patternless_encounter_events.py`
  - part-hit blocker는 제거되지만 D `squad_body_hit` normal/skill blocker는 그대로 남는 영구 회귀 추가
  - `squad_part_hit` effect 자체는 dispatcher executable로 승격하지 않음을 명시적으로 고정

promotion gate:

- run `33942326300`
- job `101242018963`
- focused patternless tests `4/4`
- full Fast damage `159/159`
- public `23 unique / 2 certified`
- blocker family:
  - `cadence 63`
  - `skill_state_delivery 43`
  - `normal_delivery 41`
  - `skill_damage 27`
  - `weapon_change 12`
  - `normal_state 7`
  - `control 6`
  - `periodic_grid 1`
- `레이드_미하라에이다`: `8 -> 6` blockers
- 남은 D blocker:
  - `normal_delivery:D : 킬러 와이프:타겟 섬멸 ATK:atk_caster_based_pct`
  - `skill_state_delivery:D : 킬러 와이프:타겟 섬멸 ATK:atk_caster_based_pct`
  - 둘 다 `squad_body_hit`이며 계속 fail closed

## Clean validation

임시 workflow 제거 commit:

- `41d9d6630c303ae13435fa00e4c391683e15648f`

clean canonical CI:

- run `33942375704`
- job `101242188029`
- result: success
- Fast damage `159/159`
- calculator `137/137` (`1 skip`)
- optimizer `374/374`
- bridge `31/31` (`1 skip`)
- site `385/385`
- golden snapshot `29/29`

cleanup 뒤 `.github/workflows`는 다시 `ci.yml`, `pages.yml`만 남았다.

## 다음 재개 지점

낮은 blocker frontier는 현재 명시적으로 보류한 항목 비중이 높다. 다음에는 fresh frontier를 다시 분류해 **비보류 small generic ownership 1개**를 새로 선정한다.

계속 보류:

- Little Mermaid `squad_ammo_consume`
- Crown arbitrary external `heal_received`
- global `squad_body_hit`
- Ada `effect_interval`
- Neon gauge chronology
- broad weapon-change ownership
- broad HP chronology
- broad reload / max-ammo expansion

이번 checkpoint를 이유로 위 항목을 암묵적으로 확장하지 않는다.
