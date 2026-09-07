# Fast Engine 작업 인계 — 2026-09-07

## 0. 재개 지점

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

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260907.md`
2. `fast_engine/research/NAYUTA_RAPID_TO_CHARGE_SKILL_WEAPON_CHANGE_WIP_CHECKPOINT_20260907.md`
3. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
4. `fast_engine/research/PRIVATY_CHARGE_LIVE_MAX_AMMO_SAFETY_CHECKPOINT_20260907.md`
5. `fast_engine/research/MORAN_RAPID_WEAPON_CHANGE_LIFECYCLE_CHECKPOINT_20260907.md`
6. `fast_engine/research/CROWN_HEAL_RECEIVED_SHARED_LIFETIME_CHECKPOINT_20260906.md`
7. `fast_engine/research/LITTLE_MERMAID_REPLACEMENT_SQUAD_AMMO_CHECKPOINT_20260906.md`
8. `fast_engine/research/VOLUME_LIVE_AMMO_LAZY_RANK_CHECKPOINT_20260906.md`
9. `fast_engine/research/MAID_MAST_HANGOVER_LIFECYCLE_CHECKPOINT_20260906.md`
10. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`

작업 시작 시 branch HEAD는 반드시 다시 조회한다. 이 문서를 작성한 뒤 docs/cleanup commit이 추가될 수 있으므로 문서 속 SHA를 무조건 현재 HEAD로 가정하지 않는다.

## 1. latest completed production checkpoint

Nayuta 작업 전 마지막 clean production baseline:

- `648749924cbbcba49dcfa19feae95307a7d8f42f`

이 commit은 Privaty probe workflow cleanup commit이며, 그 직전 completed semantic production change는:

- `87b061d76b87e9815f0474731fa0222d4115f123` — charge live max-ammo semantics safety repair

Privaty `EX 매거진 2/3` 자체는 아직 public certification하지 않았다.

현재 public frontier baseline:

- source cases `24`
- unique memberships `23`
- certified `6`
- gaps `17`

certified:

- `스쿼드4`
- `레이드_레드후드퀀시`
- `레이드_아스카루드밀라`
- `레이드_델타`
- `레이드_볼륨`
- `컨트롤_미란다미하라`

blocker families baseline:

- normal delivery `46`
- normal state `16`
- skill damage `25`
- skill-state delivery `48`
- weapon change `7`
- cadence `53`
- control `4`
- periodic grid `1`

Nayuta staged patch가 production에 아직 들어가지 않았으므로 이 frontier가 현재 production 기준이다.

## 2. current single checkpoint

**Nayuta `기억 연소` rapid→charge skill weapon-change lifecycle.**

public memberships:

- `스쿼드2`
- `레이드_네온벨벳`
- `레이드_소다`

이 checkpoint는 아직 WIP다. production implementation 완료로 보고 다음 후보로 넘어가면 안 된다.

상세 조사, Moris timing, staged architecture, first gate failure는:

- `NAYUTA_RAPID_TO_CHARGE_SKILL_WEAPON_CHANGE_WIP_CHECKPOINT_20260907.md`

에 기록했다.

## 3. Nayuta에서 이미 확정된 사실

### compiled shape

- base: `SMG / auto`, non-clip
- changed: `RL / charge`
- duration 10s
- infinite magazine
- damage coeff `275.18`
- charge time `1.8s`
- full-charge multiplier `250%`
- changed RL post-fire delay `0.215s`
- `skill_damage=True`

### damage classification

changed-mode shot은 ordinary normal attack이 아니라 weapon-mode skill damage다.

따라서 Fast는:

- normal attack bonus를 먹이면 안 됨
- weapon-mode skill core semantics를 써야 함
- full-charge layer를 써야 함
- changed RL만 보고 projectile-explosion bonus를 붙이면 안 됨
- `duration_bullets`를 이 shot으로 소비하면 안 됨

### dependent consumers

`full_charge_hit`에서 같은 actor의 두 damage consumer가 파생된다.

- `위선 5` — damage `150%`
- `위선 6` — bonus damage `380.46%`

### Moris first session

Nayuta가 실제 B2를 쓰는 `스쿼드2`, `레이드_소다`:

- mode enter `3.20`
- changed-mode shots:
  - `5.016667`
  - `7.05`
  - `9.066667`
  - `11.083333`
  - `13.10`
- mode end `13.20`
- base SMG resume `13.20`

expiration edge에서 unfinished charge는 취소되고, base rapid ammo는 입장 전 탄수를 복원하는 것이 아니라 **종료 시점 live full magazine**으로 재개한다.

`레이드_네온벨벳`은 현재 public policy에서 Nayuta가 B2를 쓰지 않아 실제 mode fire가 없지만, 이를 roster-specific unreachable shortcut으로 인증하지 않는다.

## 4. staged implementation 상태

branch에는 production patch 대신 다음 WIP helper를 의도적으로 보존한다.

- `.github/tmp_nayuta_apply.py`
  - Actions checkout에서 staged cross-mode implementation + tests 생성
- `.github/tmp_nayuta_probe.py`
  - compiled proof predicate diagnostic용

Nayuta probe/staging commit chain:

- `57afa08aaea127525f50612b8023374243a520cf`
- `bca6eafcf522ec2b8602cceb447bfd5c33cac752`
- `a3275a17fb7c0105167e248d13b4ebd150893fa5`
- `1399930de5539a83f8127ccc51cbc3091800c6d7`
- `6e4dd5d1cbed943aca7781cc123dc6cf04f8d532`
- `82667ea046478600fb181f218e759f798367cf92`
- `aa89f976ba1fac0a706f6356d925043deb2bae6e`
- `cd6ac874908510bf4447250136ace6d84b01f2ce`

중요: 이 chain에서는 production semantic commit이 생성되지 않았다.

## 5. first staged gate 결과

최신 staged run:

- run `34074367209`
- job `101597512747`
- result: failure

failure는 두 축이다.

### A. score ownership proof over-reject

신규 `_temporary_self_rapid_to_charge_skill_weapon_change_score_supported(...)`가 public 3 roster 모두 `False`.

현재 판단:

- staged graph 방향이 틀렸다고 확정된 것이 아님
- proof predicate 하나 이상이 실제 compiled shape보다 지나치게 좁음
- 다음 작업은 assertion/tolerance 완화가 아니라 exact predicate mismatch 찾기

현재 `.github/tmp_nayuta_probe.py`는 이를 출력하도록 준비돼 있다.

### B. public timing harness가 unrelated Privaty fail-closed guard에 걸림

`스쿼드2` full runtime timing test가 Nayuta runtime에 들어가기 전에:

- `프리바티 EX 매거진 2/3`
- static last-bullet cadence invalidation guard

에서 중단했다.

이것은 Nayuta runtime bug 증거가 아니다.

Privaty를 이 checkpoint 편의를 위해 열면 안 된다. Nayuta timing은 isolated runtime/unit harness로 검증한다.

## 6. current CI signal

`cd6ac874...`에 대한 canonical `ci.yml`:

- run `34074367264`
- result `success`

이 success는 production Fast가 여전히 Nayuta 이전 baseline이라는 사실과 맞는다. staged patch는 temp workflow checkout에서만 적용되었다.

handoff cleanup 뒤 새 HEAD의 canonical CI를 다시 성공 확인해야 한다.

## 7. 다음 작업자가 바로 해야 할 것

1. 현재 branch HEAD 조회
2. `master`가 `fb2fd9157aa14499daf6b9f185beb685d4393f90`인지 확인
3. 이 문서와 Nayuta WIP checkpoint를 읽기
4. `.github/tmp_nayuta_apply.py`, `.github/tmp_nayuta_probe.py` 확인
5. 필요 시 임시 workflow를 다시 만들어 helper 적용 후 diagnostic script를 실행
6. public 3 roster에서 score-proof predicate의 exact mismatch를 출력
7. 그 predicate만 필요한 만큼 수정
8. `스쿼드2` 전체 runtime 대신 isolated Nayuta timing harness 구성
9. 5-shot timing / 13.20 expiry / live-full resume / skill-damage classification 검증
10. negative neighboring shapes 유지
11. focused regression 전부 green
12. patched public frontier audit
13. 기대한 blocker만 줄었는지 확인
14. 그 후에만 production `fast_engine/` + tests로 승격
15. full Fast discovery
16. canonical CI
17. frontier 재계산
18. Nayuta checkpoint 문서 완료 상태로 갱신
19. 모든 Nayuta temp helper/workflow 제거
20. `.github/workflows`가 `ci.yml`, `pages.yml`만 남는지 확인
21. clean final HEAD canonical CI
22. `master` 불변 확인

## 8. 현재 phase를 바꾸지 말 것

계속 **false-supported safety closure → semantics restoration** 단계다.

현재까지 restoration한 주요 축:

- finite self rapid weapon-change lifecycle
- sparse Moris rapid nominal fire deadline observation
- rapid effective weapon view isolation
- Little Mermaid enemy replacement + global squad ammo crossing semantics
- Crown shared lifetime/heal_received semantics
- Privaty investigation에서 발견한 charge live max-ammo source quantization/clamp semantics

Nayuta cross-mode lifecycle가 닫히기 전 raw coverage expansion, optimizer integration, Crown/Alice/Anis-Star 다음 후보로 넘어가지 않는다.

## 9. handoff hygiene

handoff 시 active temporary workflow는 제거한다.

최종 `.github/workflows`는:

- `ci.yml`
- `pages.yml`

두 개만 남겨야 한다.

다만 production 미승격 WIP를 잃지 않기 위해 다음 두 staging script는 이번 handoff에서는 유지한다.

- `.github/tmp_nayuta_apply.py`
- `.github/tmp_nayuta_probe.py`

Nayuta checkpoint가 완료되면 이 둘도 반드시 제거한다.
