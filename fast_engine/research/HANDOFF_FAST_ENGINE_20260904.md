# Fast Engine 작업 인계 — 2026-09-04

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

현재 핵심 runtime commit:

- `46af96866b9462ec22455b9c9f5121cfa3b35bdd` — `fix: support last-bullet damage delivery`
- `0f522925b2cac86ab74329a9ce4d02347f739abe` — `fix: align Fast timing with Moris outer ticks [timing-apply]`

그 전 generic ranking fixes:

- `10e3954ae864e2139ae6a32879393504a071b6e0` — adjacent-target regression correction
- `8a12ee8c8ef8c0f7d05525f0f1c71176306c167e` — static adjacent-target scope correction
- `a5b247b08c30dbf89348a0b263d502d0f06cf5f9` — runtime adjacent-target correction
- `28428dd601ae3ce64a219188afd894b1242a5eb4` — self-state conditional passive sync
- `7695efcff56bd59a5e352a1462f4bda9e61cefed` — self-stack conditional passive sync

재개 시 우선 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260904.md`
2. `fast_engine/research/COVERAGE_FRONTIER_CHECKPOINT_20260904.md`
3. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`
4. `fast_engine/research/HANDOFF_FAST_ENGINE_20260903.md`
5. `fast_engine/research/SELF_STATE_PASSIVE_RANKING_CHECKPOINT_20260903.md`
6. `fast_engine/research/RANKING_CORE_CROSSOVER_CHECKPOINT_20260903.md`

---

## 1. 현재 phase

certified pair의 static ranking hard case는 닫았고, 2026-09-04 후반부터 coverage expansion을 다시 시작했다.

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

## 2. timing checkpoint 핵심 결론

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

최종 permanent timing runtime에서 monkey patch 없이 실행한 결과:

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

## 6. 채택하지 않은 timing 실험

다음은 정식 구현하지 않았다.

- mathematical `ceil(frame)` snap
- rapid full-frame projection
- observed-frame rapid timestamp projection
- `WEAPON_BOUNDARY` phase 강제 변경
- same-frame actor ordering을 위한 broad scheduler reshuffle

이들은 either ranking 개선이 없거나 오히려 악화됐다.

rapid path는 현재 그대로 둔다.

---

## 7. coverage frontier 재개 결과

21 coverage gaps를 mechanic 기준으로 다시 분류했다.

첫 조사에서 다음 broad 후보는 보류했다.

### Crown `heal_received`

`로얄 에타이어 4`는 heal chronology가 comparison-critical이므로 HP/heal event chronology를 열기 전에는 fail closed 유지.

### Little Mermaid `squad_ammo_consume`

real `스쿼드1` 180초에서:

- Moris squad ammo consume 34,587
- Fast physical shots 34,476
- 일부 500-shot crossing이 약 +0.6~0.7초 어긋남

team-global threshold가 current cadence approximation을 증폭하므로 아직 인증하지 않는다.

### broad `bonus_damage`

하나의 mechanic이 아니었다. Privaty last-bullet, Isabel pending B3, Cinderella stack-count, Asuka state-end/enemy-stack으로 분리된다.

### reload/max-ammo broad enable

Fast live runtime은 이미 있으나 public blockers의 상당수가 unsafe recipient의 weapon-change/control에서 파생된다. safety를 우회하지 않는다.

세부 자료는 `COVERAGE_FRONTIER_CHECKPOINT_20260904.md` 참조.

---

## 8. 첫 coverage 확장 — `last_bullet` damage delivery

Privaty `LD 어설트 2/3`에서 작은 generic gap을 확인했다.

Fast에는 이미 static/dynamic post-shot last-bullet boundary가 있었고 damage sink safe event key만 빠져 있었다.

정식 변경:

- `46af96866b9462ec22455b9c9f5121cfa3b35bdd` — `_SAFE_EVENT_KEYS`에 `last_bullet` 1줄 추가
- `4a3d6f1378f482d41d6bcc8676150509a91d2474` — real Privaty named-state gating regression

Moris parity probe, burst 없음 35초:

- LD2 activation 6 vs 6
- LD3 0 vs 0
- LD2 damage relative error 약 `-0.00006991%`

named-state probe:

- `타겟 지정` active at t=3.1 → LD3 fires
- duration expiry after t=13.0 → t=13.1 last-bullet에서 LD3 추가 발동 없음

focused last-bullet regression 8/8 success.

public blocker scan 후:

- source24 / unique23 / certified2 / gaps21 유지
- Privaty LD2/LD3 blockers: 0

영향 팀 4개:

- `스쿼드2`
- `레이드_라피앨리스`
- `레이드_아니스서머메이든`
- `레이드_트리나홍련`

다른 cadence/weapon/control blockers가 남아 아직 새 membership이 certified되지는 않았다.

---

## 9. 다음 단일 checkpoint

다음 mechanic을 단순 stat 빈도로 고르지 않는다.

이미 보류 근거가 있는 축은 건너뛴다.

- Crown heal chronology
- Little Mermaid squad-ammo chronology
- broad weapon-change
- unsafe recipient를 무시한 reload/max-ammo broad enable

다음 작업:

1. 남은 repeated damage-delivery blockers를 trigger/target/condition shape로 묶는다.
2. 같은 root cause를 공유하고 HP chronology/weapon replacement를 새로 요구하지 않는 작은 generic slice를 찾는다.
3. real effect shape probe → Moris parity → 최소 구현 → focused regression 순서를 유지한다.
4. 한 번에 하나의 mechanic만 확장한다.
5. certified membership이 실제 증가하면 standardized public audit + ranking validation을 즉시 다시 실행한다.

**optimizer production integration은 아직 하지 않는다.**

---

## 10. 고정 설계 원칙

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

## 11. cleanup 목표 상태

조사용 temporary workflow는 checkpoint 종료 전에 제거한다.

최종 `.github/workflows`에는 반드시:

- `ci.yml`
- `pages.yml`

만 남겨야 한다.

최종 normal CI 성공 여부를 확인한 뒤 checkpoint를 닫는다.
