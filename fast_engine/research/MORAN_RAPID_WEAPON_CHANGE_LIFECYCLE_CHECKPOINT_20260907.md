# 목단 finite rapid weapon-change lifecycle 체크포인트 — 2026-09-07

## 0. 결론

public frontier에서 5개 membership을 동시에 막던 목단 `정정당당 승부다!`의 finite rapid weapon-change lifecycle을 Moris oracle 기준으로 고정하고 Fast가 exact graph만 소유하도록 확장했다.

주요 semantic commit:

- `a8e0b51cb122a0e424404ed2a49e485a09d6ebd4` — `Fast: own finite rapid weapon-change lifecycle`
- `f769473f19e1f269027feb69e2c8566582211062` — `Fast: keep rapid weapon-change off baseline hot path`
- `abbc8c4616b2bca724e70634fd166668185e8d6a` — `Fast: scope rapid weapon view to changed actors`

이번 checkpoint는 generic weapon-change를 연 것이 아니다. exact finite self weapon-change shape, whole-combat hit-count dependency, rapid cadence ownership, live full-ammo restore를 함께 증명하는 경우만 scorer/runtime/dispatcher가 소유한다.

결과적으로 `스쿼드4`가 여섯 번째 public certified membership이 됐다.

## 1. Moris oracle — `정정당당 승부다!`

목단 기본 무기:

- weapon type: AR
- fire mode: auto
- max ammo: 60
- fire rate: 12/s
- damage coeff: 14.71

`정정당당 승부다!` compiled shape:

- effect type: `weapon_change`
- target: self
- duration: 10s
- trigger: `burst_cast`
- conditions: none
- parameters:
  - `favorite: 3`
  - `weapon_type: SMG`
  - `damage_coeff: 14.7`
  - `max_ammo: -1`

변경 무기는 Moris에서:

- SMG
- auto
- 24/s
- infinite ammo
- normal coeff 14.7

로 동작한다.

## 2. dependent `다 덤벼! 2`와 whole-combat hit phase

`다 덤벼! 2` relevant shape:

- damage
- stat `bonus_damage`
- value `47.18`
- enemy target
- condition `self_state:정정당당 승부다!`
- reducible modulo `hit_count:5`
- harmless provenance `parameters={'favorite': 1}`

중요한 의미론은 hit count가 weapon-change session마다 0으로 돌아가지 않는다는 점이다. Moris `BuffManager` hit count는 전투 전체에서 이어지고, AR → temporary SMG → AR 전환 사이에도 phase가 보존된다.

따라서 Fast도:

- weapon-change 시작 시 physical weapon state는 새 세션으로 초기화
- global/actor hit_count는 보존
- 5-hit consumer는 전체 hit phase를 그대로 사용

하도록 고정했다.

## 3. 24/s nominal deadline과 Moris 60Hz 관측

24/s는 `1 / 24 = 0.041666...s`라 60Hz grid와 정확히 맞지 않는다.

Moris는:

1. nominal `next_fire_time`을 이전 nominal deadline 기준으로 누적하고
2. 실제 shot은 outer 60Hz tick 중 최초 `t >= next_fire_time`에서 관측한다.

따라서 관측된 shot timestamp를 다시 다음 deadline의 기준으로 사용하면 frame drift가 누적된다.

Fast는 이 exact rapid weapon-change slice에서:

- `fire_deadline`을 nominal time으로 별도 보존
- `_after_shot()`에서 `fire_deadline += interval`
- 실제 sparse shot timestamp는 `moris_observed_tick()`으로 계산

한다.

예를 들어 nominal `3.133333...s` boundary는 Moris 반복-add lattice에서 실제 `3.15s` tick에 관측된다.

global 60Hz loop는 추가하지 않았다.

## 4. weapon-change 종료와 live full ammo

Moris는 10초 weapon-change 종료 시 단순히 base max-ammo literal `60`으로 복구하지 않는다.

그 시점의 active max-ammo modifiers까지 포함한 **live effective full ammo**로 physical weapon state를 다시 만든다.

Fast도 effective weapon callback + existing live max-ammo resolver를 통해 같은 계약을 사용한다. synthetic/public regression에서 base 60 대신 live full 138이 필요한 경우를 고정했다.

## 5. narrow ownership / fail-closed 경계

첫 rapid weapon-change slice는 다음 exact shape만 허용한다.

- PLANNED `weapon_change`
- self target
- finite positive duration
- max stack 1 이하
- no max_trigger / tick / condition
- parameters가 허용된 provenance + weapon fields로만 구성
- `weapon_type=SMG`
- `max_ammo=-1`
- positive numeric `damage_coeff`
- 단일 `burst_cast` trigger
- 원래 무기가 ordinary non-clip auto rapid path
- unsupported control/cover edge 없음
- dependent hit-count consumer가 exact self-state + reducible modulo graph에 들어옴

다음은 계속 fail closed다.

- 다른 weapon type / clip / charge weapon-change
- 조건부 또는 parameterized wider shape
- generic finite/infinite weapon replacement
- unknown external named-state consumer
- unsupported recipient cadence
- non-owned dynamic bullet/control interactions

캐릭터명 기반 runtime 분기는 없다.

## 6. 첫 성능 회귀 — whole-squad live weapon callback

초기 semantic 구현은 correctness-focused gate를 통과했지만 `스쿼드4` production scoring이 비정상적으로 느려졌다.

진단:

- 20초: 약 2.33s
- 30초: 약 7.50s
- 45초: 8초 timeout

20초 profiling run `34055659461` / job `101546969726`에서:

- `sync()` 206회에 약 2.395s
- `effective_weapon()` 경유 `_weapon` 호출:
  - `마스트 : 로망틱 메이드`: **271,449회**, 약 1.774s
  - `목단`: **3,357회**, 약 0.031s

실제 rapid weapon-change actor는 목단 하나뿐인데, callback이 rapid runtime 전체에 붙어 unrelated actor까지 dynamic lookup을 반복하고 있었다.

수정:

- `attach_effective_weapon(callback, actors=...)`
- `_effective_weapon_actors`를 별도로 보존
- callback은 실제 executable rapid weapon-change actor에만 사용
- 나머지 rapid actor는 기존 base-weapon hot path 유지

이후 baseline structural performance 회귀는 해소됐다.

## 7. 두 번째 성능 회귀 — boundaryless planner horizon scan

actor-scoping 후에도 180초 `스쿼드4`는 20초 timeout을 넘겼다.

traceback은 `DynamicRapidCadenceRuntime.sync → _plan → _predict_next_boundary → _after_shot`에 집중됐다.

원인은 **local observable boundary가 전혀 없는 rapid actor도 매 dynamic invalidation마다 horizon 끝까지 모든 physical shot을 복사 시뮬레이션하여 'boundary 없음'을 다시 증명**하던 구조였다.

수정:

- `_has_local_boundary_interest(actor, now)` 추가
- local interest는:
  - `last_bullet`
  - hit-count threshold
  - pellet threshold
  - subclass의 active dynamic `duration_bullets`
- interest가 없으면 `_predict_next_boundary()` 즉시 `None`
- ordinary shots는 기존 `advance_to()`에서 다음 global event / score horizon까지 block-compressed 처리
- future dynamic bullet-lifetime activation은 그 자체가 global state event이므로 다시 plan 가능
- squad-ammo pre-shot planner는 별도 경로라 영향 없음

regression은 boundaryless actor에서 predictor가 physical `_after_shot()`을 호출하면 즉시 실패하도록 고정했다.

## 8. focused regression / performance

핵심 계약:

- `fast_engine/tests/test_damage_moran_weapon_change_lifecycle.py` — 6 tests
- `fast_engine/tests/test_damage_dynamic_reload_scoring.py` — 12 tests
- 기존 dynamic weapon-change / performance regression 포함

최종 focused temp gate에서 모두 success.

final staged structural performance 예:

- median `193.57ms`, events `539`

pre-cleanup canonical에서는:

- median `197.62ms`
- full discovery 내부 median `196.60ms`
- threshold `<250ms` 변경 없음

## 9. 180초 production audit

post-fix temp run `34055907810` / job `101547646303`:

- `스쿼드4`
- elapsed `1.5432331279999971s`
- events processed `2459`
- squad total `2106138999.9456573`
- char totals:
  - `363083749.47304976`
  - `232453914.47245413`
  - `297125431.40520877`
  - `1125287806.7455397`
  - `88188097.84940504`
- unsupported `()`

이 수치는 semantic oracle이 아니라 full 180s runtime completeness / performance diagnostic이다.

## 10. public frontier

canonical filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외
- exact ordered membership dedupe

fresh audit:

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

Crown checkpoint 대비:

- certified `5 → 6`
- gaps `18 → 17`
- weapon change `12 → 7`
- cadence `57 → 53`
- 나머지 unchanged

목단 blocker 자체 5개가 제거됐고, 목단이 unsafe rapid recipient였기 때문에 간접적으로 막혀 있던 all-allies reload cadence ownership까지 일부 함께 열려 cadence가 4 줄었다.

## 11. pre-cleanup canonical gate

run:

- `34056008391`
- job `101547955891`
- HEAD `0c91cde7b9d45260c59667b1140d678650d54f76`
- result: **success**

exact gates:

- doclint: characters `199`, implementation keys `309`, exceptions `18`
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

## 12. post-Moran pressure / 다음 단일 checkpoint

fresh pressure audit run `34056292716`에서 top exact blockers는 4회 동률이었다.

- Little Mermaid `거품 난사:sequential_damage:10` — 4
- Privaty `EX 매거진 2:reload_speed_pct` — 4
- Privaty `EX 매거진 3:max_ammo_pct` — 4

Little Mermaid 쪽은 이미 `레이드_델타`에서 exact all-certified-rapid `squad_ammo_consume:500` pre-shot lifecycle을 소유했다. 남은 4 roster를 열려면 mixed/unsupported squad-ammo family를 넓혀야 하므로 다음 checkpoint로는 범위가 상대적으로 크다.

Privaty는 네 roster 모두에서 동일한 coupled full-burst lifecycle이다.

- `EX 매거진`: all-allies `atk_pct +23.61`, 10s, full-burst start
- `EX 매거진 2`: all-allies `reload_speed_pct +51.16`, 10s, full-burst start
- `EX 매거진 3`: all-allies `max_ammo_pct -50.66`, harmful, 10s, full-burst start
- `EX 매거진 4`: all-allies `atk_dmg_pct +20.16`, 10s, full-burst start

현재 blocker는 이 중 cadence-sensitive `2`와 `3` 두 개이며 네 membership에서 항상 함께 나타난다.

따라서 다음 단일 checkpoint는:

**Privaty `EX 매거진 2 + 3` all-allies reload-speed / negative max-ammo coupled cadence lifecycle**

으로 잡는다.

재개 시에는 두 effect를 따로 열지 말고 Moris에서 같은 full-burst-start transaction의 recipient별 ammo clamp/reload timing/lifetime 상호작용을 한 graph로 추적한다. 특히 negative max-ammo가 active magazine을 즉시 clamp하는지, reload 중/종료 시점에 어떤 full-ammo를 쓰는지, 10초 expiry 시 ammo를 어떻게 복구하는지를 먼저 oracle로 고정한다.
