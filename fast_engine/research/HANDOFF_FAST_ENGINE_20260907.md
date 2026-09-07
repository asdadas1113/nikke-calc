# Fast Engine 작업 인계 — 2026-09-07

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
- Moris 불일치를 tolerance 확대로 숨기지 않음

작업 시작 시 branch HEAD와 `master`를 다시 조회한다. 이 문서의 SHA는 semantic 기준점을 기록하는 것이며 현재 HEAD 자체를 뜻하지 않을 수 있다.

먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260907.md`
2. `fast_engine/research/RAPID_TO_SINGLE_CHARGE_WEAPON_CHANGE_CHECKPOINT_20260907.md`
3. `fast_engine/research/NAYUTA_RAPID_TO_CHARGE_SKILL_WEAPON_CHANGE_WIP_CHECKPOINT_20260907.md`
4. `fast_engine/research/PRIVATY_CHARGE_LIVE_MAX_AMMO_SAFETY_CHECKPOINT_20260907.md`
5. `fast_engine/research/MORAN_RAPID_WEAPON_CHANGE_LIFECYCLE_CHECKPOINT_20260907.md`
6. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`

## 1. Latest completed semantic checkpoint

최신 production semantic commit:

- `b492c4d0c3d45cfe3eea5ca9b80cbd755340e13a` — `Fast: support rapid-to-single-charge weapon changes`

완료 checkpoint:

- generic rapid-base → one ordinary SR full-charge shot weapon-change lifecycle
- public owned shapes:
  - `스쿼드2` 츠바이 `과충전 공식`
  - `레이드_헬름아쿠아스노우` 스노우 화이트 `세븐스 드워프 : I`

상세 기록:

- `fast_engine/research/RAPID_TO_SINGLE_CHARGE_WEAPON_CHANGE_CHECKPOINT_20260907.md`

직전 semantic checkpoint:

- `38244aeda6313f7c978af9658dc9f2eae1aa6dc0` — Nayuta `기억 연소` rapid→charge skill weapon-change lifecycle

`master` 기준 SHA:

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

이 SHA가 계속 불변이어야 한다.

## 2. Latest restored semantics

Exact common compiled shape:

- base weapon `auto`, non-clip
- self `burst_cast` weapon change
- changed weapon `SR`
- changed max ammo `1`
- no finite time duration
- `duration_bullets=1`
- positive damage/charge/full-charge fields
- no `skill_damage=True`
- same-cast self `pierce_enabled`, also `duration_bullets=1`

The changed SR shot is an ordinary full-charge weapon attack, not a skill-weapon shot.

Moris first-session oracle:

### Zwei

- mode enter `3.05`
- changed SR shot / mode consumption `4.266667`
- base SG resume next frame `4.283333`

### Snow White

- mode enter `3.35`
- changed SR shot / mode consumption `8.35`
- base AR resume next frame `8.366667`

## 3. Sparse resume and frame-lattice semantics

Moris does not restore pre-entry ammo or a live full magazine after this one-shot mode.

After the changed SR round is consumed:

- base rapid state gets exactly `1` round
- base firing resumes on the next repeated-add Moris frame
- that round then reaches zero and ordinary reload semantics continue

Fast implements this with sparse re-anchoring only:

- `resume_after_single_charge()`
- `moris_next_tick()` for base resume
- no global frame loop

A real staged Snow White divergence was also fixed:

- naive decimal `3.35 + 5.0` was observed as `8.366667`
- Moris releases at `8.35`
- the single-charge mode entry is now anchored through the existing repeated-add frame lattice with epsilon only for this exact family

No global charge timing tolerance was widened.

## 4. Bullet lifetime and score ownership

Changed-shot ordering:

1. changed SR full-charge attack is scored
2. already-owned reducible hit-count crossings may dispatch
3. `duration_bullets=1` is consumed
4. weapon-change and one-shot pierce states are removed
5. base rapid resumes next frame

Score certification requires:

- exactly one weapon change affecting the actor
- exact single-charge shape
- exact one-shot self pierce companion
- no named-state reference graph around the mode
- no executable raw `full_charge_hit` / `on_attack` consumers introduced by this slice

Still-unowned class-changing families explicitly remain fail-closed:

- `레이드_네온벨벳` — Velvet `깔끔한 마무리`
- `레이드_작열짬` — Modernia `섬멸 모드`

## 5. Privaty transitive dependency

`스쿼드2`의 Privaty `EX 매거진 2:reload_speed_pct`는 새 mechanic 구현이 아니다.

기존 generic dynamic-reload path는 이미 있었지만 Zwei recipient cadence가 unsafe여서 score proof가 fail-closed였다. 이번 exact Zwei cadence ownership으로 그 recipient dependency가 풀렸다.

따라서 `스쿼드2`에서만:

- `cadence:프리바티:EX 매거진 2:reload_speed_pct` 제거

반면:

- `cadence:프리바티:EX 매거진 3:max_ammo_pct`는 계속 fail-closed
- 다른 public Privaty pair의 unresolved recipient dependencies도 계속 fail-closed

이 변화는 regression으로 고정했다.

## 6. Promotion validation

Semantic promotion gate:

- run `34135447642`
- job `101785202117`
- result `success`

Validation:

- new single-charge focused `5/5`
- neighboring grouped suite `35/35`
- complete Fast discovery `361/361`, `65.368s`
- focused performance median `198.38ms`, events `539`
- complete-run performance median `201.28ms`, events `539`
- `master` baseline rechecked before promotion
- no `calculator/` diff
- staged semantic diff restricted to `fast_engine/`

Semantic commit diff:

- 12 `fast_engine/` files
- 420 insertions / 40 deletions
- new `test_damage_single_charge_weapon_change.py`
- stale frontier expectations repaired only where the newly owned exact scope made them obsolete

Full discovery initially found five stale regressions. They all encoded the old frontier; no runtime-semantic failure was hidden. Updated tests preserve explicit fail-closed witnesses for unrelated families.

## 7. Current public frontier

표준 `fast_engine/research/public_blocker_frontier.py` raw source-case view:

- source cases `24`
- certified source cases `6`
- source-case gaps `18`

blocker family counts:

- cadence `55`
- control `5`
- normal_delivery `45`
- normal_state `18`
- periodic_grid `1`
- skill_damage `25`
- skill_state_delivery `49`
- weapon_change `2`

Checkpoint A/B:

- cadence `56 → 55`
- normal_delivery `47 → 45`
- weapon_change `4 → 2`
- certified remains `6`

Direct removed blockers:

- `weapon_change:츠바이:과충전 공식`
- `normal_delivery:츠바이:과충전 공식 2:pierce_enabled`
- `weapon_change:스노우 화이트:세븐스 드워프 : I`
- `normal_delivery:스노우 화이트:세븐스 드워프 : I 2:pierce_enabled`

Transitive removal:

- `cadence:프리바티:EX 매거진 2:reload_speed_pct` in `스쿼드2`

`레이드_헬름아쿠아스노우`의 현재 blocker는 정확히 두 개다.

- `periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval`
- `normal_state:미란다:웨이크업! 4:rank_target_timing`

집계 주의:

- scanner raw view: `24 / 6 / 18`
- membership de-duplication view는 23 unique memberships를 사용하며 cadence count도 raw view와 다를 수 있다.

## 8. Cleanup state

이번 checkpoint 임시 자산은 모두 제거했다.

- `.github/workflows/tmp-next-frontier.yml`
- `.github/tmp_single_charge_apply.py`
- `.github/tmp_single_charge_fix1.py`
- `.github/tmp_single_charge_regression_fix.py`

최종 `.github/workflows`에는 다음 두 개만 남아야 한다.

- `ci.yml`
- `pages.yml`

재개 시 다시 확인한다.

## 9. Current phase

계속 **false-supported safety closure → semantics restoration** 단계다.

현재까지 주요 restoration 축:

- finite self rapid weapon-change lifecycle
- sparse Moris rapid nominal-fire deadline observation
- rapid effective weapon view isolation
- Little Mermaid enemy replacement + global squad ammo crossing
- Crown shared lifetime/heal_received
- charge live max-ammo source quantization/clamp safety repair
- Nayuta rapid→charge skill weapon-change lifecycle
- rapid→single-charge ordinary weapon-change + one-shot bullet lifetime

이번 checkpoint는 닫혔다. 다음에는 raw coverage 숫자를 보고 바로 가장 큰 family를 고르지 말고, current blockers 중 false-supported risk와 semantic leverage가 높은 **다음 하나의** checkpoint만 선택한다.

현재 눈에 띄는 near-frontier 예시는 `레이드_헬름아쿠아스노우`의 남은 두 blocker지만, 실제 선택은 Moris ownership 범위를 다시 조사한 뒤 결정한다.

## 10. 다음 작업자가 할 순서

1. branch HEAD 조회
2. `master`가 `fb2fd9157aa14499daf6b9f185beb685d4393f90`인지 확인
3. 이 handoff와 completed single-charge checkpoint 읽기
4. `.github/workflows`가 `ci.yml`, `pages.yml`뿐인지 확인
5. 최신 clean-HEAD canonical CI가 green인지 확인
6. 필요 시 current public frontier 재실행
7. 남은 blockers 중 false-supported risk와 semantic leverage 기준으로 다음 **하나의** checkpoint 선택
8. Moris oracle로 의미론을 먼저 고정
9. narrow ownership proof + focused regression
10. full Fast discovery + frontier A/B + canonical CI 후에만 완료 처리

## 11. 절대 하지 말 것

- `master` 수정/병합
- `calculator/` production 수정
- global 60Hz loop
- 캐릭터명 기반 runtime special-case
- unsupported mechanic silent zero
- 테스트 편의를 위한 unrelated blocker 개방
- Moris 불일치를 tolerance 확대로 숨기기
- proof 없이 family 전체를 열기
- 한 checkpoint가 닫히기 전에 다음 coverage slice를 섞기
