# Volume live-ammo / lazy-rank certification 체크포인트 — 2026-09-06

## 0. 결론

public `레이드_볼륨`의 마지막 두 blocker를 Moris oracle로 분리 검증한 뒤, Fast가 기존 sparse primitive를 좁은 compile-time ownership proof 아래 소유하도록 확장했다.

대상 root cause:

1. `홍련 : 흑영 / 화무십일홍 · 수라 2 / ammo_charge_pct`
2. `리버렐리오 / 차분한 수심 4 / rank_target_timing`

semantic production commit:

- `6bc7cbd0350da24dcb1bd5136dbdf0e5941f4103` — `Fast: own Volume live-ammo and lazy-rank cadence`

결과적으로 `레이드_볼륨`은 세 번째 public certified membership이 됐다.

이번 변경은 generic live-max-ammo refill이나 generic dynamic rank selector를 연 것이 아니다. exact transaction shape와 recipient cadence safety를 scorer/runtime이 함께 증명할 때만 blocker를 제거한다.

## 1. Moris oracle — 홍련 : 흑영 refill

`화무십일홍 · 수라` 계열에서 `full_burst_start` transaction의 relevant order는 다음이다.

1. self `max_ammo_pct +60%` finite buff 적용
2. 이어지는 `화무십일홍 · 수라 2 / ammo_charge_pct=100` 실행

Moris는 `ammo_charge_pct` activation 시점의 **실효 최대 장탄수**를 읽는다.

public `레이드_볼륨` 첫 full burst에서 확인한 상태:

- base magazine: `16`
- live `max_ammo_pct +60%` 반영 effective magazine: `26`
- `수라 2` 100% refill 후 ammo: `26`

홍련 weapon control은 pure charge `reload.cancel_on_full=true` shape이며 기존 Fast charge runtime이 이미 소유하고 있다. full refill이면 진행 중 reload를 취소하고, partial refill이면 취소하지 않는 기존 계약도 회귀 테스트로 유지한다.

## 2. Moris oracle — 리버렐리오 lazy rank target

`차분한 수심 4`는:

- target: `LOWEST_ATK_BURST3:1`
- stat: `charge_speed_caster_based_pct`
- finite positive buff
- trigger: `full_burst_start`

Moris는 ATK-rank target을 actor/event transaction 시작 전에 고정하지 않고, same-timestamp ATK 변화가 반영된 뒤 **첫 실제 target 조회 시점**에 lazy resolve한다.

public trace에서 모든 관찰 full-burst start의 `차분한 수심 4` recipient는 `홍련 : 흑영`이었다.

Fast에는 이미 lazy ATK-rank target primitive가 있었으므로 새 global ordering loop를 만들지 않았다. 이번 checkpoint는 exact cadence shape를 해당 primitive가 사용하도록 ownership proof만 확장했다.

## 3. production ownership

### `fast_engine/engine/dispatcher.py`

기존 `_lazy_rank_target_shape_supported()`를 다음 exact cadence slice까지 확장했다.

- `LOWEST_ATK_BURST3`
- count `1`
- `charge_speed_caster_based_pct`
- positive finite value/duration
- no conditions / no bullet lifetime / no extra parameters
- exactly one `full_burst_start` trigger

기존 direct-damage lazy-rank slice는 그대로 유지한다.

### `fast_engine/engine/score.py` — live max ammo → refill

live max-ammo mutation이 존재한다는 이유만으로 모든 refill을 열지 않는다.

새 proof는 다음을 모두 요구한다.

- refill actor와 target이 동일 self
- exact `ammo_charge_pct=100`
- exactly one `full_burst_start` trigger
- no condition / no parameters
- 같은 actor의 same-event positive finite self `max_ammo_pct` provider가 정확히 하나
- compiled actor effect order에서 max-ammo provider가 refill보다 앞섬
- competing live max-ammo provider 없음
- recipient weapon cadence가 기존 dynamic charge/rapid safety proof를 통과

따라서 Moris처럼 activation 순간의 live effective max ammo를 기존 `_full_ammo()`가 읽는 경로를 안전하게 승격한다.

### lazy B3 recipient score proof

`LOWEST_ATK_BURST3` cadence effect는 target resolver가 동적이라는 사실만으로 전 squad를 dynamic actor로 올리지 않는다.

compile-time에서:

- roster의 base B3 후보 집합을 계산
- 다른 actor가 burst stage를 변경할 수 있는 shape가 있으면 fail closed
- 모든 가능한 B3 recipient가 해당 cadence stat에 대해 charge-safe인지 검사

이 조건을 모두 통과할 때만 lazy rank cadence blocker를 제거한다.

## 4. fail-closed 경계

다음 변형은 계속 지원하지 않는다.

- partial 또는 다른 값의 live-max `ammo_charge_pct`
- flat/live max-ammo source를 섞은 wider transaction
- competing max-ammo provider
- provider가 refill 뒤에 오는 ordering
- 다른 event key
- ambiguous/non-self refill target
- condition/parameter가 붙은 refill
- `LOWEST_ATK_BURST3`가 아닌 cadence rank selector
- count가 1이 아닌 selector
- 다른 cadence stat
- permanent / zero-or-negative / bullet-lifetime lazy cadence buff
- named-state/event consumer dependency가 붙은 lazy cadence state
- 가능한 B3 recipient 중 하나라도 charge cadence unsafe
- burst stage를 다른 actor가 동적으로 바꾸는 roster

즉 기존 broad `ammo_charge_pct`, live max-ammo, dynamic rank family는 여전히 fail closed다.

## 5. public scope audit

same exact owned shape가 public frontier에 존재하는 범위도 전부 감사했다.

lazy `LOWEST_ATK_BURST3` charge-speed slice:

- `스쿼드4`
- `레이드_네온벨벳`
- `레이드_볼륨`

live self max-ammo → 100% refill slice:

- `스쿼드4`
- `레이드_볼륨`

이 membership들은 가능한 B3 recipient가 모두 현재 charge cadence safety proof를 통과한다.

따라서 blocker 감소가 `레이드_볼륨` 한 조합에만 국한되지 않는 것은 의도된 generic-shape coverage이며 캐릭터명 runtime 분기가 아니다.

## 6. regression / runtime audit

새 regression:

- `fast_engine/tests/test_damage_volume_cadence_rank.py`

기존 관련 regression도 함께 실행했다.

- `test_damage_charge_reload_cancel_control.py`
- `test_damage_ammo_pct_named_event.py`
- Maid Mast lifecycle / stack mutation regression

focused promotion gate:

- `33/33` success

고정한 계약:

- public owned scope exactness
- first full-burst Moris/Fast live max ammo + refill parity
- lazy target first-read result parity
- single-source-before-refill requirement
- competing/reordered/wider refill fail closed
- every static B3 candidate charge-safe requirement
- lazy shape neighboring variants fail closed
- named-state consumer collision fail closed
- reload cancel-on-full 기존 의미론 보존

production 180초 audit:

- `레이드_볼륨` `score_static_squad()` 완주
- `unsupported=()`
- events processed: `1653`

진단에서 얻은 Fast score 값은 certification 자체의 oracle이 아니라 runtime 완주/unsupported-zero 여부 확인용이다.

## 7. public frontier 결과

canonical filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외
- exact ordered membership dedupe

production frontier audit 결과:

- source cases: `24`
- unique ordered memberships: `23`
- certified: **3**
- gaps: **20**

certified:

- `레이드_레드후드퀀시`
- `레이드_볼륨`
- `컨트롤_미란다미하라`

blocker families:

- normal delivery `47`
- normal state `22`
- skill damage `27`
- skill-state delivery `49`
- weapon change `12`
- cadence `57`
- control `4`
- periodic grid `1`

직전 Maid Mast checkpoint 대비:

- certified `2 → 3`
- gaps `21 → 20`
- cadence `59 → 57`
- normal state `25 → 22`
- 나머지 unchanged

`레이드_볼륨`의 기존 마지막 두 blocker:

- `cadence:홍련 : 흑영:화무십일홍 · 수라 2:ammo_charge_pct`
- `normal_state:리버렐리오:차분한 수심 4:rank_target_timing`

은 모두 제거됐다.

## 8. canonical gate

pre-cleanup production HEAD canonical CI:

- run `34016205089`
- result: success
- Fast damage: `215/215`
- Fast complete discovery: `324/324`
- structural performance: median `186.61ms`, events `539`
- calculator: `137/137` (`1` skipped)
- optimizer: `374/374`
- bridge: `31/31` (`1` skipped)
- site: `385/385`
- golden snapshot: `29/29`
- doclint: characters `199`, implementation keys `309`, exceptions `18`

performance threshold는 변경하지 않았다.

final cleanup/docs commit 뒤에도 clean HEAD에서 같은 canonical gate를 다시 통과해야 한다. 최종 run ID를 이 문서에 다시 쓰면 doc-only commit으로 새 run이 생기는 순환이 발생하므로 최종 clean run ID는 handoff 이후 작업 결과/최종 보고에서 확인한다.

## 9. 다음 checkpoint

다음 단일 checkpoint는 **Little Mermaid producer/mutator/sequential-damage 결합 lifecycle**이다.

그 뒤 후보:

1. Crown `로얄 에타이어 4` normal/skill shared recipient/lifetime semantics
2. public frontier pressure 재계산

계속 `Moris trace → dependency/public scope audit → fail-closed 정의 → focused implementation → negative regression → canonical CI → frontier → docs/cleanup` 순서를 유지한다.
