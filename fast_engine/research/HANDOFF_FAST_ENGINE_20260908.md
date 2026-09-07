# Fast Engine 작업 인계 — 2026-09-08

## 0. 재개 원칙

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다. `calculator/`는 Moris 의미론 oracle로만 사용한다.**

Fast Engine은 Moris 복제품이 아니라 optimizer용 고속 sparse-event ranking engine이다.

금지 원칙:

- global 60Hz loop 추가 금지
- 캐릭터명 기반 runtime 분기 금지
- unsupported comparison-critical mechanic silent zero 금지
- 한 번에 하나의 semantic checkpoint만 완결
- false-supported safety closure보다 coverage 숫자를 우선하지 않음

작업 시작 시 branch HEAD와 `master`를 다시 조회한다. 이 문서의 SHA는 semantic 기준점을 기록하는 것이며 현재 HEAD 자체를 뜻하지 않을 수 있다.

먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260908.md`
2. `fast_engine/research/MIRANDA_LAZY_RANK_BULLET_LIFETIME_CHECKPOINT_20260908.md`
3. `fast_engine/research/ADA_TARGETED_EFFECT_INTERVAL_PERIODIC_GRID_CHECKPOINT_20260908.md`
4. `fast_engine/research/RAPID_TO_SINGLE_CHARGE_WEAPON_CHANGE_CHECKPOINT_20260907.md`
5. `fast_engine/research/NAYUTA_RAPID_TO_CHARGE_SKILL_WEAPON_CHANGE_WIP_CHECKPOINT_20260907.md`
6. `fast_engine/research/PRIVATY_CHARGE_LIVE_MAX_AMMO_SAFETY_CHECKPOINT_20260907.md`
7. `fast_engine/research/MORAN_RAPID_WEAPON_CHANGE_LIFECYCLE_CHECKPOINT_20260907.md`
8. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`

## 1. Protected baseline

`master` 기준 SHA:

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

Miranda 조사·promotion·cleanup 후에도 이 SHA가 불변임을 재확인했다.

## 2. Latest completed semantic checkpoint

최신 production semantic commit:

- `c877c523032459e6232547a1db21fc2db23373b8` — `Fast: support lazy rank bullet lifetimes`

완료 checkpoint:

- Miranda `웨이크업! 4`
- dynamic ATK rank target을 activation transaction의 올바른 시점에 lazy materialize
- `duration_bullets=1`을 실제 resolved recipient의 다음 live scored shot에서 소비
- 기존 bare-dispatcher atomic fail-closed 계약 유지

상세 기록:

- `fast_engine/research/MIRANDA_LAZY_RANK_BULLET_LIFETIME_CHECKPOINT_20260908.md`

## 3. Exact Miranda semantics now owned

Public source case:

- `레이드_헬름아쿠아스노우`

Effect:

- Miranda `웨이크업! 4`
- buff `crit_rate = 85.42`
- target `allies_top_atk_excl:1`
- trigger `full_burst_start`
- no time duration
- `duration_bullets = 1`

Moris oracle proved the target is not static. First five owned resolutions:

1. `3.399999999999993` → 스노우 화이트
2. `21.58333333333339` → 에이다
3. `37.56666666666582` → 스노우 화이트
4. `50.94999999999839` → 에이다
5. `64.33333333333097` → 스노우 화이트

A static rank proof would therefore be wrong.

The existing generic pending/lazy-rank infrastructure already reproduced the exact Moris sequence when forced. The production slice extends that infrastructure to this one-bullet lifetime shape rather than adding a new rank subsystem.

## 4. Ownership and fail-closed contract

`possible_ally_targets()` is intentionally conservative for dynamic rank selection, so the public effect can potentially resolve to all five members.

The public roster's possible recipients are already score-cadence-owned:

- Miranda — rapid
- Helm : Aquamarine — rapid
- Ade : Agent Bunny — charge
- Snow White — rapid / owned single-charge mode
- Ada — charge

For lazy one-bullet rank effects, score setup registers all proved recipients with the existing live dynamic bullet-lifetime machinery.

Important safety boundary:

- bare `TriggerDispatcher` keeps the previous executable + activation-time atomic fail-closed contract
- if a dynamic bullet target resolves to an actor without a live owner, activation raises rather than silently applying a stale/static lifetime
- the broader family is not opened merely because Miranda is now supported

## 5. Implementation surface

Semantic diff from promotion parent to `c877c523...` contains exactly 8 `fast_engine/` files:

- `fast_engine/engine/dispatcher.py`
- `fast_engine/engine/effects.py`
- `fast_engine/engine/score.py`
- `fast_engine/tests/test_damage_miranda_lazy_rank_bullet_lifetime.py` — new
- `fast_engine/tests/test_damage_effect_interval_periodic_grid.py`
- `fast_engine/tests/test_damage_full_charge_bullet_lifetime.py`
- `fast_engine/tests/test_damage_full_charge_hit_charge_speed.py`
- `fast_engine/tests/test_damage_stat_applied_charge_speed.py`

Stats:

- 190 insertions
- 13 deletions

`calculator/` diff: none.

The four existing test edits are stale shared-frontier expectation updates, not mechanic widening.

## 6. Promotion validation

Semantic promotion gate:

- run `34153154510`
- job `101839405882`
- result `success`

Results:

- Miranda focused `4/4`
- neighboring `25/25`
- full Fast discovery `368/368`
- performance median `181.25ms`, events `539`
- protected master assertion passed immediately before promotion
- no `calculator/` diff

## 7. Post-clean canonical CI

The first exact clean checkpoint documentation HEAD was:

- `7c595f6a199fe67651693ad47176c1934bfafd44`

Canonical CI on that exact HEAD:

- run `34153410587`
- job `101840174194`
- result `success`

Counts:

- Fast damage `254/254`
- Fast complete discovery `368/368`
- calculator `137/137` (`1` skip)
- optimizer `374/374`
- bridge `31/31` (`1` skip)
- site `385/385`
- golden snapshot `29/29`
- doclint OK
- structural performance `200.81ms` median / `539` events in the dedicated performance step

This handoff update itself creates a later documentation HEAD, so after editing this file the canonical `ci.yml` on the new exact HEAD must also be checked before handing off again.

## 8. Current public frontier

Standard `fast_engine/research/public_blocker_frontier.py` view after Miranda:

- source cases `24`
- certified source cases `7`
- source-case gaps `17`

Blocker family counts:

- cadence `55`
- control `5`
- normal_delivery `45`
- normal_state `17`
- skill_damage `25`
- skill_state_delivery `49`
- weapon_change `2`
- periodic_grid `0`

Miranda A/B:

- `normal_state: 18 → 17`
- certified `6 → 7`
- gaps `18 → 17`
- no other family count changed directly

`레이드_헬름아쿠아스노우` is now fully certified:

- blockers `()`
- unsupported `()`

## 9. Cleanup state

All temporary Miranda probe/apply/fix/workflow assets were removed after promotion.

Final `.github` root must contain only:

- `scripts/`
- `workflows/`

Final `.github/workflows` must contain only:

- `ci.yml`
- `pages.yml`

This hygiene was verified after cleanup.

## 10. Current phase

Still:

**false-supported safety closure → semantics restoration**

Recent completed restoration chain includes:

- finite self rapid weapon-change lifecycle
- sparse Moris rapid nominal-fire deadline observation
- rapid effective weapon view isolation
- Little Mermaid enemy replacement + squad ammo crossing foundation
- Crown shared lifetime/heal_received
- charge live max-ammo source quantization/clamp safety repair
- Nayuta rapid→charge skill weapon-change lifecycle
- rapid→single-charge duration-bullet weapon-change lifecycle
- Ada targeted dynamic periodic interval rescaling
- Miranda dynamic rank + one-bullet lifetime lazy materialization

Do not jump to raw coverage expansion or optimizer integration.

## 11. Next checkpoint selection

Miranda is CLOSED. Select the next single semantics-restoration checkpoint from the current `24 / 7 / 17` public frontier; do not inherit the old recommendation to work on Miranda again.

Required order:

1. query current branch HEAD and verify `master`
2. rerun/inspect the current blocker frontier and identify the closest generic candidates
3. prefer false-supported safety closure or a narrow reusable semantic slice over raw blocker count
4. inspect exact compiled shapes and dependency graph
5. execute Moris oracle traces before changing Fast semantics
6. prove ownership without character-name runtime branches or global 60Hz loops
7. focused + neighboring regression
8. full Fast discovery
9. public frontier A/B
10. semantic promotion only after all gates are green
11. cleanup temp assets
12. update checkpoint/handoff docs
13. canonical CI on the final exact clean HEAD

If a candidate widens into a broader unresolved ordering/cadence problem, leave it fail-closed and choose another single checkpoint rather than forcing certification.

## 12. Moris baseline policy

Continue using the project's fixed Moris/master baseline as the oracle for this phase.

Do not chase unrelated newer upstream Moris changes while Fast semantic restoration is still in progress. After Fast reaches the intended baseline completeness/ranking-validation state, perform a separate fixed-baseline → latest-Moris migration/audit.

Exception: if a newer Moris change is confirmed to fix the exact mechanic currently being implemented, stop and explicitly decide whether to update the oracle rather than carefully cloning a known-bad old behavior.

## 13. 절대 하지 말 것

- `master` 수정/병합
- `calculator/` production 수정
- global 60Hz loop
- 캐릭터명 기반 runtime special-case
- unsupported mechanic silent zero
- 테스트 편의를 위한 unrelated blocker 개방
- Moris 불일치를 tolerance 확대로 숨기기
- proof 없이 family 전체를 열기
- sparse engine에 불필요한 high-frequency bookkeeping 추가
- 한 checkpoint가 닫히기 전에 다음 coverage slice를 섞기
