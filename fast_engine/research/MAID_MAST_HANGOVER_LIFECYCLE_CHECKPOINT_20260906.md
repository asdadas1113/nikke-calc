# Maid Mast reachable stack-3 hangover/removal lifecycle 체크포인트 — 2026-09-06

## 0. 결론

Anchor가 없는 public Maid Mast 조합에서 실제로 도달하는 `취기 3 stack → 숙취 → 취기 제거` lifecycle을 Fast가 sparse하게 소유하도록 구현했다.

public anchors:

- `레이드_루주`
- `레이드_브리드디젤`

이번 지원은 generic stun이나 generic `remove_named_buff`를 연 것이 아니다. compile-time ownership proof가 exact producer/control/remover/passive/weapon dependency graph 전체를 증명할 때만 runtime 지원한다.

semantic production commit:

- `10f9d52a608cc9c68e6f7183d4868d60314c45e2` — `Fast: own Maid Mast hangover lifecycle`

## 1. Moris oracle

90초, `first_burst_time=3.0`, expected RNG trace에서 첫 reachable stack-3 lifecycle:

### `레이드_루주`

- third full-burst end: `39.39999999999905`
- `숙취` activate: 같은 timestamp
- `숙취.expires_at`: `49.39999999999905`
- `취기` removal: 같은 `39.39999999999905`
- `파이레츠 스피릿 3` instant: 같은 timestamp
- `[39.4, 49.4)` 일반 사격 0회
- 다음 실제 기본 공격 log: `49.416666666665144`

### `레이드_브리드디젤`

- third full-burst end: `38.466666666665766`
- `숙취` activate: 같은 timestamp
- `숙취.expires_at`: `48.466666666665766`
- `취기` removal: 같은 timestamp
- `파이레츠 스피릿 3` instant: 같은 timestamp
- `[38.4666..., 48.4666...)` 일반 사격 0회
- 다음 실제 기본 공격 log: `48.48333333333186`

Moris의 separate expire log는 다음 60Hz observation tick에 기록되지만 buff의 논리적 lifetime은 activate 시점의 `expires_at = start + 10.0`이다. Fast control primitive는 이 half-open logical interval `[start, end)`를 사용한다.

같은 full-burst-end transaction의 effect order는 compiled actor order대로 `숙취` activation 후 paired remover가 `취기`를 제거하는 형태다. 이미 생성된 `숙취`는 `취기` removal과 독립적으로 원래 10초 lifetime을 유지한다.

## 2. 함께 소유한 의미론

이번 checkpoint는 다음을 하나의 dependency로 취급한다.

1. `취기` 3스택에서 full-burst end 도달
2. 같은 timestamp `숙취` self stun 10초 생성
3. 이어서 `파이레츠 스피릿 3`이 `취기` 제거
4. 이미 생성된 `숙취`는 source 제거 후에도 유지
5. stun `[start,end)` 동안 Maid Mast 일반 사격 중단
6. stun 동안 놓친 사격을 종료 후 catch-up하지 않음
7. MG ammo / warmup / 이미 시작한 reload 수명 보존
8. stun 동안 burst candidate에서 제외
9. 대체 후보가 있으면 즉시 대체 후보 사용
10. 모든 후보가 block이면 earliest unblock timestamp까지만 sparse wait
11. `취기` 제거 시 `파이레츠 하트` / `파이레츠 하트 2` conditional passive 동기화
12. 다음 `burst_enter:1`에서 `취기=1`과 conditional passives 재시작

finite `scaling_ref=취기` consumer는 activation-time stack capture를 이미 보유하고 있으므로 source 제거 후에도 자신의 기존 finite lifetime과 captured scaling value를 유지한다.

## 3. production 구조

### `fast_engine/engine/control_lifecycle.py`

`certified_stack3_self_stun_remove_lifecycles()`를 추가했다.

runtime 캐릭터명 분기는 없다. exact shape proof는 다음을 동시에 요구한다.

- unique permanent harmful self stack provider
- `accuracy_pct -20`, max stack 3, `burst_enter:1`
- exact self stun 10초, `full_burst_end`, stack>=3
- exact paired self `remove_named_buff`, same condition/event, provider target
- control effect 직후 remover ordering
- exact `파이레츠 하트` / `파이레츠 하트 2` conditional permanent passive pair
- 기존 owned finite reference consumers만 허용
- supported non-clip `auto_warmup` MG weapon shape

### `ActiveEffectStore`

active control effect ID 집합에 대해 현재 시각의 active 여부와 가장 빠른 종료 시각을 조회하는 generic primitive를 추가했다.

half-open interval은 기존 `ActiveEffect.active(now)` 계약을 그대로 사용한다.

### `TriggerDispatcher`

compile-time proof가 반환한 control/remover effect ID만 executable로 승격한다.

paired remover는 proof-owned ID일 때만 named state를 제거하고 self-stack/self-state conditional passive를 즉시 sync한다.

standalone `remove_named_buff`나 generic stun family는 여전히 열리지 않는다.

### `DynamicRapidCadenceRuntime`

`weapon_block_until(actor, now)` callback을 추가했다.

- firing phase만 unblock point로 postpone
- reload phase 자체는 계속 진행
- blocked interval 동안 per-shot scheduler event를 만들지 않음
- 종료점 equality에서는 발사 가능
- missed-shot debt replay 없음
- MG warmup은 다음 실제 사격 직전에 전체 idle interval을 한 번 반영

Maid Mast actor는 이 ownership proof 때문에 dynamic rapid score actor로 승격되지만, 발당 global event loop로 전환하지 않는다.

### `BurstMachine`

캐릭터명과 무관한 candidate availability / unblock-time callbacks를 추가했다.

- ready + available 후보 중 기존 priority 첫 후보를 즉시 선택
- available 후보가 없으면 cooldown ready와 unblock을 결합한 earliest timestamp만 schedule
- 모두 indefinite block이면 새 event를 만들지 않음

cooldown reduction으로 waiting candidate가 재평가될 때도 동일 callback-aware ready-time을 사용한다.

### scorer / dispatcher / dynamic actor selection

세 경로 모두 같은 `certified_stack3_self_stun_remove_lifecycles()` ownership proof를 공유한다. scorer만 blocker를 지우고 runtime은 모르는 false-supported 상태를 만들지 않는다.

## 4. fail-closed 경계

다음 synthetic 변화는 ownership을 즉시 철회한다.

- duplicate `취기` provider
- competing stack provider/mutator
- additional stun provider
- `stun_immune`
- `event:state_end:취기` 또는 named-state consumer 충돌
- unsupported/ambiguous target
- extra/ambiguous condition
- weapon control 또는 unsupported weapon shape
- standalone stun/remove family

finite reference consumer는 exact previously-owned capture shape일 때만 예외로 허용한다.

## 5. regression

production regression:

- `fast_engine/tests/test_damage_maid_mast_hangover_lifecycle.py`
- 기존 `fast_engine/tests/test_damage_maid_mast_stack_mutation.py`

추가 hardening regression:

- `fast_engine/tests/test_damage_maid_mast_hangover_contract.py`

고정한 계약:

- 두 public anchor Moris activation/removal/logical expiry timestamp
- logical stun 정확히 10초
- `[start,end)` 일반 사격 0회
- end boundary 발사 가능 + catch-up 없음
- same-timestamp stun then `취기` removal
- finite reference capture source removal 독립성
- passive off/restart lifecycle
- alternate burst candidate immediate selection
- all-blocked earliest sparse wait
- existing reload completion preservation
- MG ammo/warmup preservation
- negative provider/mutator/stun/immunity/state-consumer/target/condition/weapon tests
- scheduler event 수가 shot count에 비례하지 않는 sparse 구조

focused contract diagnostic run:

- run `34006869114`
- job `101415603964`
- new hardening contract `5/5` success

public frontier audit:

- run `34006920000`
- job `101415740830`
- focused hardening `5/5` success

## 6. public frontier 결과

canonical filter:

- `지그_*` 제외
- 5인 squad
- `test_*` fixture member 제외
- exact ordered membership dedupe

결과:

- source cases: `24`
- unique ordered memberships: `23`
- certified: `2`
- gaps: `21`

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

blocker families:

- normal delivery `47`
- normal state `25`
- skill damage `27`
- skill-state delivery `49`
- weapon change `12`
- cadence `59`
- control `4`
- periodic grid `1`

직전 checkpoint 대비 정확한 변화:

- normal state `27 → 25`
- 나머지 unchanged
- certified `2 → 2`

사라진 것은 Anchor-free 두 unique membership의:

`normal_state:마스트 : 로망틱 메이드:파이레츠 스피릿 3:remove_named_buff`

이다.

Anchor 포함 3 membership은 직전 generic decrement checkpoint에서 이미 unreachable proof로 blocker가 제거되어 있었으므로, 현재 public Maid Mast 5 membership 전체에서 이 remover blocker는 0개다.

## 7. 다음 checkpoint

이번 Maid Mast lifecycle이 완전히 닫힌 뒤 다음 단일 checkpoint는 `레이드_볼륨`이다.

서로 독립적으로 Moris 검증할 두 root cause:

1. `홍련 : 흑영 / 화무십일홍 · 수라 2 / ammo_charge_pct`
2. `리버렐리오 / 차분한 수심 4 / rank_target_timing`

두 의미론을 각각 Moris로 검증하고, 둘 다 안전하게 소유될 때 세 번째 certified membership 확보를 시도한다.

그 뒤 순서:

1. Little Mermaid 결합 lifecycle
2. Crown `로얄 에타이어 4` shared recipient/lifetime semantics
3. frontier pressure 재계산

각 checkpoint는 계속 `Moris trace → dependency/public scope audit → fail-closed 정의 → focused implementation → negative regression → canonical CI → frontier → docs/cleanup` 순서를 유지한다.

## 8. 최종 promotion

이 문서 작성 시점에는 semantic/focused/frontier가 모두 완료됐고 temporary workflow cleanup을 같은 clean promotion commit에 포함한다. clean HEAD canonical `ci.yml` 전체 gate 결과는 promotion 후 확인한다.
