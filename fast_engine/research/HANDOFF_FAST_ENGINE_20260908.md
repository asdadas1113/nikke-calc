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
2. `fast_engine/research/ADA_TARGETED_EFFECT_INTERVAL_PERIODIC_GRID_CHECKPOINT_20260908.md`
3. `fast_engine/research/RAPID_TO_SINGLE_CHARGE_WEAPON_CHANGE_CHECKPOINT_20260907.md`
4. `fast_engine/research/NAYUTA_RAPID_TO_CHARGE_SKILL_WEAPON_CHANGE_WIP_CHECKPOINT_20260907.md`
5. `fast_engine/research/PRIVATY_CHARGE_LIVE_MAX_AMMO_SAFETY_CHECKPOINT_20260907.md`
6. `fast_engine/research/MORAN_RAPID_WEAPON_CHANGE_LIFECYCLE_CHECKPOINT_20260907.md`
7. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`

## 1. Protected baseline

`master` 기준 SHA:

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

Ada promotion gate 직전과 semantic promotion 시점 모두 이 SHA를 다시 검증했다.

이 SHA가 계속 불변이어야 한다.

## 2. Latest completed semantic checkpoint

최신 production semantic commit:

- `2063efc88d4947225b44746bab29364afc9a09cf` — `Fast: support targeted dynamic periodic intervals`

완료 checkpoint:

- Ada `섬광 수류탄 투척 발동 시간 조건` targeted `effect_interval`
- same-actor periodic damage의 mid-cooldown interval rescale
- Moris outer-loop phase order에 맞춘 sparse next-frame interval observation

상세 기록:

- `fast_engine/research/ADA_TARGETED_EFFECT_INTERVAL_PERIODIC_GRID_CHECKPOINT_20260908.md`

## 3. Exact Ada semantics now owned

Public source case:

- `레이드_헬름아쿠아스노우`

Producer:

- Ada `섬광 수류탄 투척 발동 시간 조건`
- self buff
- `effect_interval = -1.0`
- finite `10s`
- one stack
- one `burst_cast` trigger
- exact `target_effect = "섬광 수류탄 투척"`

Target:

- Ada `섬광 수류탄 투척`
- enemy damage
- `armor_break_damage = 420`
- fixed base `every:2s`
- `during_full_burst` activation condition
- already score-supported by `SimpleDamageScoreSink`

Owned lifecycle:

- active modifier changes effective interval `2.0s → 1.0s`
- remaining in-progress cooldown is rescaled proportionally
- modifier expiry rescales the remaining cooldown back toward the base interval
- raw deadlines are mapped onto the existing repeated-add Moris frame lattice
- stale sparse reservations are generation-invalidated

No arbitrary interval family was opened.

## 4. Important Moris phase-order lesson

Moris `BuffManager.tick()` evaluates `every:Ns` cooldowns before the burst controller on each outer-loop frame.

Therefore a `burst_cast` interval modifier created at frame `t` is not visible to that periodic cooldown system until the next repeated-add 60 Hz frame.

Public oracle around Ada's second burst:

- Ada burst cast / modifier activation: `21.533333333333392`
- first accelerated grenade: `21.783333333333378`
- subsequent accelerated grenades: `22.783333...`, `23.783333...`, ...

The first staged Fast implementation observed the modifier immediately and fired at `21.766666...`, exactly one frame early.

Do not solve such differences with tolerance widening. The fix is semantic phase ordering.

Fast now uses one sparse `PERIODIC_SYNC` boundary on `moris_next_tick()` for the owned actor/shape rather than a global 60 Hz loop.

## 5. Sparse performance boundary

An intermediate implementation scheduled deferred periodic sync after every burst-machine event and moved the structural event count from `539` to `577`.

This was rejected as unnecessarily dense even though tests were semantically green.

Final implementation schedules deferred sync only for a `burst_cast` from an actor that owns a supported targeted interval relationship.

Final promotion performance:

- median `199.36ms`
- events `539`

This is an important design constraint for future cadence work: new semantic boundaries should remain conditional sparse events.

## 6. Production implementation surface

Semantic diff from the temp promotion parent contains exactly 9 `fast_engine/` files:

- `fast_engine/engine/burst_runtime.py`
- `fast_engine/engine/dispatcher.py`
- `fast_engine/engine/dynamic_periodic.py` — new
- `fast_engine/engine/effects.py`
- `fast_engine/engine/scheduler.py`
- `fast_engine/engine/score.py`
- `fast_engine/tests/test_damage_effect_interval_periodic_grid.py` — new
- `fast_engine/tests/test_damage_periodic_enemy_received.py`
- `fast_engine/tests/test_damage_periodic_self_crit.py`

Stats:

- 480 insertions
- 23 deletions

`calculator/` diff: none.

## 7. Promotion validation

Semantic promotion workflow:

- run `34150287961`
- job `101830953514`
- result `success`

Results:

- Ada focused oracle regression `3/3`
- neighboring periodic/runtime/performance `17/17`
- full Fast discovery `364/364`
- performance median `199.36ms`, events `539`
- protected master assertion passed immediately before promotion
- no `calculator/` diff

The public Fast/Moris Ada grenade activation list matches frame-for-frame.

## 8. Current public frontier

Standard `fast_engine/research/public_blocker_frontier.py` view after Ada:

- source cases `24`
- certified source cases `6`
- source-case gaps `18`

Blocker family counts:

- cadence `55`
- control `5`
- normal_delivery `45`
- normal_state `18`
- skill_damage `25`
- skill_state_delivery `49`
- weapon_change `2`
- periodic_grid `0`

Ada A/B:

- `periodic_grid: 1 → 0`
- no other family count changed directly
- certified stays `6`

Critical near-frontier row:

`레이드_헬름아쿠아스노우`

- blockers: exactly `normal_state:미란다:웨이크업! 4:rank_target_timing`
- unsupported: empty

This roster is now one blocker from certification.

## 9. Cleanup state

All temporary Ada probe/apply/fix/workflow assets were removed after promotion.

Final `.github` root must contain only:

- `scripts/`
- `workflows/`

Final `.github/workflows` must contain only:

- `ci.yml`
- `pages.yml`

This hygiene was verified after cleanup and before writing this handoff.

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
- targeted dynamic periodic interval rescaling

Do not jump to raw coverage expansion or optimizer integration.

## 11. Next checkpoint selection

Highest-leverage immediate investigation is now Miranda `웨이크업! 4:rank_target_timing` in `레이드_헬름아쿠아스노우`, because it is the roster's only blocker.

However **do not remove it simply to obtain a seventh certified source case.** Treat it as a new semantic checkpoint.

Required order:

1. query current branch HEAD and verify `master`
2. inspect the exact compiled Miranda effect, trigger, target mode, and all ATK-ranking dependencies
3. run Moris oracle to determine whether target ranking is static in this public roster or changes over time
4. determine whether the correct fix is:
   - a narrow static ranking proof, or
   - an actual dynamic rank-target timing runtime
5. prove ownership without character-name runtime branches
6. focused regression with Moris target/timing trace
7. full Fast discovery
8. public frontier A/B
9. semantic promotion only after all gates are green
10. cleanup temp assets and run canonical CI on the final clean documentation HEAD

If Miranda is not safely narrow after inspection, choose another single restoration checkpoint instead; do not force certification.

## 12. Final canonical CI requirement

This handoff is written after semantic promotion and cleanup. The final documentation HEAD still needs its canonical `ci.yml` run checked before declaring the overall checkpoint closed.

Canonical gate must include green results for:

- doclint
- Fast shards
- Fast complete discovery
- calculator
- optimizer
- bridge
- site
- golden snapshot 29/29

The final user-facing completion message should record the exact clean HEAD, CI run/job IDs, and counts.

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
