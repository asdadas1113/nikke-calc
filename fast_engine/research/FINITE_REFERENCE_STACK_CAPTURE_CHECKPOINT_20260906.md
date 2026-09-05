# Fast Engine finite reference-stack capture 체크포인트 — 2026-09-06

## 1. 목적

false-supported 안전성 봉합 이후 남겨 둔 `scaling == stack_count` / `scaling_ref` 계열을 단순 blocker 제거가 아니라 Moris의 실제 reference-stack 의미론으로 소유한다.

이번 public anchor는 다음 세 계열을 우선 감사했다.

- `마스트 : 로망틱 메이드`
- `아르카나 : 포츈 메이트`
- `토브`

핵심 질문은 source/provider stack을 consumer effect가 **발동 시점에 캡처하는가**, 아니면 effect lifetime 동안 계속 live reference하는가였다.

## 2. Moris 의미론

`calculator/buff_manager.py`의 실제 동작을 기준으로 확인했다.

### 2.1 finite duration

`scaling == stack_count`이고 `scaling_ref`가 있으며 consumer duration이 finite이면, Moris는 effect activation 순간 `ref_count(caster, scaling_ref)`를 `ActiveBuff.scaling_stack`에 저장한다.

따라서:

- provider가 3중첩일 때 consumer가 발동하면 magnitude는 3중첩 기준으로 고정
- consumer lifetime 중 provider가 1중첩으로 내려가도 기존 consumer magnitude는 3중첩 기준 유지
- 같은 consumer가 refresh/reactivation되면 그 새 activation 시점의 provider stack을 다시 캡처

Maid Mast `취기`가 대표적인 public shape다.

### 2.2 permanent / infinite duration

consumer duration이 `None` 또는 `-1`이면 `scaling_stack`을 캡처하지 않고 live reference를 유지한다.

따라서 솔린 : 프로스트 티켓 `티켓 효과` 같은 permanent/gauge reference는 이번 finite-capture slice로 열지 않았다.

### 2.3 provider가 activation 순간 존재하지 않는 경우

Moris의 `ref_count()`가 activation 순간 값을 찾지 못하면 `scaling_stack=None`이 유지되고, 이후 magnitude 조회에서는 live `ref_count()` fallback을 사용한다.

Fast도 supported shape에서 이 fallback과 cache invalidation을 보존한다.

## 3. public surface 감사

### 3.1 Maid Mast — owned provider

provider:

- `취기`
- self buff
- duration `-1`
- max stack `3`
- `burst_enter:1`
- Fast runtime executable

finite consumers:

- `파이레츠 스피릿` — `split_dmg_pct`, 10 s
- `파이레츠 스피릿 2` — `reload_speed_pct`, 10 s
- `파이레츠 로망 3` — `atk_caster_based_pct`, 10 s

reference-stack 자체는 이제 owned다.

다만 `파이레츠 스피릿 2`의 dynamic reload certification은 recipient weapon cadence 안전성이라는 별도 조건도 필요하다. 그래서 팀별로 결과가 다를 수 있다.

- `레이드_볼륨`: 해당 reload reference blocker 제거됨
- 일부 다른 membership: unsupported recipient cadence 때문에 동일 reload effect blocker가 계속 남을 수 있음

또 `파이레츠 스피릿 3:remove_named_buff`는 별도 producer/mutator semantics이므로 계속 fail-closed다.

### 3.2 Arcana : Fortune Mate — owned provider

consumer:

- `쌓여가는 사진첩`
- `atk_caster_based_pct`
- `allies_weapon:SG`
- duration 15 s
- `scaling_ref = 소중한 추억`

provider:

- `소중한 추억`
- self buff
- duration `-1`
- max stack `3`
- Fast runtime executable

따라서 이 finite reference-stack shape는 owned 범위에 들어간다.

### 3.3 Tove — 계속 fail-closed

consumer:

- `급조품의 기적`
- `급조품의 기적 2`
- finite `atk_caster_based_pct`
- `scaling_ref = 임시 개조`

하지만 provider `임시 개조`는 `event:급조 탄환` 경로가 현재 Fast에서 완전히 소유되지 않았고, consumer와 같은 self named provider shape도 아니다.

따라서 Tove는 이번 지원 범위에서 제외하고 reference-stack delivery blocker를 유지했다.

## 4. Fast 구현

production semantic commit:

- `2184b253ab22969fff63bc9a95b44aa8a6fc49d9` — `Fast: own finite reference-stack capture`

### 4.1 local shape predicate

`fast_engine/engine/reference_stack.py`에 finite capture shape를 명시했다.

지원 조건:

- buff
- `scaling == stack_count`
- non-empty string `scaling_ref`
- parameters가 정확히 `scaling`, `scaling_ref`
- finite positive duration
- consumer max stack `1`
- no `max_trigger`
- no `tick_interval`

permanent/live refs, gauge refs, DoT scaling, stacked consumer 등은 이 predicate로 열리지 않는다.

### 4.2 provider ownership proof

local shape만 맞는다고 score support를 주지 않는다.

`TriggerDispatcher.finite_reference_stack_dependency_score_safe()`가 추가로 다음을 증명해야 한다.

- 같은 caster의 effect 목록에 exact name provider가 정확히 하나
- provider는 self buff
- provider target/runtime shape가 Fast에서 executable
- provider 자체가 또 다른 reference-stack scaling에 의존하지 않음
- provider max stack이 유효한 positive integer

이 proof를 통과한 consumer effect ID만 `ActiveEffectStore` finite capture 대상으로 등록한다.

따라서 Maid Mast/Arcana는 열리고 Tove는 닫힌다.

### 4.3 own stack과 captured reference 분리

`ActiveEffect.stacks`는 consumer 자신의 중첩으로 유지하고, 별도 `scaling_stack`을 추가했다.

수치 계산은 supported reference consumer에 대해:

1. captured `scaling_stack`이 있으면 그것을 multiplier로 사용
2. activation 시 provider가 없어 `None`이면 live same-caster named-stack fallback
3. 일반 effect는 기존 own `stacks` 사용

`sum_stat`, effective ATK, damage-facing stat readers가 동일한 scale helper를 사용한다.

### 4.4 refresh / missing-provider cache

refresh는 `_activate_one()` activation boundary에서 current provider stack을 다시 캡처한다.

activation 시 provider가 없어서 live fallback 상태인 consumer는 provider stack 생성/증감/제거/만료 때 recipient EFFECT dependency를 invalidate한다. 이미 concrete finite stack을 캡처한 consumer는 provider 변화로 magnitude가 바뀌지 않는다.

## 5. synthetic regression

신규 `test_damage_reference_stack_capture.py`에서 다음을 고정했다.

1. provider 3 stack에서 finite consumer activation → magnitude `30`
2. provider를 이후 1 stack으로 낮춰도 기존 consumer magnitude `30` 유지
3. consumer refresh → 새 provider 1 stack을 recapture해 magnitude `10`
4. matching provider가 없으면 score support를 열지 않음
5. permanent reference consumer는 계속 fail-closed
6. Maid Mast direct reference delivery는 열리되 별도 reload-recipient cadence blocker는 membership별로 독립 유지
7. Arcana owned self provider는 열리고 Tove unowned provider는 계속 닫힘

## 6. downstream stat_applied 복구

Maid Mast `파이레츠 스피릿:split_dmg_pct`가 실제 owned producer가 되면서, 기존에 의도적으로 닫아 둔 Brady `나누고 싶은 맛`의 `event:stat_applied:split_dmg_pct` dependency가 reachable해졌다.

기존 regression 주석도 이 branch를 “Maid Mast captured scaling multiplier를 Fast가 소유하기 전까지” fail-closed한다고 명시하고 있었다.

자동으로 열지 않고 실제 Moris/Fast activation trace를 직접 대조했다.

40 s `레이드_앨리스브래디`:

- Fast: `[3.1999999999999935, 15.733333333333695, 15.933333333333705, 28.266666666666342, 28.46666666666633]`
- Moris: `[3.1999999999999935, 15.733333333333695, 15.933333333333705, 28.266666666666342, 28.46666666666633]`
- pairwise difference: `[0.0, 0.0, 0.0, 0.0, 0.0]`

따라서 이 exact split branch만 downstream dependency-safe로 복구했다.

반면 `dot_dmg_pct` 기반 `머물고 싶은 맛`은 provider 미소유 상태라 계속 fail-closed다.

probe:

- run `33985501903`
- job `101358141415`

## 7. public frontier

semantic commit 기준:

- source cases: `24`
- unique ordered memberships: **23**
- certified: **2**
- gaps: **21**

certified는 변하지 않았다.

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

fresh blocker families:

- normal delivery: **49**
- normal state: **34**
- skill damage: **27**
- skill-state delivery: **51**
- weapon change: **12**
- cadence: **59**
- control: **4**
- periodic grid: **1**

직전 lazy-rank checkpoint와 비교하면:

- normal delivery `55 → 49`
- skill-state delivery `62 → 51`
- cadence `62 → 59`
- 나머지 family unchanged

certified가 `2 → 2`로 유지됐으므로 이번 slice는 기존 gaps 내부의 실제 reference semantics를 복구했지 새로운 membership을 성급히 인증하지 않았다.

`레이드_볼륨`도 여전히 Scarlet `ammo_charge_pct`, Maid Mast named remover, Riverelio rank timing 등 별도 blocker가 남아 있다.

## 8. 검증

promotion workflow:

- run `33985621674`
- job `101358468826`
- focused reference-stack regressions: success
- Fast complete discovery: **284/284**
- structural 180 s median 약 **178.67 ms**, events `539`
- RHQ 30 s parity 유지: relative error 약 `+0.0386%`
- public frontier exact family assertions: success
- exact safe stat-applied match는 Brady `나누고 싶은 맛 / split_dmg_pct` 하나뿐

임시 workflow 5개는 semantic commit에서 모두 제거했다.

## 9. 작업공간

- branch: `fast-engine-phase2-20260901`
- latest semantic: `2184b253ab22969fff63bc9a95b44aa8a6fc49d9`
- `master`: 수정/병합하지 않음
- `.github/workflows`: `ci.yml`, `pages.yml`만 유지

## 10. 다음 단일 체크포인트

**generic full-burst conditional permanent passive semantics**

다음에는 permanent buff가 full-burst 조건에 의해 활성/비활성 상태를 바꾸는 generic shape를 다시 감사한다.

우선 원칙:

- static permanent modifier로 단순 fold하지 않는다.
- Moris가 battle start / full burst enter / full burst end에서 어떤 state transition을 만드는지 직접 probe한다.
- 조건이 사라졌을 때 permanent row를 remove하는지, 한번 activation되면 계속 남는지 구분한다.
- current public provider/consumer reachability를 먼저 확인하고 그 범위만 generic ownership한다.
- broader producer/mutator dependency와 raw coverage expansion은 계속 뒤로 둔다.
