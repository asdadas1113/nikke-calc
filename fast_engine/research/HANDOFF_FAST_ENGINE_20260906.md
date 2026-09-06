# Fast Engine 작업 인계 — 2026-09-06 / 09-07 갱신

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다. `calculator/`는 Moris oracle로만 사용한다.**

Fast Engine은 Moris 복제품이 아니라 optimizer용 고속 sparse-event ranking engine이다.

금지 원칙:

- global 60Hz loop 추가 금지
- 캐릭터명 기반 runtime 분기 금지
- unsupported comparison-critical mechanic silent zero 금지
- 한 번에 하나의 semantic checkpoint만 완결

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
2. `fast_engine/research/MORAN_RAPID_WEAPON_CHANGE_LIFECYCLE_CHECKPOINT_20260907.md`
3. `fast_engine/research/CROWN_HEAL_RECEIVED_SHARED_LIFETIME_CHECKPOINT_20260906.md`
4. `fast_engine/research/LITTLE_MERMAID_REPLACEMENT_SQUAD_AMMO_CHECKPOINT_20260906.md`
5. `fast_engine/research/VOLUME_LIVE_AMMO_LAZY_RANK_CHECKPOINT_20260906.md`
6. `fast_engine/research/MAID_MAST_HANGOVER_LIFECYCLE_CHECKPOINT_20260906.md`
7. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`

## 1. latest completed semantic checkpoint

**목단 `정정당당 승부다!` finite rapid weapon-change lifecycle 완료.**

semantic commits:

- `a8e0b51cb122a0e424404ed2a49e485a09d6ebd4` — `Fast: own finite rapid weapon-change lifecycle`
- `f769473f19e1f269027feb69e2c8566582211062` — `Fast: keep rapid weapon-change off baseline hot path`
- `abbc8c4616b2bca724e70634fd166668185e8d6a` — `Fast: scope rapid weapon view to changed actors`

Moris oracle:

- base 목단: AR / auto / 12/s / max ammo 60 / coeff 14.71
- `정정당당 승부다!`: self, 10s, `burst_cast`
- changed weapon: SMG / auto / 24/s / infinite ammo / coeff 14.7
- dependent `다 덤벼! 2`: `bonus_damage 47.18`, `self_state:정정당당 승부다!`, reducible `hit_count:5`
- hit count는 weapon-change session별이 아니라 whole-combat phase
- 24/s nominal deadline과 Moris 60Hz observed tick을 분리
- mode 종료 시 literal 60이 아니라 active modifiers를 반영한 live effective full ammo로 restore

Fast ownership은 exact finite self rapid weapon-change + dependent hit-count graph에만 열린다. generic weapon-change는 계속 fail closed다.

상세는 `MORAN_RAPID_WEAPON_CHANGE_LIFECYCLE_CHECKPOINT_20260907.md` 참고.

## 2. Moran에서 발견한 performance safety

semantic correctness 뒤 두 개의 sparse-performance 문제가 드러났다.

### 2.1 whole-squad live weapon callback

20초 profiling run `34055659461` / job `101546969726`:

- `sync()` 206회에 약 2.395s
- Maid Mast `_weapon`: **271,449회**, 약 1.774s
- Moran `_weapon`: **3,357회**, 약 0.031s

실제 weapon-change actor가 목단 하나인데 unrelated rapid actors까지 dynamic weapon lookup을 수행하고 있었다.

수정:

- effective weapon callback을 executable rapid weapon-change actor set에만 attach
- 나머지 rapid actors는 base-weapon hot path 유지

### 2.2 boundaryless horizon rescan

actor-scoping 후에도 180초 audit가 timeout됐다.

원인:

- local observable boundary가 없는 rapid actor가 `_predict_next_boundary()`에서 매 invalidation마다 horizon 끝까지 모든 physical shot을 재시뮬레이션

수정:

- `_has_local_boundary_interest()` 추가
- last-bullet / hit threshold / pellet threshold / active dynamic bullet lifetime이 없으면 predictor 즉시 `None`
- ordinary shots는 기존 `advance_to()` block compression으로 global event / score horizon까지 전진
- squad-ammo pre-shot planner는 별도 경로 유지

이 최적화는 의미론 완화가 아니라 기존 sparse architecture 복구다.

## 3. production audit / current frontier

post-fix 180초 `스쿼드4` audit:

- run `34055907810` / job `101547646303`
- elapsed `1.5432331279999971s`
- events `2459`
- squad total `2106138999.9456573`
- unsupported `()`

canonical public filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외
- exact ordered membership dedupe

fresh frontier:

- source cases `24`
- unique memberships `23`
- certified **6**
- gaps **17**

certified:

- `스쿼드4`
- `레이드_레드후드퀀시`
- `레이드_아스카루드밀라`
- `레이드_델타`
- `레이드_볼륨`
- `컨트롤_미란다미하라`

blocker families:

- normal delivery `46`
- normal state `16`
- skill damage `25`
- skill-state delivery `48`
- weapon change `7`
- cadence `53`
- control `4`
- periodic grid `1`

직전 Crown checkpoint 대비:

- certified `5 → 6`
- gaps `18 → 17`
- weapon change `12 → 7`
- cadence `57 → 53`
- 나머지 unchanged

## 4. validation completed

Moran focused contracts:

- `test_damage_moran_weapon_change_lifecycle.py`: 6 tests
- `test_damage_dynamic_reload_scoring.py`: 12 tests
- neighboring dynamic weapon-change / performance tests green

pre-cleanup canonical CI:

- run `34056008391`
- job `101547955891`
- HEAD `0c91cde7b9d45260c59667b1140d678650d54f76`
- result: **success**

exact gates:

- doclint characters `199`, implementation keys `309`, exceptions `18`
- Fast damage `236/236`
- Fast complete discovery `345/345`
- structural performance median `197.62ms`, events `539`
- full-discovery structural median `196.60ms`, events `539`
- RAPI parity reference `236373847.0`, Fast `236465053.42473748`, relative error `0.0003858566668650809`
- calculator `137/137` (`1` skip)
- optimizer `374/374`
- bridge `31/31` (`1` skip)
- site `385/385`
- golden `29/29`

performance threshold는 변경하지 않았다.

## 5. current phase

계속 **false-supported safety closure → semantics restoration** 단계다.

완료된 주요 restoration에 다음을 추가한다.

17. finite self rapid weapon-change + whole-combat hit-count conditioned damage lifecycle
18. rapid nominal fire deadline과 sparse Moris 60Hz observation 유지
19. rapid live effective weapon view를 실제 changed actor에만 한정
20. boundaryless rapid planner의 horizon rescan 제거 / sparse fast-return

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 6. fresh pressure / 다음 단일 checkpoint

post-Moran pressure run:

- `34056292716` / job `101548691790`

최다 exact blocker는 4회 동률:

- `skill_damage:리틀 머메이드:거품 난사:sequential_damage:10`
- `cadence:프리바티:EX 매거진 2:reload_speed_pct`
- `cadence:프리바티:EX 매거진 3:max_ammo_pct`

Little Mermaid `거품 난사`는 이미 `레이드_델타`에서 exact all-certified-rapid squad-ammo pre-shot lifecycle을 소유한다. 남은 4 roster를 열려면 mixed/unsupported squad-ammo family를 넓혀야 해서 다음 checkpoint로는 상대적으로 넓다.

Privaty는 네 membership에서 두 cadence blocker가 항상 함께 나타나고 compiled shape도 동일하다.

- `EX 매거진`: all-allies `atk_pct +23.61`, 10s, full-burst start
- `EX 매거진 2`: all-allies `reload_speed_pct +51.16`, 10s, full-burst start
- `EX 매거진 3`: all-allies `max_ammo_pct -50.66`, harmful, 10s, full-burst start
- `EX 매거진 4`: all-allies `atk_dmg_pct +20.16`, 10s, full-burst start

다음 단일 checkpoint:

**Privaty `EX 매거진 2 + 3` all-allies reload-speed / negative max-ammo coupled cadence lifecycle**

재개 순서:

1. 네 public membership의 recipient weapon/cadence를 전수 수집
2. Moris에서 full-burst-start same-timestamp transaction trace
3. negative max-ammo activation 시 current ammo 즉시 clamp 여부 확인
4. buff 활성 중 reload start/completion과 live full-ammo 확인
5. 10초 expiry 시 max-ammo/current-ammo 복구 semantics 확인
6. reload-speed와 negative max-ammo를 따로 열지 말고 one lifecycle graph로 ownership proof 정의
7. broader all-allies negative max-ammo / reload family fail-closed negative regression
8. focused gate → full Fast → canonical CI → frontier 재계산

## 7. cleanup / final clean gate

Moran checkpoint 종료 시 모든 temporary Moran helper/probe/workflow를 제거한다.

최종 `.github/workflows`는 반드시:

- `ci.yml`
- `pages.yml`

두 파일만 남긴다.

cleanup/docs 뒤 **clean HEAD canonical `ci.yml` 전체 gate를 한 번 더 성공 확인**하고 종료한다.

최종 clean run ID를 기록하기 위한 추가 doc-only commit은 만들지 않는다. 다음 재개 시 branch HEAD, `master`, latest successful clean canonical run부터 확인한다.
