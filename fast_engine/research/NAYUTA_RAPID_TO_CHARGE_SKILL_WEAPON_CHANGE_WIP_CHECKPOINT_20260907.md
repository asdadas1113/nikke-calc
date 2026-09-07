# Nayuta `기억 연소` rapid→charge skill weapon-change WIP checkpoint — 2026-09-07

## Status

**WIP / production 미승격.**

이 문서는 다음 작업자가 현재 조사와 staged implementation을 그대로 이어가기 위한 인계용 체크포인트다.

현재 production Fast Engine의 의미론 기준선은 Nayuta 작업 시작 전 clean HEAD:

- `648749924cbbcba49dcfa19feae95307a7d8f42f`

최신 completed production semantic commit은 Privaty 조사에서 발견한 charge live max-ammo safety repair:

- `87b061d76b87e9815f0474731fa0222d4115f123`

Nayuta 관련 현재 branch commit들은 probe/helper/workflow staging뿐이며 **production Fast 파일을 아직 승격하지 않았다.**

`master`는 계속 다음 SHA를 유지해야 한다.

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

## 1. 작업 원칙

- `master` 수정/병합 금지
- `calculator/` Moris는 oracle로만 사용
- Fast Engine은 optimizer용 sparse-event ranking engine
- global 60Hz loop 금지
- 캐릭터명 기반 runtime branch 금지
- unsupported comparison-critical mechanic silent zero 금지
- 한 번에 하나의 semantic checkpoint만 완결
- 이번 checkpoint가 완전히 닫히기 전 Crown/Alice/Anis-Star 등 다음 후보로 이동하지 않음

## 2. public surface

`weapon_change:나유타:기억 연소`가 반복되는 public membership은 3개다.

1. `스쿼드2`
2. `레이드_네온벨벳`
3. `레이드_소다`

현재 public policy에서:

- `스쿼드2`: Nayuta가 B2를 사용하므로 `기억 연소` 실제 발동
- `레이드_소다`: Nayuta가 B2를 사용하므로 `기억 연소` 실제 발동
- `레이드_네온벨벳`: 현재 policy에서는 다른 B2가 사용되어 Nayuta `기억 연소` 미발동

중요: 네온벨벳을 단순 unreachable special-case로 열지 않는다. 동일 compiled graph를 generic ownership으로 안전하게 소유하거나 계속 fail-closed한다.

## 3. compiled `기억 연소` shape

확인된 핵심 shape:

- owner/target: self
- trigger: `burst_cast`
- duration: 10s finite
- base weapon: `SMG / auto`, non-clip
- changed weapon: `RL / charge`
- changed max ammo: `-1` (infinite)
- changed damage coefficient: `275.18`
- charge time: `1.8s`
- full-charge multiplier: `250%`
- weapon-change RL post-fire delay: Moris weapon-change default `0.215s`
- `skill_damage=True`

기존 Moran finite rapid→rapid weapon-change primitive와 구조적으로 다르다. Moran primitive를 넓혀서 처리하면 안 된다.

## 4. state/consumer graph

`기억 연소` 상태와 함께 소유해야 하는 full-charge 소비자는 Nayuta 자신의 두 damage effect다.

- `위선 5`: `full_charge_hit` → direct `damage 150%`
- `위선 6`: `full_charge_hit` → `bonus_damage 380.46%`

staged score proof의 목표는 다음 graph만 여는 것이다.

- finite self `burst_cast` weapon-change
- base non-clip rapid auto
- changed SR/RL infinite-mag charge
- `skill_damage=True`
- 같은 actor의 exact `full_charge_hit` direct-damage consumer 두 개
- 이 외 named-state/state-end/target-effect/scaling-ref observer 없음
- extra charge/on-attack consumer 없음

다음은 계속 fail-closed해야 한다.

- `skill_damage=False`
- finite changed magazine
- clip/control/cover-during-delay base actor
- external recipient
- extra weapon-change parameters
- extra state consumer/mutator
- unrelated rapid→charge family

## 5. Moris oracle — first session

### `스쿼드2`

첫 burst:

- B1 `3.05`
- Nayuta B2 `3.20`
- B3 `3.35`
- full burst `3.40`

`기억 연소` full-charge skill shots:

1. `5.016667`
2. `7.05`
3. `9.066667`
4. `11.083333`
5. `13.10`

mode expires at `13.20`, then base SMG fire resumes immediately at `13.20`.

### `레이드_소다`

같은 first-session timing:

- B2 cast `3.20`
- skill shots `5.016667, 7.05, 9.066667, 11.083333, 13.10`
- base SMG resume `13.20`

### expiration edge

중요 semantics:

- 10초 만료 직전 새 charge가 시작되어도 만료 뒤까지 이어서 발사하지 않는다.
- 미완성 changed-mode charge는 session end에서 취소된다.
- mode 종료 시 base rapid magazine은 과거 입장 전 탄수를 복원하지 않는다.
- **종료 시점 live full magazine**으로 base weapon을 재개한다.

실측 예:

- `스쿼드2`: `13.20`에 live full `215` 기준으로 재개
- `레이드_소다`: `13.20`에 live full `282` 기준으로 재개

## 6. Moris damage classification

`기억 연소` changed-mode shot은 ordinary normal attack이 아니라 **weapon-mode skill damage**다.

따라서:

- `is_normal_atk=False`
- `is_weapon_mode_skill=True`
- full-charge layer 적용
- core damage는 weapon-mode skill 규칙으로 적용
- ordinary normal-attack damage bonus는 적용하지 않음
- `duration_bullets` state를 이 shot이 소비하지 않음
- Moris `_charge_fire()`는 `skill_name='기억 연소'`로 기록
- post-shot `full_charge_hit`를 발생시키며 그 뒤 `위선 5/6`이 같은 timestamp에 파생

projectile-explosion 분류는 Moris 코드의 `_charge_fire()`가 `self.base_weapon_type == 'RL'`을 사용하므로 changed RL이라는 이유만으로 자동 적용하면 안 된다. Nayuta base는 SMG이므로 이 mode shot에 projectile-explosion bonus를 잘못 얹지 않는다.

## 7. staged architecture

현재 staged patch는 branch production 파일이 아니라 다음 helper가 Actions checkout에서 임시 적용한다.

- `.github/tmp_nayuta_apply.py`

현재 diagnostic script:

- `.github/tmp_nayuta_probe.py`

staged design의 방향:

1. Dispatcher에 기존 charge/rapid weapon-change family와 분리된 exact `rapid_to_charge_skill_weapon_change` shape/runtime proof 추가
2. `DynamicChargeCadenceRuntime`에 base가 charge가 아닌 actor를 위한 **dormant mode-only charge actor** 개념 추가
3. mode activation edge에서만 fresh infinite-mag charge session 시작
4. `DynamicRapidCadenceRuntime` base actor는 mode interval 동안 sparse block/suspend
5. expiration edge에서 incomplete charge 폐기
6. expiration edge에 rapid actor를 `live full magazine + now`로 re-anchor
7. changed-mode shots만 dynamic charge scheduler boundary로 materialize
8. shot score는 normal-attack path가 아니라 `HitSpec(is_normal_atk=False, is_weapon_mode_skill=True, is_full_charge=True)` 계열로 처리
9. post-shot `full_charge_hit` consumer는 기존 dispatcher/damage sink를 통해 전달

이 방향은 global frame loop나 character-name branch를 요구하지 않는다.

## 8. staged tests

helper가 생성하는 신규 test module:

- `fast_engine/tests/test_damage_nayuta_cross_mode_weapon_change.py`

의도한 coverage:

1. public 3 membership에서 exact ownership proof
2. owned public scope가 정확히 3개인지 확인
3. 첫 public session 5-shot timing + `13.20` live-full resume
4. skill-mode damage classification
5. neighboring shape negative tests
6. `skill_damage=False`, finite ammo, extra parameter, widened consumer graph fail-closed

같이 돌린 기존 regression:

- `test_damage_moran_weapon_change_lifecycle`
- `test_damage_dynamic_reload_scoring`
- `test_dynamic_weapon_signals`
- `test_dynamic_charge_max_ammo_semantics`
- `test_performance_contract`

## 9. first focused gate failure

staged run:

- workflow run `34074322492`
- focused tests: 6 Nayuta tests 중 4 fail + 1 error
- production semantic commit step는 gate 실패 때문에 실행되지 않음

동일 staged gate가 최신 diagnostic HEAD에서도 다시 fail:

- run `34074367209`
- job `101597512747`

### failure A — ownership proof가 public 3 roster 전부 거절

`_temporary_self_rapid_to_charge_skill_weapon_change_score_supported(...)`가 세 roster 모두 `False`를 반환했다.

즉 staged proof의 조건 하나 이상이 실제 compiled consumer graph보다 지나치게 좁다.

**다음 첫 작업은 기대값이나 assertion을 완화하는 것이 아니라, proof의 각 predicate를 실제 compiled shape와 항목별 비교해 정확히 어느 조건이 틀렸는지 찾는 것.**

현재 `.github/tmp_nayuta_probe.py`는 이를 위해 다음을 출력하도록 준비돼 있다.

- member weapon / burst cooldown
- effect capability disposition/blockers
- effect exact fields/parameters
- dispatcher shape result
- related weapon_change effects
- `기억 연소` reference consumers
- 모든 `full_charge_hit` / `on_attack` consumer

주의: 최신 temp workflow는 staged helper + focused regression을 실행하며 이 diagnostic script를 별도 단계로 실행하지 않았다. 재개 시 workflow를 다시 만들거나 직접 runner에서 `python -u .github/tmp_nayuta_probe.py`를 실행해 proof predicate를 먼저 고정한다.

### failure B — timing harness가 unrelated Privaty blocker에서 중단

`스쿼드2` 전체 `BurstRuntime.start()`를 이용한 timing probe가 Nayuta에 도달하기 전에 다음 기존 fail-closed guard에서 멈췄다.

- `Fast static last-bullet cadence can be invalidated by live weapon modifiers: 프리바티<-EX 매거진 2, 프리바티<-EX 매거진 3`

이것은 Nayuta runtime 실패 증거가 아니다. `스쿼드2`의 기존 Privaty all-allies cadence blocker가 test harness 전체-runtime 실행을 막은 것이다.

**Privaty blocker를 Nayuta를 위해 열지 않는다.**

Nayuta timing test를 isolated runtime/unit harness로 바꾸거나, unrelated public blocker가 개입하지 않는 방식으로 mode runtime 자체를 검증한다.

## 10. 현재 production 상태

Nayuta production files는 아직 수정되지 않았다.

Nayuta probe/staging commits chain:

- `57afa08aaea127525f50612b8023374243a520cf` — temporary Nayuta probe
- `bca6eafcf522ec2b8602cceb447bfd5c33cac752` — temporary workflow
- `a3275a17fb7c0105167e248d13b4ebd150893fa5` — source probe extension
- `1399930de5539a83f8127ccc51cbc3091800c6d7` — Moris mode trace
- `6e4dd5d1cbed943aca7781cc123dc6cf04f8d532` — Fast ownership hook inspection
- `82667ea046478600fb181f218e759f798367cf92` — staged implementation helper
- `aa89f976ba1fac0a706f6356d925043deb2bae6e` — staged semantic gate workflow
- `cd6ac874908510bf4447250136ace6d84b01f2ce` — diagnostic probe update

현재 canonical CI on `cd6ac874...`:

- run `34074367264`
- result `success`

이 success는 production Fast가 여전히 pre-Nayuta baseline이라는 사실과 일치한다. staged changes는 temp workflow checkout에만 적용된다.

## 11. 다음 재개 순서

1. branch HEAD와 `master`를 다시 확인
2. 이 문서와 `HANDOFF_FAST_ENGINE_20260907.md`를 먼저 읽기
3. `.github/tmp_nayuta_apply.py`, `.github/tmp_nayuta_probe.py` 존재 확인
4. diagnostic script를 실제 staged checkout에서 실행해 score-proof predicate mismatch를 특정
5. proof를 **필요한 만큼만** 좁게 수정
6. timing test를 Privaty와 분리된 isolated harness로 변경
7. focused Nayuta tests 전부 green
8. Moran / dynamic reload / dynamic weapon / charge-max-ammo / performance regression green
9. patched public frontier audit
10. public blockers가 의도대로만 줄었는지 확인
11. 그 뒤에만 staged patch를 production `fast_engine/` + tests로 승격
12. full Fast discovery
13. canonical CI
14. frontier 재계산 및 checkpoint 문서 완결
15. 모든 Nayuta temp helper/workflow 제거
16. `.github/workflows`가 `ci.yml`, `pages.yml`만 남는지 확인
17. clean final HEAD canonical CI
18. `master` 불변 확인

## 12. 절대 하지 말 것

- public 3 roster를 맞추기 위해 character name `나유타` runtime branch 추가
- changed RL이라는 이유로 generic charge weapon_change 전체를 열기
- `skill_damage` semantics를 ordinary normal attack으로 근사
- `duration_bullets`를 mode skill shot으로 소비
- Privaty live cadence blocker를 Nayuta test 편의를 위해 열기
- Moris timing과 다를 때 tolerance를 넓혀 통과시키기
- 60Hz global loop 추가
- staged gate가 green이 되기 전에 production patch commit
