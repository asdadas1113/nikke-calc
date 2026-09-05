# Fast Engine full-burst conditional permanent passive 체크포인트 — 2026-09-06

## 1. 목적

finite reference-stack 복구 다음 단계로, Moris의 `passive + during_full_burst` 영구 버프를 단순 static fold나 blocker 삭제가 아니라 실제 runtime 의미론으로 소유한다.

이번 public anchor는 `도로시 : 세렌디피티`의 `광익 2`다.

- `atk_pct +75.24%`
- target `self`
- duration `-1`
- max stack `1`
- timing `passive` (`battle_start`로 compile)
- condition `during_full_burst`

`광익 3:accuracy_pct`, 츠바이 multi-stack/on-attack, 라피 : 레드 후드 enemy stack, 소다 hit-count stack은 같은 full-burst 문구가 있어도 별도 미소유 의미론이므로 이번 slice에 포함하지 않는다.

## 2. Moris 의미론

`calculator/buff_manager.py`와 `calculator/timeline.py`를 직접 추적했다.

### 2.1 passive row는 battle start에 등록된다

Moris의 permanent `passive`는 battle start에서 condition이 false여도 active row 자체를 등록한다. 이때 activation event만 suppress한다.

즉 `광익 2`는 전투 시작부터 row가 존재하지만 full burst 밖에서는 수치 기여가 0이다.

### 2.2 permanent runtime condition은 live gate다

`get_buffs()`는 duration이 `None/-1`인 runtime-conditioned buff의 condition을 매 read마다 평가한다.

따라서:

- full burst 진입 즉시 `광익 2` ATK contribution ON
- full burst 종료 즉시 contribution OFF
- row 자체를 매번 생성/삭제하는 모델은 아님

`BuffManager.tick()`의 `_cond_passive_prev`는 False→True / True→False 전환 로그만 남긴다.

### 2.3 로그와 실제 기여 시점은 다르다

통제 squad:

- `라피 : 레드 후드`
- `레드 후드`
- `프리카`
- `민트`
- `도로시 : 세렌디피티`

30 s, first burst 3.0 s에서 Fast full-burst 경계:

- starts: `3.399999999999993`, `15.933333333333705`, `28.46666666666633`
- ends: `13.400000000000245`, `25.93333333333314`

Moris `광익 2` transition log:

- activate `3.4166666666666594`
- expire `13.416666666666913`
- activate `15.950000000000372`
- expire `25.949999999999807`
- activate `28.483333333332997`

각 로그는 true phase edge보다 정확히 `1/60 s` 늦다. 이것은 `tick()`이 다음 outer frame에서 전환을 관측하기 때문이다.

하지만 timeline은 start에서 먼저 `state["full_burst"] = True`, cache invalidate를 수행한 뒤 같은 `t`의 `get_buffs()`와 pending burst damage를 계산한다. end도 먼저 `full_burst=False`로 바꾼다.

따라서 **실제 대미지 의미론의 ON/OFF 경계는 full-burst start/end 그 시각 자체**다. Fast가 1프레임 늦은 로그를 모사하면 오히려 틀린다.

## 3. Fast 구현

production semantic commit:

- `7df61bd3853cca202808a43d2d155a38a36df450` — `Fast: own full-burst conditional permanent passive`

### 3.1 narrow owned shape

`full_burst_conditional_permanent_passive_shape()`를 추가했다.

지원 조건:

- buff
- stat: `atk_pct`, `atk_flat`, `atk_caster_based_pct`만
- non-null value
- target `self`
- duration `None/-1`
- max stack `1`
- no max-trigger / tick interval / parameters
- condition 정확히 하나: `during_full_burst`
- trigger 정확히 하나: raw `passive`, event key `battle_start`

이번 slice에서 의도적으로 제외:

- `not_during_full_burst`
- `accuracy_pct` 및 다른 hit/core/cadence 연계 stat
- all-allies / dynamic target
- multi-stack
- on-attack / hit-count 등 다른 timing

### 3.2 sparse phase-edge sync

`TriggerDispatcher`가 owned full-burst passive ID만 별도 보관한다.

`BurstRuntime`에서 `BurstMachine.handle()`이 phase를 먼저 바꾼 직후:

- `FULL_BURST_START` → condition true이면 materialize
- `FULL_BURST_END` → condition false이면 de-materialize

그 다음에 `full_burst_start/end` signal을 dispatch한다.

이 순서는 Moris가 phase state를 먼저 바꾸고 같은 시각의 buff read/trigger/damage를 처리하는 순서와 맞는다.

global 60 Hz loop나 frame polling은 추가하지 않았다.

### 3.3 condition transition은 fresh trigger가 아니다

기존 self-stack/self-state conditional passive와 동일하게 `activate_group/deactivate_group`만 사용한다. condition이 바뀌었다고 generic `event:{effect.name}`을 새로 방송하지 않는다.

추가 score guard로, 해당 passive 이름을 다른 effect가 named event나 named state condition으로 참조하면 이번 slice는 계속 fail-closed한다.

## 4. regression

신규 `test_damage_full_burst_conditional_passive.py`에서 다음을 고정했다.

1. real Dorothy `광익 2`는 owned shape
2. `광익 3:accuracy_pct`는 계속 unowned
3. Fast materialization/de-materialization이 exact full-burst start/end와 일치
4. Moris transition log는 각 실제 edge보다 정확히 `DT = 1/60 s` 늦음
5. max-stack 2, all-allies, extra parameters, `not_during_full_burst` 이웃 shape는 fail-closed

기존 false-supported guard도 갱신해 exact newly-owned shape만 blocker-free이고 `not_during_full_burst` 이웃은 계속 blocker가 남도록 했다.

## 5. public frontier

semantic commit 기준:

- source cases: `24`
- unique ordered memberships: **23**
- certified: **2**
- gaps: **21**

certified는 그대로다.

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

fresh blocker families:

- normal delivery: **47**
- normal state: **34**
- skill damage: **27**
- skill-state delivery: **49**
- weapon change: **12**
- cadence: **59**
- control: **4**
- periodic grid: **1**

finite reference-stack checkpoint 대비:

- normal delivery `49 → 47`
- skill-state delivery `51 → 49`
- 나머지 unchanged
- certified `2 → 2`

감소 4건은 Dorothy `광익 2`가 등장하는 public 두 membership에서 normal/skill delivery blocker가 각각 하나씩 제거된 결과다.

## 6. 검증

promotion workflow:

- run `33987191917`
- job `101362856181`
- focused regressions: success
- Fast complete discovery: **288/288**
- structural 180 s median 약 **187.97 ms**, events `539`
- RHQ 30 s parity 유지: `236373847.0` vs `236465053.42473748`, relative error 약 `+0.0386%`
- public frontier exact assertion: success

semantic promotion commit에서 임시 full-burst workflow 3개를 모두 제거했다.

## 7. 현재 안전 경계

이번 구현은 “full burst 조건이 붙은 permanent passive 일반”을 전부 연 것이 아니다.

계속 fail-closed:

- `not_during_full_burst` permanent passive
- Dorothy `광익 3:accuracy_pct`
- Tsubai multi-stack / on-attack / bullet-lifetime 조합
- Rapi enemy stack marker
- Soda hit-count stack
- named-state/named-event consumer가 붙은 dormant passive
- broader producer/remover/mutator dependency

## 8. 다음 단일 체크포인트

**broader producer/mutator dependency ownership**

다음에는 단순히 executable provider가 생겼다는 이유로 downstream state를 자동 인증하지 않고, `remove_named_buff` 등 scored-state mutator가 실제 public score에 미치는 dependency를 다시 분해한다.

우선순위:

1. 현재 public blocker 중 scored direct-damage state를 실제로 만들거나 지우는 producer/mutator pair를 전수 추출
2. marker-only remover와 score-affecting remover를 분리
3. activation/removal ordering과 target cohort를 Moris에서 직접 probe
4. exact reachable pair만 generic dependency ownership

raw coverage expansion, optimizer production integration, global frame loop는 계속 보류한다.
