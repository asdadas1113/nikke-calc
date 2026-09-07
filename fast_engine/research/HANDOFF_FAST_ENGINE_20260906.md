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
2. `fast_engine/research/PRIVATY_CHARGE_LIVE_MAX_AMMO_SAFETY_CHECKPOINT_20260907.md`
3. `fast_engine/research/MORAN_RAPID_WEAPON_CHANGE_LIFECYCLE_CHECKPOINT_20260907.md`
4. `fast_engine/research/CROWN_HEAL_RECEIVED_SHARED_LIFETIME_CHECKPOINT_20260906.md`
5. `fast_engine/research/LITTLE_MERMAID_REPLACEMENT_SQUAD_AMMO_CHECKPOINT_20260906.md`
6. `fast_engine/research/VOLUME_LIVE_AMMO_LAZY_RANK_CHECKPOINT_20260906.md`
7. `fast_engine/research/MAID_MAST_HANGOVER_LIFECYCLE_CHECKPOINT_20260906.md`
8. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`

## 1. latest completed semantic checkpoint

**Privaty `EX 매거진 2 + 3` 조사에서 발견한 charge live max-ammo safety repair 완료.**

semantic production commit:

- `87b061d76b87e9815f0474731fa0222d4115f123` — `Fast: align charge live max-ammo semantics`

중요: Privaty blocker 자체를 public certification한 것이 아니다.

남아 있는 exact blockers:

- `cadence:프리바티:EX 매거진 2:reload_speed_pct`
- `cadence:프리바티:EX 매거진 3:max_ammo_pct`

둘은 다음 네 public membership에서 모두 의도적으로 fail-closed다.

- `스쿼드2`
- `레이드_아니스서머메이든`
- `레이드_라피앨리스`
- `레이드_트리나홍련`

상세는 `PRIVATY_CHARGE_LIVE_MAX_AMMO_SAFETY_CHECKPOINT_20260907.md` 참고.

## 2. Privaty Moris oracle

compiled pair:

- `EX 매거진 2`: all-allies `reload_speed_pct +51.16`, 10s, full-burst start
- `EX 매거진 3`: all-allies `max_ammo_pct -50.66`, 10s, full-burst start

Moris 의미론:

1. max-ammo percentage source를 source-by-source로 base magazine에 적용해 반올림
2. negative live cap이 current ammo보다 작아지면 active reload 중이 아닌 한 즉시 current ammo clamp
3. reload duration은 reload start의 speed를 snapshot
4. reload completion refill은 completion 당시 live max ammo 사용
5. cap expiry가 current ammo를 위로 refill하지 않음
6. effective magazine 최소 1

public trace 예:

- Snow White : Heavy Arms `12 -> 11`
- Aid / Maiden `12 -> 11`
- Little Mermaid `267 -> 215`
- Crown `697 -> 566`
- Rapi : Red Hood `697 -> 566`
- Privaty `39 -> 30`

## 3. 발견·수정한 Fast divergence

rapid runtime에는 이미 static/live split, source quantization, cap-drop clamp가 있었다.

charge runtime에는 두 차이가 있었다.

- live max-ammo percentage를 합산 후 한 번 반올림
- live cap 하락 시 current ammo clamp 누락

수정 후 `DynamicChargeCadenceRuntime`은:

- permanent unconditional self max-ammo source를 static-folded source로 별도 처리
- static/live `max_ammo_pct`를 source별 quantize
- active store에서 static-folded source를 제외해 double count 방지
- non-reloading actor의 current ammo를 live cap 하락 시 즉시 clamp
- active reload completion은 기존대로 completion 시점 live cap 사용

첫 staged attempt에서 static-folded source를 active source로 다시 더해 Snow cap이 Moris `11` 대신 `3`이 되는 문제가 잡혔다. 기대값을 완화하지 않고 static/live split을 고쳐 해결했다.

## 4. Privaty pair를 열지 않은 이유

### `스쿼드2`

- Tswei: existing rapid score safety 실패
- Nayuta: existing rapid score safety 실패
- Snow Heavy 자체는 reload upper `80.85%`로 charge safety 통과

Tswei/Nayuta의 별도 weapon/cadence dependency 때문에 all-allies pair ownership 불가.

### `레이드_아니스서머메이든`

- Maiden : Ice Rose: charge + `cover_during_delay`
- positive reload-speed upper bound `130.13%`
- Moris의 `reload_speed >= 100%` cover branch가 Fast 미소유

### `레이드_라피앨리스`

- Alice: charge + `cover_during_delay`
- upper bound `125.2%`
- 같은 >=100% special branch로 fail-closed

### `레이드_트리나홍련`

- Trina: charge RL + `is_clip=True`
- dynamic clip reload 미소유

따라서 Privaty pair를 지금 열면 false-supported가 된다.

## 5. validation / frontier

신규 regression:

- `fast_engine/tests/test_dynamic_charge_max_ammo_semantics.py` — 5 tests

focused:

- 신규 `5/5`
- dynamic reload `12/12`
- dynamic weapon-change `4/4`
- performance contract `2/2`

post-repair full Fast validation:

- run `34070413183` / job `101586577274`
- result: success
- Fast full discovery `350/350`
- structural median `141.31ms`, events `539`
- RAPI parity unchanged: reference `236373847.0`, Fast `236465053.42473748`, relative error `0.0003858566668650809`

canonical public frontier는 의도적으로 그대로다.

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

## 6. current phase

계속 **false-supported safety closure → semantics restoration** 단계다.

최근 완료 restoration:

17. finite self rapid weapon-change + whole-combat hit-count conditioned damage lifecycle
18. rapid nominal fire deadline과 sparse Moris 60Hz observation 유지
19. rapid live effective weapon view를 실제 changed actor에만 한정
20. boundaryless rapid planner horizon rescan 제거
21. charge live max-ammo static/live source 분리와 source별 percentage quantization
22. charge negative live cap의 non-reload current-ammo clamp

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 7. dependency-adjusted pressure / 다음 단일 checkpoint

raw top exact count만 보면 아직:

- Little Mermaid `거품 난사` 4회
- Privaty `EX 매거진 2` 4회
- Privaty `EX 매거진 3` 4회

지만 이 셋은 이미 상위 dependency에 막혀 있다는 것이 확인됐다.

Crown `로얄 에타이어 4` 3회도 reachable heal-provider dependency 때문에 의도적으로 남겨 둔 family다.

따라서 다음 단일 checkpoint는 raw count보다 독립적으로 닫을 수 있는 ownership graph를 우선한다.

**다음 단일 checkpoint: Nayuta `기억 연소` weapon-change lifecycle shape audit → exact ownership 여부 결정.**

`weapon_change:나유타:기억 연소`는 현재 3 public membership에 반복된다.

- `스쿼드2`
- `레이드_네온벨벳`
- `레이드_소다`

재개 순서:

1. 세 public membership의 Nayuta compiled effect / weapon / consumer graph 전수 수집
2. Moris에서 weapon-change activation/end와 ammo/cadence transition trace
3. Moran finite rapid weapon-change primitive와 동일한 축인지 비교
4. 같은 이름 state를 보는 damage/cadence consumer가 있으면 lifecycle graph에 포함
5. class-changing / infinite-ammo / clip / external recipient가 섞이면 즉시 fail-closed
6. exact generic ownership proof + neighboring negative regression
7. focused → full Fast → canonical → frontier 재계산

shape audit에서 Moran primitive와 구조적으로 다르면 이 checkpoint는 확장하지 않고 fail-closed 근거만 기록한 뒤 Alice/Anis-Star 등 다음 dependency-adjusted 후보로 이동한다.

## 8. cleanup / final clean gate

Privaty checkpoint 종료 시 temporary Privaty helper/probe/workflow를 전부 제거한다.

최종 `.github/workflows`는 반드시:

- `ci.yml`
- `pages.yml`

두 파일만 남긴다.

cleanup/docs 뒤 clean HEAD canonical `ci.yml` 전체 gate를 한 번 더 성공 확인한다. 최종 run ID 기록용 추가 doc-only commit은 만들지 않는다.
