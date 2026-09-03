# Fast Engine 작업 인계 — 2026-09-03

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

확인한 `master` SHA:

`fb2fd9157aa14499daf6b9f185beb685d4393f90`

이번 인계 직전 cleanup HEAD:

`f10c9730784969a1f4bb49e3a18171677bd9d8b1`

이번 세션에서 실제 runtime 코드가 마지막으로 바뀐 핵심 commit:

`7695efcff56bd59a5e352a1462f4bda9e61cefed` — `fix: sync self-stack conditional passives`

인계 전에 조사용 `tmp-*` workflow 및 helper를 모두 제거했다. `.github/workflows`에는 다시 다음 둘만 남는다.

- `ci.yml`
- `pages.yml`

이 문서는 2026-09-02 장기 인계의 **증분 최신판**이다. 새 세션에서는 먼저 다음을 읽는다.

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260903.md`
2. `fast_engine/research/HANDOFF_FAST_ENGINE_20260902.md` — 장기 아키텍처/금지사항
3. `fast_engine/research/PROJECTILE_NAMED_STACK_CHECKPOINT_20260903.md`
4. `fast_engine/research/RANKING_CORE_CROSSOVER_CHECKPOINT_20260903.md`
5. `fast_engine/research/RL_PROJECTILE_NORMAL_CHECKPOINT_20260903.md`

---

## 1. 현재 phase

Fast coverage 확장은 현재 **중단 상태**다.

Rapi : Red Hood projectile/named-stack generic slice 이후 실 public 팀이 2개 certified가 되었기 때문에, 사용자와 합의한 규칙대로 ranking validation phase로 전환했다.

현재 certified real public teams:

- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

표준 public contract는 계속 다음과 같다.

- 고정 24개 non-`지그_*` five-person source case
- candidate generation bypass
- duration 180s
- first burst 3.0s
- expected RNG
- 기본 enemy DEF 31,784
- 기본 core/parts/immune/element window 없음

`public_ranking_probe.py`가 동일 membership을 deduplicate하여 23 unique membership으로 출력할 수 있으나, 프로젝트의 표준 source universe 자체는 **24 source case**다. 이 accounting 문제를 engine result와 혼동하지 않는다.

---

## 2. ranking에서 이미 확인된 실제 실패

`RANKING_CORE_CROSSOVER_CHECKPOINT_20260903.md`에서 지원 범위 안의 static scenario로 두 certified 팀을 근접시키자 Fast가 실제로 순서를 틀렸다.

고정 조건:

- duration 180s
- first burst 3.0s
- expected RNG
- enemy DEF 60,000
- enemy code `작열`
- only `core_px` changes

Moris는 `core_px=0~10` 사이에서 crossover하지만 Fast는 `30~40` 사이에서 crossover한다.

특히 `core_px=10`:

- Moris: Red Hood/Quency가 약 +0.45% 우세
- Fast: Miranda/Mihara가 약 +9.36% 우세

따라서 현재 문제는 coverage가 아니라 **이미 supported라고 인증한 의미론의 ranking bias**다.

---

## 3. 이번 세션에서 해결된 ranking-semantic 항목

### 3.1 RL normal projectile-explosion routing

`RL_PROJECTILE_NORMAL_CHECKPOINT_20260903.md`

Moris는 ordinary RL normal attack을 `is_projectile_explosion=True`로 계산한다. Fast는 `projectile_explosion_dmg_pct` 상태값 자체는 읽고 있었지만 normal attack HitSpec에 RL projectile-explosion shape가 없어 factor가 빠졌다.

수정 후:

- `NormalAttackSpec.is_projectile_explosion`
- compiled/base weapon `weapon_type == "RL"`에서 true
- `HitSpec.is_projectile_explosion`로 전달

민트 첫 full-charge hit가 Moris와 사실상 일치하도록 수정됐다.

공식 full CI 기준 implementation HEAD:

`ece369165b31a233519bc08e2afe06a6c2fa569c`

CI run:

`33691333035` — success

해당 시점 standard public default:

- certified 2
- Miranda/Mihara rel error 약 `-0.68184%`
- Red Hood/Quency rel error 약 `-5.90561%`

그러나 core crossover의 `core_px=10/20/30` misorder는 남았다.

---

## 4. 이번 세션에서 새로 반영한 generic fix

### self-stack conditional permanent passive synchronization

commit:

`7695efcff56bd59a5e352a1462f4bda9e61cefed`

변경 파일:

- `fast_engine/engine/dispatcher.py`
- `fast_engine/engine/effects.py`
- `fast_engine/tests/test_conditional_passive_self_stack.py`

문제:

Moris는 `passive` permanent buff를 battle start에 등록해두고 `self_stack_above` 류 조건이 현재 참인지에 따라 기여를 gate한다. Fast는 이전에 조건이 false인 시점에는 effect를 materialize하지 않았고, 이후 named self stack이 생겨도 해당 permanent conditional passive를 다시 평가하지 않았다.

새 narrow generic contract:

- effect type `buff`
- permanent (`duration None/-1`)
- one-stack passive
- static/runtime-supported target
- trigger exactly `passive`
- 조건은 `SELF_STACK_AT_LEAST`만

이 shape만 stack-provider activation / bullet lifetime removal / expiry edge에서 sparse하게 재평가한다.

false→true는 새 trigger count나 named-event broadcast가 아니라 Moris의 condition gating transition으로 취급한다.

`EffectRegistry.deactivate_group(...)`도 이 목적에 맞게 추가했다.

**주의:** arbitrary conditional passive 전체를 연 것이 아니다. 이 narrow shape 밖은 계속 fail closed로 본다.

이번 수정 뒤 Quency 진단을 재실행했고, normal-attack 쪽의 큰 누락 일부는 줄었지만 전체 ranking bias는 아직 해결되지 않았다.

이 commit 이후 full official CI는 아직 인계 시점 기준으로 별도 완료 결과를 확정 기록하지 않았다. 다음 세션은 branch CI 상태를 먼저 확인하고, 실패가 있으면 이 commit부터 검증한다.

---

## 5. 현재 미완료 핵심 진단 — Quency

중단 직전 `레이드_레드후드퀀시`를 30초 Fast/Moris로 **평타와 스킬 대미지를 분해**했다.

가장 중요한 결과:

- 퀀시 normal attack 오차는 대략 **-6% 수준**
- 퀀시 Burst damage `위대한 도둑 3`은 Fast가 Moris보다 **정확히 -40.28% 낮음**
- 같은 비율의 부족이 30초/180초에서 반복되어, 단발성 shot timing 흔들림보다 **동일 burst 시각의 자기 버프와 burst damage 적용 순서**가 가장 강한 후보다.

즉 지금은 Quency 전체 평타 모델을 먼저 넓힐 단계가 아니다. `위대한 도둑 3` 한 계열에서 반복되는 고정 비율 누락을 먼저 잡는 것이 ranking inversion 해결에 가장 직접적이다.

### 현재 가설

Moris에서는 같은 burst activation 안에서 `위대한 도둑` 계열의 self buff/state가 먼저 활성화되고 `위대한 도둑 3` damage가 그 버프를 본 뒤 계산되는데, Fast의 burst/effect delivery에서는 damage가 그 동일시각 새 상태를 보지 못하는 ordering 가능성이 높다.

**아직 확정된 원인은 아니다. 수정도 하지 않았다.**

### 재개 시 첫 조사 순서

1. Quency의 `위대한 도둑` 관련 compiled effects를 모두 출력한다.
2. Moris에서 burst_cast 한 번의 effect dispatch 순서를 확인한다.
3. Fast `TriggerDispatcher` / burst-effect delivery에서 같은 timestamp ordering을 비교한다.
4. `위대한 도둑 3` damage term을 Moris/Fast로 한 번만 isolated score하여 어떤 factor가 정확히 40.28% 빠지는지 확인한다.
5. character-name hack 없이 generic same-trigger/same-time ordering bug로 증명될 때만 수정한다.
6. focused regression을 추가한다.
7. full Fast regression + official CI.
8. 같은 core-crossover grid를 다시 돌려 `core_px=10/20/30` order가 개선되는지 본다.

### 피해야 할 것

- `퀀시` 이름으로 special-case
- 단순히 damage coefficient에 40.28%를 더하는 보정
- coverage를 다시 넓히는 것
- candidate generation/optimizer algorithm으로 넘어가는 것
- boss chronology를 추가하는 것

현재 문제는 이미 supported된 ranking semantics 검증이다.

---

## 6. 이 시점의 다음 성공 조건

가장 가까운 성공 조건은 certified 수 증가가 아니다. 이미 ranking phase에 들어왔다.

다음 checkpoint는 다음 중 하나여야 한다.

### A. generic ordering bug가 확인될 경우

- generic fix
- focused regression
- full test/CI
- Quency 30s decomposition 재확인
- core crossover 재실행
- 결과 checkpoint 문서화

### B. ordering이 원인이 아닐 경우

- `위대한 도둑 3`의 정확히 -40.28% 차이를 factor 단위로 더 분해
- 다음 supported damage semantic 원인을 특정
- 아직 코드 변경 없이 diagnostic checkpoint로 남겨도 됨

어느 경우든 **ranking inversion의 원인을 이해하기 전에는 coverage expansion이나 optimizer integration을 재개하지 않는다.**

---

## 7. 장기 금지사항/설계 원칙

2026-09-02 handoff의 원칙을 그대로 유지한다.

- Fast는 broad scorer이지 Moris 2.0이 아니다.
- comparison-critical unsupported는 fail closed.
- character-name hack 금지.
- global 1/60 loop 금지.
- state-relevant하지 않은 global per-shot/per-pellet scheduling 금지.
- Fast parity를 위해 Moris `calculator/` semantics를 바꾸지 않는다.
- static enemy scope 유지.
- Crown `heal_received`는 HP/heal/lifesteal/overheal chronology가 필요하므로 계속 보류.
- engine은 pairing을 결정하지 않는다. Mint+Frika 같은 조합 탐색은 향후 candidate-generation/optimizer layer 문제다.
- 사용자는 special combination inventory를 더 확보하기 전 optimizer algorithm phase로 들어가지 않기로 했다.

---

## 8. clean-up 상태

인계 직전 제거 완료:

- `.github/workflows/tmp-branch-safety.yml`
- `.github/workflows/tmp-dummy.yml`
- `.github/workflows/tmp-public-audit-check.yml`
- `.github/workflows/tmp-quency-fast-breakdown.yml`
- `.github/workflows/tmp-quency-normal-diagnosis.yml`
- `.github/workflows/tmp-quency-normal-vs-fast.yml`
- `.github/workflows/tmp-stopgap.txt`
- `fast_engine/research/tmp_apply_conditional_passive_patch.py`

따라서 다음 세션은 조사 workflow 복구부터 시작하지 말고, 필요할 때만 새 임시 probe를 만들고 끝나면 다시 제거한다.
