# Fast Engine timing semantics ranking checkpoint — 2026-09-04

## 0. 결론

`fast-engine-phase2-20260901`의 정식 Fast runtime에 Moris와의 비교에 필요한 timing semantics를 generic하게 반영했다.

핵심 runtime commit:

- `0f522925b2cac86ab74329a9ce4d02347f739abe` — `fix: align Fast timing with Moris outer ticks [timing-apply]`

이번 수정 뒤 certified pair의 static hard-case ranking grid는 다음 전체 축에서 Moris order와 일치했다.

- core grid: `6/6`
- DEF grid: `11/11`
- enemy-code grid: `5/5`

특히 이전 near-tie inversion 지점인 `DEF=55,000 / code=작열 / core_px=10`은:

- Moris margin `+0.10477149%`
- Fast margin `+0.07771104%`

으로 같은 방향을 회복했다.

stress workflow run:

- `33770526797` — success

---

## 1. 조사에서 분리된 원인

이번 ranking drift는 단일 공식 보정 문제가 아니었다.

### 1.1 repeated-add outer-frame observer

Moris는 전역 시간을 수학적인 `frame / 60`으로 재구성하지 않고 실제로 반복 덧셈한 `t += 1/60` timestamp에서 deadline을 관찰한다.

따라서 예를 들어 charge/post-fire deadline `3.65`는 수학적으로 정확한 3.65가 아니라 repeated-add lattice에서 처음 `t >= 3.65`가 되는 시점으로 진행될 수 있다.

단순 `ceil(t / (1/60)) * (1/60)` 방식은 실험에서 ranking을 오히려 악화시켰으므로 채택하지 않았다.

정식 구현은 `fast_engine/engine/frame_lattice.py`에 cached repeated-add timestamps를 두고 필요한 boundary만 매핑한다.

**global 1/60 combat loop는 추가하지 않았다.**

### 1.2 burst deadline epsilon semantics

Moris burst ready check는 outer-frame timestamp에서 `t >= ready_at - 1e-9` 의미론을 사용한다.

Fast burst scheduler는 이를 별도 epsilon-aware observer로 반영한다.

charge/reload phase와 burst deadline은 같은 tick helper를 공유하지만 epsilon contract는 다르게 유지한다.

### 1.3 finite effect true-expiry semantics

Fast `ActiveEffect.active()`가 과거 `now < expires_at - EPS`를 사용해 실제 만료보다 조금 이르게 finite buff를 끄는 경우가 있었다.

정식 구현은:

- permanent: 기존대로 active
- finite: `now < expires_at`

으로 정리했다.

이는 buff/debuff 종류와 무관한 generic lifetime correction이다.

### 1.4 dynamic charge / temporary weapon-change semantics

조사에서 Red Hood 계열 temporary charge weapon 전환 시 Moris가:

1. 전환 순간 기존 magazine ammo를 상속하고,
2. 그 상속 ammo를 소모한 뒤,
3. 다음 outer tick에서 변경 weapon의 full magazine으로 전환

하는 edge가 확인됐다.

Fast의 기존 dynamic charge runtime은 weapon-change 진입 시 즉시 변경 weapon full ammo로 refill해 cadence와 later buff-window alignment를 바꿀 수 있었다.

정식 구현은 charge actor state에 generic pending-refill 상태를 두어 이 semantics를 반영했다.

character-name 분기는 없다.

### 1.5 max-ammo / reload-only state change

Moris는 charge 중 max-ammo 또는 reload-only modifier가 변했다고 해서 이미 진행 중인 charge를 restart하지 않는다.

Fast는 signature 변경 시 모든 charge deadline을 재계산하던 경로를 좁혀:

- charge speed/time 자체가 바뀐 경우에만 in-flight charge deadline 재계산
- max-ammo / reload-speed only 변화는 cadence plan invalidate는 하되 charge start는 유지

하도록 했다.

---

## 2. 채택하지 않은 경로

다음은 조사했으나 정식 구현하지 않았다.

- global 60fps combat loop
- mathematical exact-frame `ceil()` snap
- rapid/MG 전체 frame projection
- `WEAPON_BOUNDARY` phase를 임의로 앞당기는 same-timestamp ordering 수정
- character-name special case
- 결과에 맞춘 보정 계수

rapid observed-frame timestamp trial은 Quency 첫 10초에서 shot timestamp를 Moris형으로 바꿔도 damage가 변하지 않았고, 180초 ranking에서는 오히려 오차가 악화됐다.

따라서 rapid path는 이번 checkpoint에서 변경하지 않는다.

---

## 3. 다른 generic 수정 — adjacent target semantics

이번 timing 조사 중 별개의 generic bug도 확인되어 이미 영구 수정했다.

Moris `allies_adjacent:N`은:

- caster 포함
- left neighbor
- right neighbor
- `N`은 adjacent neighbor list에만 적용

한다.

예: 5인 squad, actor index 3, `N=2` → `(3, 2, 4)`.

Fast runtime/static scope가 caster를 빼고 있던 문제를 수정했고 regression을 추가했다.

이는 Rouge `소드 코인` 자기 적용 누락을 설명했으며 timing correction과는 별개다.

---

## 4. 정식 stress grid

공통 조건:

- duration `180s`
- first burst `3.0s`
- expected RNG
- parts / immunity chronology / element-window chronology 없음
- pair:
  - `컨트롤_미란다미하라`
  - `레이드_레드후드퀀시`

margin은 `(Miranda/Mihara - Red Hood/Quency) / max(scores)`.

### 4.1 core grid — DEF 60,000 / 작열

| core_px | Moris | Fast | order |
|---:|---:|---:|:---:|
| 0 | +9.9374% | +8.8251% | agree |
| 10 | -0.4525% | -0.4811% | agree |
| 20 | -2.6112% | -2.6414% | agree |
| 30 | -7.0051% | -7.0381% | agree |
| 40 | -13.5240% | -13.5602% | agree |
| 52 | -20.5416% | -20.5809% | agree |

`core_px=10`에서 team absolute error:

- Miranda/Mihara `+0.01781%`
- Red Hood/Quency `+0.04655%`

### 4.2 DEF grid — core_px 10 / 작열

| DEF | Moris | Fast | order |
|---:|---:|---:|:---:|
| 0 | +4.7742% | +4.7612% | agree |
| 20,000 | +3.3359% | +3.3187% | agree |
| 31,784 | +2.3644% | +2.3442% | agree |
| 40,000 | +1.6222% | +1.5998% | agree |
| 50,000 | +0.6361% | +0.6106% | agree |
| 55,000 | +0.1048% | +0.0777% | agree |
| 60,000 | -0.4525% | -0.4811% | agree |
| 65,000 | -1.0335% | -1.0636% | agree |
| 70,000 | -1.6398% | -1.6714% | agree |
| 80,000 | -2.9345% | -2.9694% | agree |
| 90,000 | -4.3522% | -4.3906% | agree |

이 grid에서 ranking crossover 위치와 response slope가 매우 가깝게 정렬됐다.

### 4.3 enemy-code grid — DEF 60,000 / core_px 10

| code | Moris | Fast | order |
|:---|---:|---:|:---:|
| 작열 | -0.4525% | -0.4811% | agree |
| 수냉 | +15.2455% | +15.2334% | agree |
| 전격 | -36.5025% | -36.5052% | agree |
| 철갑 | +10.4287% | +10.4170% | agree |
| 풍압 | +40.9042% | +40.8972% | agree |

---

## 5. regression

정식 timing patch 적용 workflow에서 다음 focused validation이 모두 통과한 뒤 runtime commit을 push했다.

- `fast_engine.tests.test_damage_moris_frame_timing`
- `fast_engine.tests.test_dynamic_weapon_change`
- `fast_engine.tests.test_damage_dynamic_charge_scoring`
- `fast_engine.tests.test_burst_machine`
- `py_compile`
- `git diff --check`

새 regression은 최소한 다음을 고정한다.

- repeated-add charge boundary
- burst epsilon boundary
- finite effect true expiry
- DEF55 near-tie에서 Moris ranking order 보존

---

## 6. 현재 해석

이번 checkpoint에서 이전 certified-pair static hard-case ranking inversion은 닫는다.

Fast와 Moris의 margin 차이는 대부분 수십 bp 이하로 줄었고, 특히 crossover 인근 DEF 55k~60k에서 방향과 기울기가 일치한다.

다만 이것은 **certified pair 1개 비교**에 대한 강한 validation이지 production optimizer integration 근거는 아니다.

현재 policy 유지:

- coverage expansion은 당장 서두르지 않는다.
- unsupported comparison-critical mechanic은 fail closed.
- optimizer production integration은 아직 하지 않는다.
- 다음 ranking checkpoint는 certified sample 확대 또는 coverage 재개 여부를 판단하는 단계다.

---

## 7. cleanup contract

이 checkpoint 이후 조사용 다음 파일은 제거한다.

- `.github/workflows/tmp-ranking-static-hardcase.yml`
- `fast_engine/research/tmp_apply_moris_timing.py`

최종 `.github/workflows`는 다시:

- `ci.yml`
- `pages.yml`

만 남겨야 한다.
