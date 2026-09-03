# Fast Engine 작업 인계 — 2026-09-04

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

현재 핵심 runtime commit:

- `0f522925b2cac86ab74329a9ce4d02347f739abe` — `fix: align Fast timing with Moris outer ticks [timing-apply]`

그 전 generic ranking fixes:

- `10e3954ae864e2139ae6a32879393504a071b6e0` — adjacent-target regression correction
- `8a12ee8c8ef8c0f7d05525f0f1c71176306c167e` — static adjacent-target scope correction
- `a5b247b08c30dbf89348a0b263d502d0f06cf5f9` — runtime adjacent-target correction
- `28428dd601ae3ce64a219188afd894b1242a5eb4` — self-state conditional passive sync
- `7695efcff56bd59a5e352a1462f4bda9e61cefed` — self-stack conditional passive sync

재개 시 우선 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260904.md`
2. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`
3. `fast_engine/research/HANDOFF_FAST_ENGINE_20260903.md`
4. `fast_engine/research/SELF_STATE_PASSIVE_RANKING_CHECKPOINT_20260903.md`
5. `fast_engine/research/RANKING_CORE_CROSSOVER_CHECKPOINT_20260903.md`

---

## 1. 현재 phase

Fast coverage 확장은 아직 적극 재개하지 않는다.

현재까지는 ranking validation phase를 유지했고, 이번 checkpoint에서 certified pair의 static hard-case inversion을 해결했다.

Fast-certified real public memberships:

- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

표준 public source accounting:

- source cases: 24 non-`지그_*` five-person cases
- exact ordered-membership dedupe 후 ranking candidates: 23
- certified memberships: 2
- coverage gaps: 21

24→23은 coverage 변화가 아니라 duplicate ordered membership 제거다.

---

## 2. 이번 checkpoint의 핵심 결론

이전 DEF/core near-tie ranking inversion의 주요 원인은 result-fitting이 아니라 Moris/Fast 사이의 generic timing semantics 차이였다.

정식 Fast runtime에 다음을 반영했다.

1. Moris repeated-add outer-frame timestamp observer
2. burst ready check의 `-1e-9` epsilon contract
3. finite effect의 true-expiry semantics
4. dynamic charge weapon-change 진입 시 existing magazine inheritance
5. inherited magazine 소진 후 next outer tick refill edge
6. max-ammo/reload-only 변화가 in-flight charge를 restart하지 않는 semantics

중요:

- global 1/60 combat loop 없음
- rapid/MG frame projection 없음
- character-name hack 없음
- fitted coefficient 없음
- Moris `calculator/` semantics 변경 없음

세부 근거는 `TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md` 참조.

---

## 3. 정식 ranking stress 결과

공통:

- duration 180s
- first burst 3.0s
- expected RNG
- parts / immunity chronology / element-window chronology 없음
- pair: Miranda/Mihara vs Red Hood/Quency

최종 permanent runtime에서 monkey patch 없이 실행한 결과:

- core grid: `6/6` order agreement
- DEF grid: `11/11` order agreement
- enemy-code grid: `5/5` order agreement

가장 중요한 near-tie:

`DEF=55,000 / code=작열 / core_px=10`

- Moris margin: `+0.10477149%`
- Fast margin: `+0.07771104%`
- order: agree

`DEF=60,000 / code=작열 / core_px=10`

- Moris margin: `-0.45248086%`
- Fast margin: `-0.48107045%`
- order: agree

즉 crossover 위치와 slope도 매우 가깝게 맞는다.

stress workflow run:

- `33770526797` — success

---

## 4. absolute error 상태

대표 `DEF=60k / 작열 / core_px=10`에서:

- Miranda/Mihara Fast team error: `+0.01781335%`
- Red Hood/Quency Fast team error: `+0.04654626%`

이전 RHQ +1~2% 수준의 bias가 사실상 대부분 제거됐다.

core 0처럼 damage composition이 크게 달라지는 지점에서는 RHQ absolute error가 약 +1.26%까지 남지만 ranking direction은 유지된다.

따라서 현재 issue는 더 이상 certified pair의 near-tie ranking inversion이 아니다.

---

## 5. adjacent-target correction도 유지

이번 timing 조사 중 별개 generic bug였던 `allies_adjacent:N` semantics도 이미 정식 수정되어 있다.

Moris semantics:

- caster 포함
- immediate left
- immediate right
- `N`은 adjacent neighbors에만 적용

예: actor index 3, N=2 → `(3,2,4)`.

Rouge `소드 코인` self buff 누락을 설명했던 문제다.

이 수정은 timing patch와 별개이며 되돌리지 않는다.

---

## 6. 채택하지 않은 실험

다음은 정식 구현하지 않았다.

- mathematical `ceil(frame)` snap
- rapid full-frame projection
- observed-frame rapid timestamp projection
- `WEAPON_BOUNDARY` phase 강제 변경
- same-frame actor ordering을 위한 broad scheduler reshuffle

이들은 either ranking 개선이 없거나 오히려 악화됐다.

rapid path는 현재 그대로 둔다.

---

## 7. regression 상태

정식 runtime commit 전 focused regression 통과:

- `fast_engine.tests.test_damage_moris_frame_timing`
- `fast_engine.tests.test_dynamic_weapon_change`
- `fast_engine.tests.test_damage_dynamic_charge_scoring`
- `fast_engine.tests.test_burst_machine`
- `py_compile`
- `git diff --check`

추가된 regression은 repeated-add timing, burst epsilon, true expiry, DEF55 near-tie order를 고정한다.

---

## 8. 다음 단일 checkpoint

이번 certified pair의 static ranking hard case는 닫는다.

다음에는 새 timing micro-fix를 더 찾지 않는다.

우선 선택지는 둘 중 하나다.

### A. ranking sample 확대

이미 Fast-certified 가능한 다른 real membership을 찾거나, 기존 public universe에서 coverage gap 하나를 generic하게 해소해 comparable certified sample을 늘린다.

### B. coverage 재개 판단

현재 certified pair의 core/DEF/code static axes가 안정됐으므로 coverage 확장을 다시 시작할지 판단한다.

권장 순서:

1. 21 coverage gaps를 mechanic family 기준으로 다시 분류
2. 여러 public teams를 동시에 열 수 있는 generic mechanic을 우선
3. 새 mechanic 구현 전 ranking-critical 여부와 fail-closed contract 확인
4. 한 번에 하나의 mechanic family만 확장
5. coverage 증가 뒤 standardized public audit + ranking validation 재실행

**optimizer production integration은 아직 하지 않는다.**

---

## 9. 고정 설계 원칙

- Fast는 broad scorer이지 Moris 2.0이 아니다.
- unsupported comparison-critical mechanic은 fail closed.
- character-name hack 금지.
- result-fitting coefficient 금지.
- global 1/60 combat loop 금지.
- state-relevant하지 않은 global per-shot/per-pellet scheduling 금지.
- Fast parity를 위해 Moris `calculator/` semantics를 변경하지 않는다.
- static enemy scope 유지.
- engine은 candidate generation을 결정하지 않는다.
- unsupported coverage를 numeric score로 위장하지 않는다.

---

## 10. cleanup 목표 상태

조사용 파일은 제거했다.

제거 대상:

- `.github/workflows/tmp-ranking-static-hardcase.yml`
- `fast_engine/research/tmp_apply_moris_timing.py`

최종 확인 시 `.github/workflows`에는 반드시:

- `ci.yml`
- `pages.yml`

만 남아야 한다.

최종 normal CI 성공 여부를 확인한 뒤 이 checkpoint를 닫는다.
