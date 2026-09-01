# Fast Engine 작업 인계 — 2026-09-02

## 0. 새 세션에서 가장 먼저 할 일

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

마지막으로 확인한 `master` SHA:

`fb2fd9157aa14499daf6b9f185beb685d4393f90`

이번 인계의 **최종 코드 검증 기준점**은 다음 clean HEAD이다.

`e031dc1c375c2593f81f44c3a6270a8b08b3bf57`

이 SHA는 임시 patch/frontier workflow와 조사용 스크립트를 모두 제거한 뒤의 코드 상태다.

전체 CI:

- workflow run: `33565697370`
- run attempt: `2`
- verify job: `100052062063`
- conclusion: **success**

검증된 항목:

- doclint
- Fast burst machine
- Fast capabilities/state
- Fast compiled triggers
- Fast core semantics
- Fast damage suite
- Fast dispatch/burst runtime
- Fast dynamic weapon signals
- Fast greenfield core
- Fast periodic runtime
- Fast target snapshot
- Fast weapon suite
- Fast structural performance
- Moris/calculator unit tests
- optimizer unit tests
- bridge smoke tests
- browser/site tests
- golden snapshot 29/29

첫 CI attempt에서는 기존 사이트 UI 테스트 385개 중 `blocks a forged growth stage 1.5...` 한 건이 `simulateCalls == 0` 대신 1을 보면서 실패했다. Fast/engine/optimizer/bridge는 그 attempt에서도 모두 통과했다. 코드 수정 없이 같은 verify job을 재실행했고 attempt 2에서 브라우저 385개와 golden snapshot까지 전부 통과했다. 따라서 이번 Fast 작업으로 인한 재현 가능한 회귀로 보지 않는다.

**주의:** 이 인계 문서 자체의 commit은 위 코드 checkpoint 뒤에 생긴다. 새 세션에서는 branch tip을 다시 확인하되, handoff-only commit 때문에 `e031...`의 이미 검증된 코드 내용을 다시 의심해서 되돌리지 않는다.

---

## 1. 프로젝트 목적

Fast Engine은 Moris를 대체하는 두 번째 정밀 전투 계산기가 아니다.

목적은 대량의 후보 스쿼드를 Moris보다 훨씬 싸게 비교하여, 비싼 Moris authoritative re-score에 넘길 후보를 넓고 안전하게 추리는 것이다.

의도한 production pipeline:

```text
account / roster / builds
        ↓
structural candidate generation
        ↓
Fast broad scoring
        ↓
wide / protected shortlist
        ↓
Moris authoritative re-score
        ↓
exact non-overlap 5-team allocation
        ↓
optional refinement
```

우선순위:

1. throughput
2. Moris Top-N recall inside Fast Top-K
3. catastrophic false-negative 방지
4. stable pairwise ordering
5. meaningful synergy 보존
6. absolute damage accuracy

작은 공통 절대오차보다 특정 무기/기믹/조합을 체계적으로 과대·과소평가하는 편향이 더 위험하다.

---

## 2. 사용자가 확정한 장기 범위

앞으로 Fast Engine에 큰 보스 시뮬레이션 기능을 넣을 계획은 없다.

### user-facing static enemy 범위

주로 다음과 같은 정적 입력만 선택 가능하게 한다.

- 전투시간
- 적 방어력
- 적 속성/코드
- 코어 비율 또는 코어 조건
- 필요하면 코어 크기(`core_px`)처럼 정적인 정확도 입력

### 의도적으로 넣지 않을 범위

- 보스 이동 chronology
- 점프
- 무적 시간축
- 강제 엄폐
- 보스 공격 chronology
- 피격 패턴
- 엄폐 파괴
- 스턴
- 부위 노출/파괴 시간축
- 복잡한 면역 window

즉 Fast의 외생 시간축은 최대한 단순하게 유지한다.

사용자가 예상하는 가장 큰 후속 기능은 **힐러 강제 배정/필수 힐러 제약** 정도이며, 이는 Fast 전투 runtime이 아니라 candidate generation / allocation 알고리즘 축으로 처리하는 것이 원칙이다.

Fast를 “Moris가 할 수 있는 것은 전부 할 수 있는 엔진”으로 키우지 않는다.

---

## 3. 핵심 아키텍처 계약

정본 문서:

- `docs/FAST_ENGINE_ARCHITECTURE.md`
- `docs/OPTIMIZER_PROJECT_STATE.md`
- `fast_engine/research/LESSONS.md`

입력/호환 경계:

```text
profile / account / overrides
        ↓
context.spec.build_squad(...)      # Moris-owned
        ↓
Moris character dicts
        ↓
Fast compiler / adapter boundary
        ↓
immutable Fast IR
        ↓
independent Fast runtime
```

Fast는 Moris의 account/build assembly와 parsed skill/weapon data를 재사용하지만, 정상 Fast evaluation에서 `calculator.timeline.simulate()`를 호출하지 않는다.

### 절대 지킬 것

- global 1/60 loop 금지
- state 변화가 없는데 global per-shot/per-pellet scheduling 금지
- character-name hack 금지
- Fast에 맞추기 위해 `calculator/` Moris 의미론을 바꾸지 않기
- comparison-critical 미지원 상태는 fail closed
- blocked/unsupported는 coverage gap이지 ranking false negative가 아님
- 후보생성 문제와 Fast coverage/ranking 문제를 혼동하지 않기

검증 시 항상 다음 층을 분리한다.

```text
source universe
→ candidate generation
→ Fast coverage
→ Fast ranking
→ Moris shortlist
→ final allocation
```

Fast 자체 parity/coverage를 볼 때는 optimizer candidate generation을 우회하고 고정 실스쿼드 + 공통 scenario를 사용한다.

---

## 4. 현재 중요한 시간축/무기 의미론

### equal-time 대략적 phase

현재 Fast에서 비교-critical한 동일시각 순서는 다음을 기준으로 생각한다.

```text
ordinary state expiry
→ timed STATE_END_NOTIFY
→ fixed periodic
→ burst transitions/effects
→ weapon / damage boundaries
```

새로운 기믹을 열 때 이 순서를 무심코 바꾸지 않는다.

### charge event invariant

- Moris raw `full_charge` = **pre-shot**
- `full_charge_hit` = **post-shot**
- 절대 alias하지 않는다.

Dynamic charge score callback은 physical shot/ammo state가 먼저 진행된 뒤 실행되며, post-shot trigger delivery보다 앞선다.

### bullet lifetime ordering

지원되는 dynamic actor에서는 consuming shot이 버프를 본 상태로 피해 계산한 후:

1. post-shot hit/count signal
2. bullet lifetime consume
3. 필요 시 `last_bullet`

순서를 유지한다.

### reload speed

일반 non-clip reload는 reload 시작 시 speed를 snapshot한다.
이미 시작한 reload는 중간에 reload-speed buff가 바뀌어도 duration이 바뀌지 않는다.
`post_reload_delay`는 reload completion 시점의 speed를 다시 읽는 기존 계약을 유지한다.

### ammo refill

- `ammo_charge_pct`: `round(effective_max_ammo * pct / 100)`
- `ammo_charge_flat`: `int(value)`
- max ammo에서 cap
- 이미 진행 중인 reload는 일반 ammo refill만으로 취소되지 않음
- `reload.cancel_on_full` control은 별도 기믹이며 현재 일반화하지 않음

### force reload

Moris 의미:

- 이미 reloading이면 no-op
- 아니면 현재 ammo = 0
- 그 시각에 ordinary reload 즉시 시작

### MG warmup speed

MG physical shot 이후 live `mg_warmup_speed_pct`를 읽고:

```python
increment = max(0.0, 1.0 + mg_warmup_speed_pct / 100.0)
warmup = min(warmup + increment, warmup_bullets)
```

이미 이전 shot이 예약해 둔 interval을 retroactive하게 줄이지 않는다.

---

## 5. 최근 완료된 주요 runtime slice

### 5.1 dynamic rapid reload / own_full_burst cover / live bullet lifetime

주요 문서:

`fast_engine/research/LIVE_RELOAD_RAPID_COVER_CHECKPOINT_20260902.md`

지원된 핵심:

- non-clip auto/MG live reload-speed
- reducible `hit_count` / `pellet_hit`
- `cover.policy == own_full_burst`
- partial-mag cover entry manual reload
- reload may finish under cover
- no catch-up shots after cover
- exact cover-end shot 가능
- dynamic rapid `duration_bullets`

첫 공개 certified team:

`미란다 / 브리드 : 사일런트 트랙 / 헬름 / 루주 / 미하라 : 본딩 체인`

### 5.2 charge live bullet lifetime + safe `cover_during_delay`

주요 문서:

`fast_engine/research/CHARGE_BULLET_LIFETIME_CHECKPOINT_20260902.md`

구현 commit:

`88ab8b5d01e9accf81c4259e67ed16be2ee80129`

핵심:

- dynamic charge actor가 실제 charge shot으로 `duration_bullets`를 소비
- rapid/charge dynamic bullet-lifetime registration은 additive
- charge `cover_during_delay`는 무조건 거부하지 않고, 가능한 positive `reload_speed_pct` upper bound가 100% 미만임을 증명할 때만 허용

공개 `스쿼드1` Helm은 Crown + Cube 최대 reload-speed 보수합이 74.04%라 100% 특수 branch가 도달 불가로 인증됐다.

### 5.3 dynamic ammo charge

주요 문서:

`fast_engine/research/AMMO_CHARGE_CHECKPOINT_20260902.md`

구현 commit:

`230c2acb8d240dc6c6111722c755e9f048ea7c7a`

핵심:

- `ammo_charge_pct`
- `ammo_charge_flat`
- refill 중 stale weapon boundary 무효화/replan
- reload_wait에서 양의 ammo가 생기면 firing 복귀
- active reloading은 그대로 유지
- charge post_fire_reload에서 ammo가 생기면 post_fire로 복구

여전히 fail-closed:

- battle_start ammo charge
- live max-ammo mutation과 섞이는 unsafe recipient
- unsupported control/clip
- named `event:<effect name>` consumer chain

따라서 “ammo charge 전부 지원”이라고 말하면 안 된다.

### 5.4 MG warmup / timed state-end / force reload bundle

주요 문서:

`fast_engine/research/MG_WARMUP_STATE_END_CHECKPOINT_20260902.md`

기본 구현 commit:

`008efafacc54ae93faa97057343c47745031f38c`

state-end source safety hardening:

`f1640611e0981f502405d648ee1f27d05725e954`

Asuka : WILLE `섬멸 태세` 종료 시 같은 이벤트에 다음 cadence 변화가 함께 있으므로 원자적으로 처리했다.

- `긴급 수복 2`: `mg_warmup_speed_pct`
- `긴급 수복 3`: `force_reload`
- `긴급 수복 5`: `reload_speed_pct`, `duration_bullets: 1`

`force_reload`가 원래 `_CADENCE_OR_SHAPE_STATS`에 없어 blocker audit에서 빠져 있던 것도 수정했다.

### timed state-end bridge의 매우 중요한 제한

임의의 `event:state_end:*`를 허용한 것이 아니다.

score gate는 source state가 다음 조건을 모두 만족하는지 증명한다.

- same actor owner
- effect type `buff`
- self-target
- finite ordinary time duration
- `duration_bullets` 없음
- runtime executable

다음 source는 여전히 fail closed:

- explicit named-buff removal
- bullet-lifetime-driven end
- group/multi-target lifetime aggregation
- weapon-change ending
- 기타 source semantics가 증명되지 않은 state end

이 gate를 느슨하게 만들지 않는다.

---

## 6. 현재 public 24-team frontier

표준 audit:

- `context.snapshot.SQUADS`에서 24개 실제 five-person membership 사용
- candidate generation bypass
- duration 180s
- first burst 3.0s
- expected RNG
- enemy DEF 31,784
- core/parts/immune/element window 없음

최근 safety-gate 재감사:

- run `33565485221`
- job `100047586948`
- audit commit `d4fe96f27b882cc4843fc67eb3722d88bdb181a1`
- teams: 24
- certified: **1**
- coverage gaps: **23**

### nearest unresolved

`레이드_델타`

- raw blockers: **2**
- conceptual: **1**
- 남은 유일 conceptual blocker: Crown `로얄 에타이어 4:atk_dmg_pct`

`스쿼드1`

- raw blockers: **2**
- conceptual: **1**
- 남은 유일 conceptual blocker: Crown `로얄 에타이어 4:atk_dmg_pct`

두 raw row는 normal delivery + skill-state delivery 표현 차이이며 실제 conceptual mechanism은 하나다.

### `레이드_아스카루드밀라`

- raw: **7**
- conceptual: **4**

남은 conceptual:

1. Naga `우정의 가드 2:core_dmg_pct`
2. Naga `친구들과 함께라면! 3:atk_caster_based_pct`
3. Crown `로얄 에타이어 4:atk_dmg_pct`
4. Ludmilla : Winter Owner `여왕의 시선 3:ammo_charge_flat`

Asuka MG/state-end cadence blockers는 제거된 상태가 맞다.

---

## 7. Crown `heal_received`는 계속 보류

Crown `로얄 에타이어 4`:

- `atk_dmg_pct +20.99%`
- duration 7s
- target all allies
- trigger `event:heal_received`

이건 단순 trigger whitelist 문제가 아니다.

공개 팀에는 실제 도달 가능한 heal/lifesteal source가 있기 때문에 정확히 열려면 최소한 다음 축을 다뤄야 한다.

- HP
- direct heal
- lifesteal
- 실제 회복 적용 여부
- `heal_received` producer
- 경우에 따라 overheal/HP cap 등

사용자가 현재 Fast 범위를 크게 확장할 생각이 없으므로, 이 경로는 계속 후순위로 둔다.

coverage 숫자를 늘리기 위해 `heal_received`를 patternless/unreachable로 취급하거나 whitelist하지 않는다.

---

## 8. 다음 독립 coverage 후보

`heal_received`를 보류할 경우 가장 자연스러운 다음 조사 대상은:

**Ludmilla : Winter Owner `여왕의 시선 3:ammo_charge_flat`**

ammo-charge primitive 자체는 이미 구현됐지만 해당 실전 effect는 recipient/trigger/cadence 안전계약 때문에 아직 blocker다.

다음 세션에서 coverage 작업을 재개한다면 먼저:

1. effect의 exact trigger/condition/recipient
2. `_is_dynamic_ammo_charge_score_supported`가 어느 gate에서 false인지
3. core-count / max-ammo / reload / control 중 무엇이 실제 원인인지

를 분해한다.

캐릭터 이름 예외를 넣지 않고 mechanic-level contract가 작게 확장 가능한 경우에만 구현한다.

---

## 9. 현재 성능/정확도 해석

최근 standardized public timing probe:

- run `33561207208`
- job `100033858795`
- source commit `075f557cc89f3818ce35461d4f472c3ac36d2b71`

결과:

- Moris certified-team score: `2,826,025,741`
- Fast score: `2,806,756,837.590`
- relative error: **-0.68184%**
- practical Fast 180s score call: **약 0.226 s**

주의:

- 이 0.226s는 실제 public certified squad 한 팀의 wall measurement다.
- 24팀 중 23팀은 scoring 전에 coverage block되므로 24-team Fast runtime으로 해석하면 안 된다.
- structural CI fixture는 훨씬 단순해서 수십 ms 수준이며 직접 비교하지 않는다.

현재 certified public team이 1개뿐이므로:

- single-score Fast-vs-Moris error는 관측 가능
- pairwise ordering accuracy는 **관측 불가**
- ranking recall은 **아직 측정 불가**

두 번째 이상 real team이 certified되는 즉시 ranking pair를 측정해야 한다. coverage를 무작정 늘린 뒤 나중에 ranking을 보지 않는다.

---

## 10. Moris 의존성과 유지보수에 대한 현재 판단

Fast는 독립 계산식 모델이 아니라 **Moris 데이터/의미론을 공유하는 고속 압축 runtime**이다.

장점:

- 캐릭터/스킬/build 데이터를 별도로 이중 관리하지 않음
- Moris를 최종 authority로 유지 가능
- 새 캐릭터가 기존 primitive 조합이면 Fast 코드 변경 없이 따라올 수 있음
- fail-closed로 silent bias 위험을 낮춤

대가:

- Moris event ordering / weapon semantics / state lifetime이 바뀌면 Fast compatibility 확인이 필요
- certification gate가 점점 복잡해질 수 있음

이 복잡성은 현재 목적상 받아들이는 trade-off다.

### 다음에 하면 좋은 유지보수 작업 — 아직 미구현

대규모 refactor가 아니라 **Moris ↔ Fast compatibility contract tests를 얇게 분리**하는 것을 권장한다.

예시 계약:

- `full_charge` pre-shot
- `full_charge_hit` post-shot
- state expiry / state_end / weapon equal-time ordering
- reload-speed snapshot timing
- active reload 중 `force_reload` no-op
- ammo charge round/cap
- bullet lifetime consuming-shot ordering
- MG warmup increment/cooling

목적은 Moris가 바뀌었을 때 “Fast 전체가 이상하다”가 아니라 어떤 의미론 계약이 깨졌는지 바로 알게 하는 것이다.

**이 작업은 아직 하지 않았다.** 새 세션에서 구조정리를 하기로 한다면 첫 maintenance task로 적합하다.

Fast IR 자체는 가능하면 안정적으로 유지하고, Moris schema 변경은 compiler/adapter boundary에서 흡수한다.

---

## 11. 현재 코드 복잡도에서 특히 조심할 곳

가장 조심할 영역은 `score.py`의 certification logic이다.

runtime primitive가 구현되어 있다는 사실만으로 effect를 인증하면 안 된다.

항상 다음을 같이 증명해야 한다.

- trigger producer가 실제 존재하는가
- condition을 runtime이 정확히 판정하는가
- target set을 정확히 알 수 있는가
- source state가 실제로 Fast에서 생성되는가
- lifetime/refresh가 맞는가
- recipient weapon이 dynamic ownership에 들어가는가
- 다른 cadence mutation이 future timeline을 stale하게 만들지 않는가

최근 state-end source fail-open 가능성이 실제로 이 계층에서 발견됐고 gate로 닫았다.

coverage를 높이기 위해 인증 규칙을 느슨하게 만들지 않는다.

---

## 12. 다음 세션 권장 순서

### A. 유지보수 정리를 먼저 할 경우

1. 이 handoff 읽기
2. branch tip / master SHA 확인
3. `docs/FAST_ENGINE_ARCHITECTURE.md`, `fast_engine/research/LESSONS.md` 읽기
4. Moris↔Fast compatibility contract test bundle을 작은 범위로 분리
5. runtime 의미 변경 없이 CI green 확인
6. frontier로 복귀

### B. 바로 coverage로 갈 경우

1. Ludmilla Winter Owner `여왕의 시선 3:ammo_charge_flat` blocker 원인 분해
2. 작은 generic contract로 안전하게 해결 가능하면 구현
3. public frontier 재실행
4. certified team이 2개 이상이면 즉시 pairwise/ranking validation
5. Crown `heal_received`는 계속 deferred

### C. optimizer 기능으로 갈 경우

힐러 강제 배정은 candidate-generation/allocation policy로 구현한다.
Fast combat runtime에 healer-specific branch를 넣지 않는다.

---

## 13. 하지 말 것

- `master` 수정/병합
- Fast parity를 위해 Moris `calculator/`를 임의 수정
- character-name whitelist
- unsupported effect를 0으로 치고 certified score 반환
- raw blocker 수 감소를 ranking 향상이라고 표현
- 1개 certified team 결과로 전체 ranking accuracy 선언
- candidate-generation miss를 Fast ranking false negative라고 부르기
- 보스 chronology를 Fast에 계속 추가해서 Moris 2호기로 만들기
- Crown `heal_received`를 coverage 압박 때문에 억지로 열기
- `event:state_end:*`를 source 검증 없이 일반 허용
- `ammo_charge_*`가 구현됐다는 이유로 모든 ammo effect를 지원했다고 가정

---

## 14. 현재 research/checkpoint 문서

우선순위 높은 문서:

- `fast_engine/research/HANDOFF_FAST_ENGINE_20260902.md` — 이 문서
- `docs/FAST_ENGINE_ARCHITECTURE.md`
- `docs/OPTIMIZER_PROJECT_STATE.md` — 일부 immediate resume 내용은 과거 checkpoint이므로 이 handoff가 더 최신
- `fast_engine/research/LESSONS.md`
- `fast_engine/research/LIVE_RELOAD_RAPID_COVER_CHECKPOINT_20260902.md`
- `fast_engine/research/CHARGE_BULLET_LIFETIME_CHECKPOINT_20260902.md`
- `fast_engine/research/AMMO_CHARGE_CHECKPOINT_20260902.md`
- `fast_engine/research/MG_WARMUP_STATE_END_CHECKPOINT_20260902.md`
- `fast_engine/research/PUBLIC_RANKING_AUDIT_20260901.md`
- `fast_engine/research/public_blocker_frontier.py`

`fast_engine/research/`에는 마지막 확인 기준 임시 `_apply_*`, `_fix_*`, `_inspect_*` patch helper나 one-shot frontier workflow를 남기지 않았다.

---

## 15. 새 채팅용 최소 전달 프롬프트

다음 문구로 시작하면 된다.

> GitHub `asdadas1113/nikke-calc`의 `fast-engine-phase2-20260901` 브랜치에서 `fast_engine/research/HANDOFF_FAST_ENGINE_20260902.md`를 먼저 읽고 Fast Engine 작업을 이어서 진행해줘. `master`는 수정/병합하지 말고, handoff에 기록된 `e031dc1c375c2593f81f44c3a6270a8b08b3bf57` 전체 CI green checkpoint 이후 상태를 기준으로 작업해줘. Moris↔Fast compatibility contract 정리 또는 Ludmilla Winter Owner ammo blocker 원인 분해부터 진행하고, Crown `heal_received`와 보스 패턴 chronology는 보류해줘.
