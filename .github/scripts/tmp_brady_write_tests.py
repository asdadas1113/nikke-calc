from __future__ import annotations

from pathlib import Path

PRODUCTION_SHA = "8880049678c9270de8d7b98c456b93fa00a67502"
CHECKPOINT = Path("fast_engine/research/STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md")
HANDOFF = Path("fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md")
LESSONS = Path("fast_engine/research/LESSONS.md")


def write_checkpoint() -> None:
    CHECKPOINT.write_text(
        '''# Fast Engine — recipient stat-applied charge-speed checkpoint (2026-09-05)

## 1. 목적

Cinderella checkpoint 뒤 public cadence frontier `64`에서 다음 작은 generic ownership을 재분류했다. all-allies reload/max-ammo는 unsafe recipient와 결합돼 있었고, Snow White `charge_time_fixed`는 weapon-change와 결합돼 있어 독립 slice로 부적합했다.

이번 anchor는 `레이드_앨리스브래디`의 Brady `나누고 싶은 맛`이다.

- effect: `buff`
- stat: `charge_speed_pct -20`
- target: `self`
- duration: `50s`
- max stack: `1`
- trigger: `event:stat_applied:split_dmg_pct`
- condition: `not_self_state:머물고 싶은 맛`
- capability blocker: exactly `timing:named_event`

목표는 Brady 이름을 특별취급하는 것이 아니라, recipient에게 특정 stat buff가 실제 적용된 직후 발생하는 좁은 `stat_applied` semantic event와 그 source proof를 generic하게 소유하는 것이다.

## 2. Moris 의미론과 runtime 재사용

Moris `calculator/buff_manager.py`는 일반 buff activation이 성공한 뒤 stat이 `dot_dmg_pct` 또는 `split_dmg_pct`이면 각 실제 ally recipient에게 같은 시각 다음 이벤트를 notify한다.

- `event:stat_applied:dot_dmg_pct`
- `event:stat_applied:split_dmg_pct`

이 이벤트는 broad named-event broadcast가 아니다. 실제 provider target별 recipient-scoped event이며 refresh에서도 다시 발생한다.

Fast는 새 frame loop나 global shot loop를 추가하지 않았다. 기존 `TriggerDispatcher`의 actor-scoped event bucket과 `ActiveEffectStore`를 재사용한다.

ordering은 다음과 같다.

1. provider buff target 해석
2. provider activation / refresh
3. 기존 provider-name event가 있으면 그 event 처리
4. 지원 stat이면 각 concrete ally recipient에게 `event:stat_applied:{stat}` dispatch
5. consumer activation
6. 기존 dynamic charge cadence sync

따라서 stat을 실제로 받지 않은 actor에게 이벤트를 broadcast하지 않는다.

## 3. narrow certification / source proof

structural consumer helper는 다음 조건만 허용한다.

- capability disposition `PLANNED`
- blocker set exactly `{timing:named_event}`
- effect type `buff`
- stat `charge_speed_pct`
- target `SELF`
- value `> -100`
- positive finite-lifetime shape
- max stack absent or `1`
- no max trigger / tick interval / parameters
- exactly one EVENT trigger
- event key가 `event:stat_applied:dot_dmg_pct` 또는 `event:stat_applied:split_dmg_pct`
- condition 없음, 또는 exactly one `NOT_SELF_STATE`

하지만 structural executable만으로 score를 열지 않는다. `stat_applied_dependency_score_safe()`가 모든 가능한 source provider를 별도로 증명해야 한다.

- consumer actor를 실제 target으로 삼을 수 있는 source provider가 최소 하나 존재해야 한다.
- 모든 가능한 provider가 executable buff여야 한다.
- provider target scope가 runtime-safe여야 한다.
- provider 자체가 다른 named-event source proof에 의존하면 닫는다.
- `NOT_SELF_STATE`가 있으면 반대 상태를 만들 수 있는 source stat이 해당 recipient에게 도달 가능한지 검사한다.
- 반대 source가 하나라도 가능하면 condition을 immutable로 간주하지 않고 fail closed한다.

또한 dynamic charge score path도 이제 executable 여부만 보지 않고 named-event source proof를 통과해야 한다. 이는 이번 Brady slice가 드러낸 기존 certification hole을 함께 닫는다.

## 4. Brady public proof / runner-only A/B

public `레이드_앨리스브래디`에서 Brady의 관련 effect는 네 개다.

- `머물고 싶은 맛`: `dot_dmg_pct` stat-applied -> self charge speed -20
- `머물고 싶은 맛 2`: opposing named-buff remove
- `나누고 싶은 맛`: `split_dmg_pct` stat-applied -> self charge speed -20, `not_self_state:머물고 싶은 맛`
- `나누고 싶은 맛 2`: opposing named-buff remove

이 public membership에서는 Brady에게 도달 가능한 `split_dmg_pct` provider가 존재하고 `dot_dmg_pct` provider는 없다. 따라서 split branch의 negative condition은 이 membership에서 immutable true로 증명되며, dot branch는 source-unreachable이다. 두 remove effect는 계속 unsupported다.

runner-only A/B:

- run: `33929600782`
- job: `101205337651`
- result: success

40초 trace에서 Fast와 Moris의 `나누고 싶은 맛` activation sequence가 정확히 일치했다.

- `3.1999999999999935`
- `15.733333333333695`
- `15.933333333333705`
- `28.266666666666342`
- `28.46666666666633`

provider refresh가 일어날 때도 `stat_applied`가 다시 emit되어 sequence가 유지됐다. synthetic하게 반대 `dot_dmg_pct` source를 만들면 split branch source proof는 즉시 false가 되어 fail closed로 돌아갔다.

A/B gate:

- semantic trace: success
- focused regressions: success
- full Fast: `254/254`
- standardized public ranking probe: success

## 5. public blocker / ranking delta

이 helper는 unique-23 public memberships에서 source-certified consumer를 정확히 하나만 연다.

- `레이드_앨리스브래디 / 브래디 / 나누고 싶은 맛 / event:stat_applied:split_dmg_pct`

Brady `머물고 싶은 맛` cadence blocker와 두 remove effect 관련 unsupported semantics는 그대로 남는다.

public accounting:

- source cases: `24`
- unique ordered memberships: `23`
- certified: `2`
- coverage gaps: `21`
- cadence blocker family: `64 -> 63`

이번에는 standardized ranking probe도 실제 재실행했다.

- clean relative error median: `0.0006268322047938701`
- min: `0.000349533271479352`
- max: `0.0009041311381083883`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`
- unsupported family: none

blocker family counts:

- cadence `63`
- skill_state_delivery `45`
- normal_delivery `44`
- skill_damage `27`
- weapon_change `12`
- normal_state `7`
- control `6`
- periodic_grid `1`

## 6. production promotion

production semantic commit:

- `8880049678c9270de8d7b98c456b93fa00a67502` — `fast: certify recipient stat-applied charge speed`

promotion final run:

- run: `33929914438`
- job: `101206236343`
- focused production regressions: `33/33`
- full Fast production regressions: `258/258`
- intended production diff whitelist: success
- production commit/push: success

permanent regression:

- `fast_engine/tests/test_damage_stat_applied_charge_speed.py` — 4 tests
- `fast_engine/tests/test_damage_full_charge_hit_charge_speed.py` — chained public cadence expectation `64 -> 63`

promotion 전 실패들은 production semantic failure가 아니었다. 첫 시도는 workflow/harness parse 문제였고, 다음 시도는 `git diff --name-only`가 untracked 새 테스트를 보지 못한 whitelist 문제였다. untracked까지 포함한 whitelist로 고친 최종 promotion이 통과했다.

## 7. fail-closed 유지

이번 checkpoint는 다음을 지원한다고 주장하지 않는다.

- arbitrary `stat_applied:*` family
- `dot_dmg_pct`/`split_dmg_pct` 외 stat-applied event
- source가 없는 consumer 추측 실행
- source provider 일부가 unsupported인데 나머지만 보고 certification
- 반대 state source가 가능한 mutual-exclusion branch
- Brady의 opposing named-buff remove semantics
- arbitrary finite negative charge-speed families
- all-allies reload/max-ammo unsafe recipient 무시
- broad/cross-class weapon change
- global shot/frame chronology

특히 consumer shape가 executable이라는 사실과 score source가 증명됐다는 사실을 분리한다.

## 8. canonical CI

production semantic promotion 자체는 runner에서 full Fast `258/258`까지 통과했다.

cleanup 뒤 `.github/workflows`를 `ci.yml`, `pages.yml`만 남긴 clean HEAD에서 canonical CI를 다시 실행한다. 이 절의 최종 run/job/count는 clean canonical 결과가 확보된 뒤 기록한다.
''',
        encoding="utf-8",
    )


def update_handoff() -> None:
    text = HANDOFF.read_text(encoding="utf-8")
    text = text.replace(
        "1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`\n2. `fast_engine/research/FULL_CHARGE_HIT_CHARGE_SPEED_CHECKPOINT_20260905.md`",
        "1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`\n2. `fast_engine/research/STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md`\n3. `fast_engine/research/FULL_CHARGE_HIT_CHARGE_SPEED_CHECKPOINT_20260905.md`",
        1,
    )
    # Renumber the remaining early list only for readability.
    for old, new in [("10. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`", "11. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`"),
                     ("9. `fast_engine/research/CROWN_SELF_STACK_HEAL_CHECKPOINT_20260904.md`", "10. `fast_engine/research/CROWN_SELF_STACK_HEAL_CHECKPOINT_20260904.md`"),
                     ("8. `fast_engine/research/COVERAGE_FRONTIER_CHECKPOINT_20260904.md`", "9. `fast_engine/research/COVERAGE_FRONTIER_CHECKPOINT_20260904.md`"),
                     ("7. `fast_engine/research/PATTERNLESS_ENCOUNTER_EVENT_CHECKPOINT_20260905.md`", "8. `fast_engine/research/PATTERNLESS_ENCOUNTER_EVENT_CHECKPOINT_20260905.md`"),
                     ("6. `fast_engine/research/ADA_ONE_SHOT_CHARGE_SPEED_CHECKPOINT_20260905.md`", "7. `fast_engine/research/ADA_ONE_SHOT_CHARGE_SPEED_CHECKPOINT_20260905.md`"),
                     ("5. `fast_engine/research/ADA_CHARGE_HOLD_CONTROL_CHECKPOINT_20260905.md`", "6. `fast_engine/research/ADA_CHARGE_HOLD_CONTROL_CHECKPOINT_20260905.md`"),
                     ("4. `fast_engine/research/TOVE_AMMO_PCT_NAMED_EVENT_CHECKPOINT_20260905.md`", "5. `fast_engine/research/TOVE_AMMO_PCT_NAMED_EVENT_CHECKPOINT_20260905.md`"),
                     ("3. `fast_engine/research/PERIODIC_FINITE_SELF_CRIT_CHECKPOINT_20260905.md`", "4. `fast_engine/research/PERIODIC_FINITE_SELF_CRIT_CHECKPOINT_20260905.md`")]:
        text = text.replace(old, new, 1)

    old_latest = '''현재 최신 production semantic commit:

- `721cd9a8720766c14a814eb8973ca5cd685d7c73` — full-charge-hit permanent self `charge_speed_pct` certification

직전 production semantic commit:

- `fee2fe343cf75861185dd780d9191bbf6f48da8f` — finite periodic self `crit_rate` state certification
'''
    new_latest = '''현재 최신 production semantic commit:

- `8880049678c9270de8d7b98c456b93fa00a67502` — recipient-scoped `stat_applied` finite self `charge_speed_pct` certification

직전 production semantic commit:

- `721cd9a8720766c14a814eb8973ca5cd685d7c73` — full-charge-hit permanent self `charge_speed_pct` certification
'''
    if old_latest not in text:
        raise SystemExit("handoff latest production marker missing")
    text = text.replace(old_latest, new_latest, 1)

    text = text.replace(
        "latest standardized public ranking은 certified universe가 2개일 때의 기존 결과를 유지한다.",
        "latest standardized public ranking은 Brady stat-applied candidate gate에서 실제 재실행했고 certified universe는 여전히 2개다.",
        1,
    )
    text = text.replace(
        "이번 Cinderella full-charge-hit charge-speed slice 뒤에도 certified count가 `2`라 ranking probe는 재실행하지 않았다.",
        "Brady stat-applied gate run `33929600782`에서 ranking probe를 재실행했고 수치가 유지됐다. 최신 cadence blocker family는 `63`이다.",
        1,
    )

    # Shift existing recent sections before inserting the new latest one.
    text = text.replace("## 1B. 직전 완료 — finite periodic self crit", "## 1C. 그 이전 완료 — finite periodic self crit", 1)
    text = text.replace("## 1A. 최신 완료 — full-charge-hit self charge speed", "## 1B. 직전 완료 — full-charge-hit self charge speed", 1)
    insert_marker = "## 1B. 직전 완료 — full-charge-hit self charge speed"
    new_section = '''## 1A. 최신 완료 — recipient stat-applied charge speed

Brady `나누고 싶은 맛`을 anchor로 recipient-scoped `event:stat_applied:split_dmg_pct` 뒤 finite self `charge_speed_pct`를 좁게 generic certification했다.

production:

- `8880049678c9270de8d7b98c456b93fa00a67502`

Moris는 `dot_dmg_pct`/`split_dmg_pct` buff가 실제 ally recipient에게 적용된 직후 같은 시각 recipient-scoped `stat_applied` event를 notify한다. Fast도 기존 actor-scoped dispatcher를 재사용하며, source provider가 해당 recipient에게 실제로 도달 가능하고 모든 가능한 source가 executable임을 별도 proof한다.

public `레이드_앨리스브래디`에서는 split provider가 있고 dot provider가 없으므로 `not_self_state:머물고 싶은 맛`을 immutable true로 증명할 수 있다. synthetic opposite source를 추가하면 즉시 fail closed한다. Brady의 dot branch와 두 opposing remove effect는 계속 닫혀 있다.

A/B run `33929600782` / job `101205337651`:

- Fast/Moris split activation 5개 시각 exact match
- focused success
- full Fast `254/254`
- standardized ranking probe success
- cadence blocker family `64 -> 63`

production promotion run `33929914438` / job `101206236343`:

- focused production `33/33`
- full Fast `258/258`
- production diff whitelist success
- production commit/push success

상세:

- `fast_engine/research/STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md`

---

'''
    if insert_marker not in text:
        raise SystemExit("handoff latest-section marker missing")
    text = text.replace(insert_marker, new_section + insert_marker, 1)

    start = text.index("## 7. 다음 단일 checkpoint")
    end = text.index("## 8. 고정 원칙")
    text = text[:start] + '''## 7. 다음 단일 checkpoint

다음 작업은 **Brady slice 이후 cadence `63` 기준으로 unique-23 frontier를 다시 shape 단위로 분류하고, 다음 작은 generic ownership을 하나만 고르는 것**이다.

기존 no-patch/hold 축은 그대로 제외한다.

- Mihara / executable `squad_body_hit`
- Little Mermaid / `squad_ammo_consume`
- Crown external heal
- broad/cross-class weapon change
- opposite-source가 가능한 Brady mutual-exclusion/remove 확장

직전 frontier에서 all-allies reload/max-ammo는 unsafe recipient와 결합돼 있었고 Snow White `charge_time_fixed`는 weapon-change와 결합돼 있었다. 따라서 다음 후보를 이 둘 중 하나로 미리 고정하지 말고 cadence-63 frontier를 fresh audit한다.

다음 production slice도 real Moris semantic probe, existing runtime reuse, public source scope, negative fail-closed case를 먼저 증명한다. certified count와 무관하게 comparison-critical semantics를 건드리면 standardized ranking probe를 재실행해도 된다.

목표는 blocker 숫자를 줄이는 것이 아니라 comparison-critical 의미론을 증명할 수 있는 작은 generic ownership을 늘리는 것이다.

---

''' + text[end:]

    start = text.index("## 9. CI / cleanup 계약")
    text = text[:start] + '''## 9. CI / cleanup 계약

이번 Brady checkpoint의 production semantic commit은 `8880049678c9270de8d7b98c456b93fa00a67502`다.

finalizer는 `STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md`, handoff, `LESSONS.md`를 갱신하고 다음 조사용 파일을 같은 cleanup commit에서 제거한다.

- `.github/workflows/tmp-frontier-next-20260905.yml`
- `.github/scripts/tmp_brady_stat_applied_ab.py`
- `.github/scripts/tmp_brady_write_tests.py`

cleanup 뒤 `.github/workflows`에는 `ci.yml`, `pages.yml`만 남겨야 한다.

bot cleanup commit은 recursive push CI를 만들지 않으므로, user-authored checkpoint metadata commit으로 canonical CI를 다시 실행한다. 최종 run/result는 `STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md`의 canonical CI 절에 기록한다.

`master`는 그대로 둔다.
'''
    HANDOFF.write_text(text, encoding="utf-8")


def update_lessons() -> None:
    text = LESSONS.read_text(encoding="utf-8").rstrip() + "\n"
    heading = "## 2026-09-05 — recipient semantic event는 consumer shape보다 source proof가 우선이다"
    if heading in text:
        return
    text += f'''\n{heading}\n\n- `event:stat_applied:*`처럼 provider 적용 결과로 생기는 이벤트는 consumer가 구조적으로 executable이라는 이유만으로 score-safe가 아니다. 실제 recipient에게 도달 가능한 모든 source provider를 증명해야 한다.\n- runtime source proof와 score source proof를 같은 conservative helper로 공유하면 한쪽만 broad-enable되는 drift를 줄일 수 있다.\n- negative state condition을 고정값으로 취급하려면 반대 state의 source가 해당 recipient에 도달할 수 없음을 증명해야 한다. 반대 source가 하나라도 가능하면 fail closed가 맞다.\n- dynamic cadence path도 named-event consumer라면 structural executability 뒤 source certification을 반드시 통과해야 한다.\n'''
    LESSONS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    write_checkpoint()
    update_handoff()
    update_lessons()
