# Fast Engine 작업 인계 — 2026-09-09

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

작업 시작 시 branch HEAD와 `master`를 다시 조회한다. 이 문서의 semantic SHA와 현재 branch HEAD를 혼동하지 않는다.

먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260909.md`
2. `fast_engine/research/VELVET_FINITE_CHARGE_TO_RAPID_WEAPON_CHANGE_CHECKPOINT_20260909.md`
3. `fast_engine/research/MIRANDA_LAZY_RANK_BULLET_LIFETIME_CHECKPOINT_20260908.md`
4. `fast_engine/research/ADA_TARGETED_EFFECT_INTERVAL_PERIODIC_GRID_CHECKPOINT_20260908.md`
5. `fast_engine/research/RAPID_TO_SINGLE_CHARGE_WEAPON_CHANGE_CHECKPOINT_20260907.md`
6. `fast_engine/research/NAYUTA_RAPID_TO_CHARGE_SKILL_WEAPON_CHANGE_WIP_CHECKPOINT_20260907.md`
7. `fast_engine/research/MORAN_RAPID_WEAPON_CHANGE_LIFECYCLE_CHECKPOINT_20260907.md`
8. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`

## 1. Protected baseline

Fixed Moris/master baseline:

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

Velvet investigation, staging, promotion, and cleanup all rechecked against this SHA. It remains unchanged.

## 2. Latest completed semantic checkpoint

Latest production semantic commit:

- `822944c3de7719434ef97e49225c81d517908b6b` — `Fast: support finite charge-to-rapid weapon changes`

Completed slice:

- generic finite self charge→ordinary infinite-MG weapon mode
- base charge state suspension while temporary rapid runtime owns the actor
- effective temporary MG warmup/cadence
- whole-combat actor `hit_count` seed and residual handoff
- live-full base magazine restoration
- raw expiry → Moris outer-frame resume timing

Detailed record:

- `fast_engine/research/VELVET_FINITE_CHARGE_TO_RAPID_WEAPON_CHANGE_CHECKPOINT_20260909.md`

## 3. Exact Velvet semantics now owned

Public source case:

- `레이드_네온벨벳`

Effect:

- Velvet `깔끔한 마무리`
- base fire mode `charge` / SR
- temporary `weapon_type = MG`
- `duration = 10.0`
- `damage_coeff = 7.0`
- `max_ammo = -1`
- self target
- one `burst_cast` event trigger

Moris oracle:

- first 10s MG session: `451` shots
- first `hit_count:50` crossing: `6.466666…s`
- nine reduced 50-hit crossings per session
- first base SR resume: `13.200000000000236`
- second raw expiry observed at: `25.74999999999982`
- base magazine resumes live-full and the immediate resumed shot consumes one round (`14 → 13` in the oracle trace)

The actor's `hit_count` is whole-combat. It is not reset by weapon-mode entry or exit.

## 4. Runtime architecture

The implementation does not add a global frame loop.

Key pieces:

- `TriggerDispatcher.event_count()` exposes read-only actor-scoped trigger count
- exact charge→rapid shape/runtime proof is wired into executable admission and activation
- base charge runtime can be marked as suspended during the owned temporary rapid mode
- rapid runtime can register dormant mode-only rapid actors whose base weapon is charge
- MG cadence reads the effective temporary weapon's rate/warmup fields
- mode entry seeds rapid count from dispatcher state
- mode exit flushes residual count before base SR resume
- base resume uses existing Moris observed-frame semantics

No character name appears in runtime routing.

## 5. Ownership/fail-closed boundary

The score proof remains deliberately narrow.

It rejects shapes with wider dependencies such as:

- overlapping weapon changes
- consumers of the weapon-change named state/state-end
- unsupported shot-event consumers
- non-reducible `hit_count` semantics
- wider squad-body-hit dependency
- reload/control contracts outside this slice

`모더니아:섬멸 모드` remains fail-closed and is retained as the neighboring class-changing witness.

Do not generalize from Velvet to arbitrary SR→MG or arbitrary class-changing modes without a new semantic checkpoint.

## 6. Semantic diff

Promotion parent → `822944c3...`:

- 12 files, all under `fast_engine/`
- 568 insertions
- 32 deletions
- no `calculator/` production diff

Production files:

- `fast_engine/engine/burst_runtime.py`
- `fast_engine/engine/dispatcher.py`
- `fast_engine/engine/dynamic_rapid.py`
- `fast_engine/engine/dynamic_reload.py`
- `fast_engine/engine/dynamic_weapon.py`
- `fast_engine/engine/score.py`
- `fast_engine/engine/weapon.py`

Focused/new or stale-frontier regression files:

- `fast_engine/tests/test_damage_charge_to_rapid_weapon_change.py` — new
- `fast_engine/tests/test_damage_full_charge_hit_charge_speed.py`
- `fast_engine/tests/test_damage_moran_weapon_change_lifecycle.py`
- `fast_engine/tests/test_damage_stat_applied_charge_speed.py`
- `fast_engine/tests/test_dynamic_weapon_change.py`

## 7. Validation

Final staging gate:

- run `34263340013`
- job `102186484455`
- result `success`

Promotion gate:

- run `34263609821`
- job `102187383687`
- result `success`

Validated before semantic promotion:

- focused Velvet lifecycle `6/6`
- neighboring weapon-change regression `21/21`
- full Fast discovery `374/374`
- structural event count `539`
- staging performance median `180.92ms`
- `RAPI_CHAIN_30S` relative error `0.0003858566668650809`
- public frontier scan success
- no `calculator/` diff

Two full-suite failures seen during staging were stale shared aggregate assertions (`cadence 52 → 51`) after the new ownership surface. They were updated only after the new focused/neighbor semantics were already green. Do not reinterpret that aggregate assertion change as an independently completed public cadence mechanic without a separate proof.

## 8. Current public frontier

After Velvet:

- source cases `24`
- certified `7`
- gaps `17`

Certified/gap totals are unchanged by this checkpoint. Velvet removes one real blocker but its team is not yet certified.

`레이드_네온벨벳` now has exactly three raw blockers:

- `normal_delivery:네온 : 비전 아이:초화력:atk_dmg_pct`
- `skill_damage:리틀 머메이드:거품 난사:sequential_damage:10`
- `skill_state_delivery:네온 : 비전 아이:초화력:atk_dmg_pct`

Conceptually this is two mechanisms:

- `damage_delivery:네온 : 비전 아이:초화력:atk_dmg_pct`
- `skill_damage:리틀 머메이드:거품 난사:sequential_damage:10`

The Velvet weapon-change blocker is gone.

Another nearest non-certified source case is `스쿼드1`, also at 3 raw / 2 conceptual blockers, and it shares the Little Mermaid sequential-damage blocker.

## 9. Cleanup state

Temporary Velvet helper/workflow were removed after semantic promotion:

- `.github/tmp_next_frontier_probe.py`
- `.github/workflows/tmp-next-frontier-probe.yml`

Verified post-clean `.github/` root:

- `scripts/`
- `workflows/`

Required final workflow directory:

- `ci.yml`
- `pages.yml`

No temporary workflow may survive the handoff.

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
- Velvet finite charge→rapid MG lifecycle

Do not jump to optimizer integration or broad unsupported-family coverage.

## 11. Next single checkpoint candidate

First candidate to **investigate**, not blindly implement:

- Little Mermaid `거품 난사`
- blocker: `skill_damage:리틀 머메이드:거품 난사:sequential_damage:10`

Why it is high leverage:

- appears in blocker pressure with count `4`
- shared by both nearest non-certified source cases:
  - `레이드_네온벨벳`
  - `스쿼드1`

Required investigation order:

1. recheck branch HEAD and fixed `master`
2. inspect exact compiled `거품 난사` effect(s), trigger count, target and all parameters
3. identify every public consumer/dependency and whether `sequential_damage:10` is one mechanic or several shapes
4. run Moris oracle traces for activation timing, hit ordering, repeated damage spacing/count and interaction with burst/state boundaries
5. determine whether a narrow generic sparse sequential-damage runtime is sufficient
6. explicitly preserve any wider shapes as fail-closed
7. focused Moris parity regression
8. neighboring regression
9. full Fast discovery
10. public frontier A/B
11. semantic promotion only after all green
12. delete every temporary helper/workflow
13. update checkpoint/handoff
14. canonical CI on the exact final clean HEAD

If sequential damage requires hidden per-frame ordering or a wider unresolved damage scheduler, do not force it merely to certify `레이드_네온벨벳`/`스쿼드1`. Leave it blocked and choose another single semantics-restoration slice.

## 12. Moris baseline policy

Continue using fixed master SHA `fb2fd915...` as the oracle during this restoration phase.

Do not chase unrelated newer Moris changes. Perform latest-Moris migration/audit as a separate later phase.

Exception: if a newer Moris change is confirmed to fix the exact mechanic being implemented, stop and explicitly decide whether the oracle baseline should move rather than cloning known-bad behavior.

## 13. 절대 하지 말 것

- `master` 수정/병합
- `calculator/` production 수정
- global 60Hz loop
- 캐릭터명 기반 runtime special-case
- unsupported mechanic silent zero
- 테스트 편의를 위한 unrelated blocker 개방
- Moris 불일치를 tolerance 확대로 숨기기
- proof 없이 family 전체 열기
- sparse engine에 불필요한 high-frequency bookkeeping 추가
- 한 checkpoint가 닫히기 전에 다음 coverage slice 섞기
