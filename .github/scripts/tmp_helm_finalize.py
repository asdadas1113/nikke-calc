from __future__ import annotations

from pathlib import Path

PROD = "4a6cbe388cd0ef32ec07e5b825078fe457619181"
AB_RUN = "33932690769"
AB_JOB = "101214374980"
PROMO_RUN = "33932866252"
PROMO_JOB = "101214901667"


def write_checkpoint() -> None:
    path = Path("fast_engine/research/PERIODIC_ENEMY_RECEIVED_DAMAGE_CHECKPOINT_20260905.md")
    path.write_text(f'''# Fast Engine — periodic enemy received-damage checkpoint (2026-09-05)

## 1. 목적

Brady checkpoint 이후 cadence `63` unique-23 frontier를 다시 비교했다. 다음 후보로 Ada `effect_interval`, Neon : Vision Eye `초화력`, Helm : Aquamarine `이지스 캐논 견제 사격 2`를 Moris 의미론과 기존 Fast runtime 재사용 가능성 기준으로 비교했다.

- Ada `effect_interval`은 Moris가 이미 예약된 periodic deadline을 실시간 재스케일하는 동적 grid mutation이라 독립 slice가 아니었다.
- Neon `초화력`은 `화력 게이지 == 100`을 요구해 gauge chronology가 선행된다.
- Helm : Aquamarine의 enemy `received_dmg_pct`는 기존 fixed periodic scheduler, enemy state store, damage resolver를 그대로 재사용할 수 있었다.

따라서 이번 anchor는 `레이드_헬름아쿠아스노우`의 `이지스 캐논 견제 사격 2`다.

실제 shape:

- effect type: `buff`
- stat: `received_dmg_pct +5.64`
- polarity: `harmful`
- target: enemy singleton (`same_target` -> Fast `ENEMY`)
- duration: `5s`
- max stack: `5`
- trigger: fixed periodic `every:4s`
- condition: `target_code:전격`
- parameters: none
- capability blockers exactly:
  - `category:hit_formula`
  - `stat:received_dmg_pct`
  - `timing:periodic`
  - `condition:enemy`
  - `target:enemy_singleton`

## 2. runtime 재사용

새 periodic scheduler나 1/60 loop를 추가하지 않았다.

Fast의 기존 `BurstRuntime._schedule_initial_periodics()`는 nominal interval을 `moris_observed_tick()`로 outer-tick 시각에 맞춰 예약하고, 이후 `PERIODIC_TICK -> TriggerDispatcher.dispatch_periodic() -> ActiveEffectStore` 경로를 사용한다.

`received_dmg_pct` 자체는 이미 enemy damage term에 반영되는 stat이다. 따라서 필요한 것은 broad timing 지원이 아니라 이 fixed-grid enemy-stack shape를 좁게 executable/score-safe로 인정하는 것이다.

`_periodic_finite_enemy_received_damage_shape_supported()`는 다음을 모두 요구한다.

- capability disposition `PLANNED`
- blocker set이 위 5개와 정확히 동일
- `buff / harmful / received_dmg_pct`
- enemy singleton runtime target
- non-negative numeric value
- positive finite duration
- integer `max_stack >= 1`
- no max-trigger / tick-interval / parameters
- exactly one `TARGET_CODE` condition with a concrete code
- exactly one positive fixed `PERIODIC` trigger

이 helper만 `TriggerDispatcher.is_executable_effect()`와 `_is_score_safe_fixed_periodic()`에 추가했다. broad `damage_policy` periodic timing은 열지 않았다.

## 3. Moris/Fast semantic A/B

runner-only A/B:

- run `{AB_RUN}`
- job `{AB_JOB}`
- result `success`

전격 enemy, 25초 구간에서 Fast와 Moris의 activation 시각이 6개 모두 정확히 일치했다.

- `4.016666666666658`
- `8.016666666666644`
- `12.000000000000176`
- `16.000000000000373`
- `20.000000000000146`
- `24.016666666666584`

스택과 누적값도 일치했다.

- stack: `1 -> 2 -> 3 -> 4 -> 5 -> 5`
- `received_dmg_pct`: `5.64 -> 11.28 -> 16.92 -> 22.56 -> 28.2 -> 28.2`

동일 squad에서 enemy code를 `작열`로 바꾸면 Fast와 Moris 모두 activation `0회`였다. 즉 target-code condition도 static enemy profile로 정확히 닫힌다.

## 4. regression / fail-closed

새 permanent regression:

- `fast_engine/tests/test_damage_periodic_enemy_received.py` — 4 tests

검증 범위:

1. real Helm shape와 blocker delta
2. Moris/Fast activation + stack/value trace exact match
3. target-code mismatch에서 양쪽 모두 0회
4. condition 제거, fractional max stack, beneficial polarity 등 neighboring shape fail closed

기존 `test_damage_periodic_self_crit.py`도 과거의 “Helm enemy stack은 미지원” expectation만 갱신했고, Ada `effect_interval`을 새로운 neighboring fail-closed anchor로 유지했다.

의도적으로 계속 닫는 축:

- arbitrary periodic enemy buffs/debuffs
- broad periodic timing in `damage_policy`
- dynamic periodic-grid mutation (`effect_interval`, `skill_cooldown_pct`, `skill_cooldown_reduce_pct`, `force_skill_use`)
- non-static enemy condition chronology
- missing/unsupported target-code condition
- non-enemy target variants
- beneficial `received_dmg_pct` variant
- non-integer stack shape

## 5. public blocker / ranking delta

A/B 후 `레이드_헬름아쿠아스노우`의 Helm blocker 2개가 제거됐다.

제거:

- `normal_delivery:헬름 : 아쿠아마린:이지스 캐논 견제 사격 2:received_dmg_pct`
- `skill_state_delivery:헬름 : 아쿠아마린:이지스 캐논 견제 사격 2:received_dmg_pct`

남음:

- `weapon_change:스노우 화이트:세븐스 드워프 : I`
- `normal_delivery:스노우 화이트:세븐스 드워프 : I 2:pierce_enabled`
- `periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval`

public accounting은 그대로다.

- source cases `24`
- unique memberships `23`
- certified `2`
- coverage gaps `21`

blocker family delta:

- cadence `63` 유지
- skill_state_delivery `45 -> 44`
- normal_delivery `44 -> 43`
- skill_damage `27`
- weapon_change `12`
- normal_state `7`
- control `6`
- periodic_grid `1`

standardized ranking probe도 실제 재실행했다.

- clean relative error median `0.0006268322047938701`
- min `0.000349533271479352`
- max `0.0009041311381083883`
- pairwise accuracy `1.0`
- top-N recall `1.0`
- unsupported family none

## 6. production promotion

production semantic commit:

- `{PROD}` — `fast: certify periodic enemy received damage`

A/B final gate:

- run `{AB_RUN}` / job `{AB_JOB}`
- focused `21/21`
- full Fast `262/262`
- standardized public ranking probe success

promotion:

- run `{PROMO_RUN}` / job `{PROMO_JOB}`
- exact candidate apply success
- focused production regressions success
- full Fast `262/262`
- production diff whitelist success
- production commit/push success

## 7. 다음 checkpoint

이번 비교에서 Ada `effect_interval`은 단순 blocker 완화 대상이 아니라 실제 dynamic periodic deadline rescheduling 문제임이 확인됐다. Neon gauge branch도 gauge chronology가 선행된다. 둘 다 다음 slice로 즉시 broad-enable하지 않는다.

clean canonical CI까지 닫은 뒤 unique-23 frontier를 다시 보고 다음 작은 generic ownership을 고른다. 가까운 blocker 수만으로 Little Mermaid/Crown/Mihara/weapon-change 보류 축을 우회하지 않는다.

## 8. canonical CI

production promotion에서 full Fast `262/262`까지 검증했다.

cleanup 뒤 `.github/workflows`를 `ci.yml`, `pages.yml`만 남긴 clean HEAD에서 canonical CI를 다시 실행하고 최종 run/job/count를 이 절에 기록한다.
''', encoding="utf-8")


def update_handoff() -> None:
    path = Path("fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md")
    text = path.read_text(encoding="utf-8")

    text = text.replace(
        "1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`\n2. `fast_engine/research/STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md`",
        "1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`\n2. `fast_engine/research/PERIODIC_ENEMY_RECEIVED_DAMAGE_CHECKPOINT_20260905.md`\n3. `fast_engine/research/STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md`",
        1,
    )
    text = text.replace(
        "현재 최신 production semantic commit:\n\n- `8880049678c9270de8d7b98c456b93fa00a67502` — recipient-scoped `stat_applied` finite self `charge_speed_pct` certification\n\n직전 production semantic commit:\n\n- `721cd9a8720766c14a814eb8973ca5cd685d7c73` — full-charge-hit permanent self `charge_speed_pct` certification",
        f"현재 최신 production semantic commit:\n\n- `{PROD}` — fixed-grid periodic enemy `received_dmg_pct` certification\n\n직전 production semantic commit:\n\n- `8880049678c9270de8d7b98c456b93fa00a67502` — recipient-scoped `stat_applied` finite self `charge_speed_pct` certification",
        1,
    )
    text = text.replace(
        "latest standardized public ranking은 Brady stat-applied candidate gate에서 실제 재실행했고 certified universe는 여전히 2개다.",
        "latest standardized public ranking은 Helm periodic enemy candidate gate에서 실제 재실행했고 certified universe는 여전히 2개다.",
        1,
    )
    text = text.replace(
        "Brady stat-applied gate run `33929600782`에서 ranking probe를 재실행했고 수치가 유지됐다. 최신 cadence blocker family는 `63`이다.",
        f"Helm periodic enemy gate run `{AB_RUN}`에서 ranking probe를 재실행했고 수치가 유지됐다. 최신 blocker family는 cadence `63`, normal delivery `43`, skill-state delivery `44`다.",
        1,
    )

    marker = "## 1A. 최신 완료 — recipient stat-applied charge speed\n"
    helm_section = f'''## 1A. 최신 완료 — periodic enemy received damage

Helm : Aquamarine `이지스 캐논 견제 사격 2`를 anchor로 fixed-grid finite enemy `received_dmg_pct` stack을 좁게 generic certification했다.

production:

- `{PROD}`

새 periodic scheduler는 만들지 않았다. 기존 Moris-observed fixed periodic scheduler, enemy ActiveEffectStore, DamageTermResolver를 재사용한다. 전격 enemy에서 4초 periodic activation 6회와 stack/value가 Moris와 exact match했고, 작열 enemy에서는 양쪽 모두 0회였다.

A/B run `{AB_RUN}` / job `{AB_JOB}`:

- focused `21/21`
- full Fast `262/262`
- standardized ranking probe success
- normal delivery `44 -> 43`
- skill-state delivery `45 -> 44`

promotion run `{PROMO_RUN}` / job `{PROMO_JOB}`:

- focused success
- full Fast `262/262`
- diff whitelist success
- production commit/push success

Ada `effect_interval`은 dynamic periodic deadline rescheduling 문제라 계속 fail closed다. Neon `초화력`은 gauge chronology가 필요해 보류한다.

상세:

- `fast_engine/research/PERIODIC_ENEMY_RECEIVED_DAMAGE_CHECKPOINT_20260905.md`

---

## 1B. 직전 완료 — recipient stat-applied charge speed
'''
    if marker not in text:
        raise SystemExit("handoff latest section marker missing")
    text = text.replace(marker, helm_section, 1)
    text = text.replace("## 1B. 직전 완료 — full-charge-hit self charge speed", "## 1C. 그 이전 완료 — full-charge-hit self charge speed", 1)
    text = text.replace("## 1C. 그 이전 완료 — finite periodic self crit", "## 1D. 그 이전 완료 — finite periodic self crit", 1)

    start = text.find("## 7. 다음 단일 checkpoint\n")
    end = text.find("\n---\n\n## 8. 고정 원칙", start)
    if start < 0 or end < 0:
        raise SystemExit("handoff next checkpoint section markers missing")
    next_section = '''## 7. 다음 단일 checkpoint

Helm periodic enemy slice 뒤 unique-23 frontier를 fresh audit해 다음 작은 generic ownership을 하나만 고른다.

이번 비교에서 다음은 보류 근거가 더 명확해졌다.

- Ada `effect_interval` — Moris가 남은 periodic deadline을 재스케일하는 dynamic grid mutation
- Neon : Vision Eye `초화력` — `화력 게이지 == 100` chronology 선행 필요

기존 보류 축도 그대로 유지한다.

- Little Mermaid `squad_ammo_consume`
- Crown external `heal_received`
- Mihara/D global `squad_body_hit`
- broad/cross-class weapon change
- unsafe reload/max-ammo
- HP-derived state / generic bonus-damage broad enable

다음 slice도 real Moris semantic probe, existing runtime reuse, negative fail-closed case를 먼저 증명한다. blocker 수가 적다는 이유만으로 deferred 축을 연다거나 certified count를 인위적으로 늘리지 않는다.
'''
    text = text[:start] + next_section + text[end:]

    ci_start = text.find("## 9. CI / cleanup 완료\n")
    if ci_start >= 0:
        text = text[:ci_start] + f'''## 9. CI / cleanup 진행

이번 Helm periodic enemy production semantic commit은 `{PROD}`다.

promotion run `{PROMO_RUN}` / job `{PROMO_JOB}`에서 full Fast `262/262` 및 production diff whitelist까지 통과했다.

이번 finalizer에서 checkpoint/handoff/LESSONS를 갱신하고 조사용 temp workflow/scripts를 제거한다. cleanup 뒤 `.github/workflows`에는 `ci.yml`, `pages.yml`만 남겨야 한다.

clean HEAD canonical CI 결과를 확보한 뒤 이 절을 최종 완료 상태로 갱신한다.

`master`는 그대로 둔다.
'''
    path.write_text(text, encoding="utf-8")


def update_lessons() -> None:
    path = Path("fast_engine/research/LESSONS.md")
    text = path.read_text(encoding="utf-8")
    marker = "## 2026-09-05 — fixed periodic enemy state는 broad timing support가 필요하지 않다"
    if marker not in text:
        text += '''

## 2026-09-05 — fixed periodic enemy state는 broad timing support가 필요하지 않다

- periodic effect 하나가 기존 nominal-grid scheduler와 ActiveEffectStore로 완전히 표현된다면 `damage_policy` 전체에 periodic timing을 열 필요가 없다.
- structural helper에서 stat, polarity, target singleton, finite lifetime, stack shape, static enemy condition, exact capability blockers를 묶고 `_is_score_safe_fixed_periodic()`에만 추가하면 훨씬 좁게 ownership할 수 있다.
- periodic activation 시각만 맞추지 말고 stack/value trace와 condition-negative case까지 Moris와 직접 비교한다.
- 반대로 `effect_interval`처럼 이미 예약된 periodic deadline 자체를 바꾸는 stat은 같은 범주가 아니다. fixed-grid certification과 dynamic grid mutation을 분리해 fail closed해야 한다.
'''
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    write_checkpoint()
    update_handoff()
    update_lessons()
