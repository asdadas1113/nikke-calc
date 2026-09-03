# Fast Engine 작업 인계 — 2026-09-03

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

현재 runtime 의미론의 마지막 핵심 변경 commit:

- `28428dd601ae3ce64a219188afd894b1242a5eb4` — `fix: sync self-state conditional passives`

그 직전 ranking-semantic 핵심 변경:

- `7695efcff56bd59a5e352a1462f4bda9e61cefed` — `fix: sync self-stack conditional passives`

이번 조사 결과는 다음 문서에 영구 기록했다.

- `fast_engine/research/SELF_STATE_PASSIVE_RANKING_CHECKPOINT_20260903.md`

재개 시 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260903.md`
2. `fast_engine/research/SELF_STATE_PASSIVE_RANKING_CHECKPOINT_20260903.md`
3. `fast_engine/research/HANDOFF_FAST_ENGINE_20260902.md`
4. `fast_engine/research/RANKING_CORE_CROSSOVER_CHECKPOINT_20260903.md`
5. `fast_engine/research/RL_PROJECTILE_NORMAL_CHECKPOINT_20260903.md`

---

## 1. 현재 phase

Fast coverage 확장은 계속 **일시 중단**한다.

현재는 ranking validation phase다.

Fast-certified real public memberships는 여전히 2개다.

- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

표준 public source universe는 24개 non-`지그_*` five-person source case다. 이 중 ordered membership 하나가 중복되어 ranking analyzer에 넣을 unique membership은 23개다.

즉:

- source accounting: 24 cases
- ranking candidates after exact ordered-membership dedupe: 23

이 차이를 coverage 변화로 해석하지 않는다.

---

## 2. 이번 세션의 핵심 결론

이전 checkpoint에서 발견된 supported `core_px` ranking inversion은 **현재 해결됐다.**

원인은 하나의 core 공식이 아니었다. 두 generic conditional-passive delivery gap이 연속으로 영향을 주고 있었다.

### 2.1 Quency self-stack conditional permanent passives

`7695efc`

Moris는 permanent passive를 등록해두고 named self stack 조건으로 contribution을 gate한다. Fast는 과거 조건이 false일 때 materialize하지 않았고 이후 stack edge에서 재평가하지 않았다.

이를 `SELF_STACK_AT_LEAST` narrow generic shape에 대해 sparse edge-sync하도록 수정했다.

중요한 정정:

이전 인계에서 Quency `위대한 도둑 3`이 Fast에서 약 `-40.28%`라고 기록되어 same-timestamp burst ordering을 의심했다.

현재 runtime에서 직접 단발 비교한 결과:

- Moris: `25,711,754`
- Fast: `25,711,753.73`

즉 현재 Quency burst ordering bug는 재현되지 않는다.

과거 `-40.28%`는 `7695efc` 이전에 completed-route critical-rate / split-damage conditional passives가 빠졌을 때의 비율과 사실상 일치한다.

Quency ordering을 별도로 수정하지 않는다.

### 2.2 Frika self-state conditional permanent passive

Quency 수정 뒤에도 `core_px=10`에서 약 0.9%p 수준의 작은 pairwise inversion이 남았다.

actor decomposition 결과 Frika만 약 `-18.7%`로 크게 낮았다.

Frika의 해당 시나리오 damage는 전부 normal attack이며:

- Moris shots: 122
- Fast static shots: 123

따라서 shot count 부족이 아니었다.

Frika compiled effect에는 `self_state:퍼포먼스` 조건에서 permanent `pierce_enabled`를 켜는 passive가 있다. `퍼포먼스`가 burst로 생긴 뒤에도 Fast의 normal-attack terms는 `pierce_enabled=False`였다.

`28428dd`에서 기존 sparse conditional-passive sync 구조를 다음 narrow generic shape까지 확장했다.

- permanent one-stack buff
- static/runtime-supported target
- trigger exactly `passive`
- conditions only `SELF_STATE` or `NOT_SELF_STATE`

character-name special case는 없다.

회귀 테스트:

- 기존 Quency self-stack test 유지
- Frika `퍼포먼스 -> pierce_enabled` materialization test 추가
- targeted 2 tests 모두 통과

---

## 3. ranking inversion 재검증

고정 stress scenario:

- duration 180s
- first burst 3.0s
- expected RNG
- enemy DEF 60,000
- enemy code `작열`
- parts / immunity chronology / element-window chronology 없음
- only `core_px` changes

Margin은 `(Miranda/Mihara - Red Hood/Quency) / max(team scores)`.

| core_px | Moris margin | Fast margin | order |
|---:|---:|---:|:---:|
| 0 | +9.94% | +8.28% | agree |
| 10 | -0.45% | -2.22% | agree |
| 20 | -2.61% | -4.34% | agree |
| 30 | -7.01% | -8.64% | agree |
| 40 | -13.52% | -15.03% | agree |
| 52 | -20.54% | -21.90% | agree |

기존에 틀렸던 `core_px=10/20/30`도 모두 Moris order를 보존한다.

핵심 near-tie `core_px=10`:

Moris:

- Miranda/Mihara `3,441,496,042`
- Red Hood/Quency `3,457,138,934`
- RH/Quency 약 +0.45%

Fast:

- Miranda/Mihara `3,441,658,894.956`
- Red Hood/Quency `3,519,875,399.507`
- RH/Quency 약 +2.22%

Frika error는 수정 전 약 `-18.7%`에서 수정 후 약 `+2.6~2.8%`로 바뀌었다.

따라서 현재까지 관측된 큰 supported-core ranking inversion은 닫는다.

---

## 4. 수정 후 standardized public audit

공통 기본 contract:

- public default builds
- duration 180s
- first burst 3.0s
- expected RNG
- default static enemy
- candidate generation bypass

결과:

- source cases: 24
- unique memberships: 23
- certified: 2
- coverage gaps: 21
- certified pairwise accuracy: `1.0` (`1/1`)
- clean top-N recall: `1.0`

Certified default scores:

### 컨트롤_미란다미하라

- Moris `2,826,025,741`
- Fast `2,806,756,837.590`
- error `-0.68184%`

### 레이드_레드후드퀀시

- Moris `2,009,756,793`
- Fast `2,045,799,145.664`
- error `+1.79337%`

clean median error는 약 `+0.556%`다.

주의: `public_ranking_probe.py`를 24 source case 그대로 실행하면 현재 optimizer ranking validator가 duplicate membership을 거부한다. 이번 audit은 source count 24를 기록한 뒤 **exact ordered membership만 23개로 dedupe하여 ranking 계산**했다. 이것은 engine/candidate-generation 변경이 아니다.

향후 helper를 고친다면 이 accounting contract를 명시적으로 구현해야 한다. 급하게 optimizer validator를 느슨하게 만들지 않는다.

---

## 5. 현재 해석

현재 certified pair에서는 이전의 실제 ranking failure를 재현하지 못한다. `core_px` stress axis의 6개 tested point 모두 order가 맞는다.

하지만 이것으로 Fast ranking을 production optimizer에 연결해서는 안 된다.

이유:

1. real certified membership이 아직 2개뿐이다.
2. comparable pair가 1개뿐이다.
3. RH/Quency default absolute score는 Fast가 약 +1.8% 높다.
4. 현재 결과는 static supported scenario에 한정된다.

따라서 다음 단계는 **coverage 숫자를 늘리는 것보다 현재 certified pair를 다른 supported static stress axis에서 더 압박하는 ranking validation**이다.

---

## 6. 다음 단일 checkpoint

다음 세션의 첫 작업은 새 mechanic 구현이 아니다.

`컨트롤_미란다미하라` vs `레이드_레드후드퀀시` 두 certified 팀에 대해 supported static scenario grid를 하나 더 설계한다.

권장 우선순위:

1. `enemy DEF` 변화
2. 이미 지원되는 `enemy code` 변화
3. 필요하면 기존 `core_px`와 결합하되 작은 bounded grid로 유지

목적:

- Moris가 near-tie가 되는 추가 지점을 찾는다.
- Fast가 해당 지점의 order를 보존하는지 확인한다.
- 단순 큰-margin 12/12 같은 결과만 반복하지 않는다.
- absolute error보다 ranking-relevant response slope가 안정적인지 본다.

이 추가 hard-case에서도 안정적이면 다음 checkpoint에서 ranking validation sample 확대 또는 coverage 재개 여부를 판단한다.

**optimizer production integration은 아직 하지 않는다.**

---

## 7. 설계 원칙 / 금지사항

2026-09-02 handoff 원칙 유지:

- Fast는 broad scorer이지 Moris 2.0이 아니다.
- comparison-critical unsupported는 fail closed.
- character-name hack 금지.
- global 1/60 loop 금지.
- state-relevant하지 않은 global per-shot/per-pellet scheduling 금지.
- Fast parity를 위해 Moris `calculator/` semantics를 변경하지 않는다.
- static enemy scope 유지.
- engine은 optimizer pairing/candidate generation을 결정하지 않는다.
- unsupported coverage를 억지 numeric score로 채우지 않는다.

---

## 8. cleanup 상태

이번 세션 조사용 temporary workflow와 probe outputs는 모두 제거했다.

`.github/workflows`에는 다음 둘만 남는다.

- `ci.yml`
- `pages.yml`

`fast_engine/research`의 이번 세션 `tmp_*` 진단 산출물도 제거했다.

영구 결과는 다음 문서에 남아 있다.

- `SELF_STATE_PASSIVE_RANKING_CHECKPOINT_20260903.md`
- 이 `HANDOFF_FAST_ENGINE_20260903.md`
