# Fast Engine 작업 인계 — 2026-09-06

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다. `calculator/`는 Moris oracle로만 사용한다.**

Fast Engine의 목적은 Moris 복제품이 아니라 optimizer용 고속 sparse-event ranking engine이다.

금지 원칙:

- 60Hz global loop 추가 금지
- 캐릭터명 기반 runtime 분기 금지
- unsupported comparison-critical mechanic silent zero 금지
- 한 번에 하나의 semantic checkpoint만 완결

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
2. `fast_engine/research/VOLUME_LIVE_AMMO_LAZY_RANK_CHECKPOINT_20260906.md`
3. `fast_engine/research/MAID_MAST_HANGOVER_LIFECYCLE_CHECKPOINT_20260906.md`
4. `fast_engine/research/MAID_MAST_GENERIC_STACK_DECREMENT_CHECKPOINT_20260906.md`
5. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
6. `fast_engine/research/FINITE_REFERENCE_STACK_CAPTURE_CHECKPOINT_20260906.md`
7. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`

## 1. latest completed semantic checkpoint

**`레이드_볼륨` live-ammo refill + lazy B3 rank-target certification 완료.**

semantic production commit:

- `6bc7cbd0350da24dcb1bd5136dbdf0e5941f4103` — `Fast: own Volume live-ammo and lazy-rank cadence`

public target:

- `레이드_볼륨`

마지막 두 blocker:

- `cadence:홍련 : 흑영:화무십일홍 · 수라 2:ammo_charge_pct`
- `normal_state:리버렐리오:차분한 수심 4:rank_target_timing`

둘 다 Moris oracle로 독립 검증 후 제거했다.

### owned live-ammo transaction

Moris는 `ammo_charge_pct` activation 순간의 live effective max ammo를 기준으로 refill한다.

public first full burst에서:

- 홍련 base magazine `16`
- same-event 선행 `max_ammo_pct +60%` 반영 effective max `26`
- 이어지는 `ammo_charge_pct=100` refill 후 ammo `26`

Fast는 기존 `_full_ammo()`와 ammo sink를 그대로 사용한다. 새 지원은 exact same-actor `full_burst_start`, single positive finite self max-ammo provider가 refill보다 먼저 오는 100% self refill transaction에서만 열린다.

### owned lazy rank cadence

`리버렐리오 / 차분한 수심 4`는:

- `LOWEST_ATK_BURST3:1`
- finite positive `charge_speed_caster_based_pct`
- `full_burst_start`

Moris는 same-timestamp ATK transaction이 정착된 뒤 first target read에서 lazy resolve한다. public trace recipient는 관찰한 모든 full-burst start에서 `홍련 : 흑영`이었다.

Fast는 기존 lazy target primitive를 재사용하고, 가능한 static B3 후보 전원이 charge cadence-safe일 때만 scorer가 ownership을 인정한다.

캐릭터명 runtime hack은 없다.

## 2. fail-closed safety

이번 checkpoint에서도 broad family는 열지 않았다.

live-ammo proof는 다음에서 철회된다.

- refill이 100%가 아님
- self가 아닌 target
- 다른 event/condition/parameter
- competing live max-ammo provider
- provider가 refill 뒤에 오는 order
- wider flat/infinite max-ammo combination
- recipient weapon cadence unsafe

lazy rank cadence proof는 다음에서 철회된다.

- `LOWEST_ATK_BURST3:1` 외 selector/count
- `charge_speed_caster_based_pct` 외 cadence stat
- non-finite/negative/bullet lifetime shape
- named-state/event consumer collision
- 가능한 B3 후보 중 하나라도 charge unsafe
- 다른 actor의 burst-stage mutation 가능성

기존 broad generic stun/remove/live-reference/multi-stack/weapon-replacement family도 계속 fail closed다.

## 3. current public frontier

canonical filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외
- exact ordered membership dedupe

fresh production audit 결과:

- source cases `24`
- unique memberships `23`
- certified **3**
- gaps **20**

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

직전 Maid Mast lifecycle checkpoint 대비:

- certified `2 → 3`
- gaps `21 → 20`
- cadence `59 → 57`
- normal state `25 → 22`
- 나머지 unchanged

same exact generic shape coverage audit:

lazy B3 charge-speed:

- `스쿼드4`
- `레이드_네온벨벳`
- `레이드_볼륨`

live max-ammo → 100% refill:

- `스쿼드4`
- `레이드_볼륨`

따라서 frontier 감소가 Volume 한 membership에만 국한되지 않는 것은 의도된 generic-shape coverage다.

## 4. validation completed

focused promotion:

- Volume/new cadence contract + existing refill/Maid regressions `33/33` success

production frontier + 180초 score audit:

- frontier `24 source / 23 unique / 3 certified / 20 gaps`
- `레이드_볼륨 score_static_squad()` 180초 완주
- `unsupported=()`
- Fast events `1653`

pre-cleanup canonical CI:

- run `34016205089`
- result: success
- Fast damage `215/215`
- Fast complete discovery `324/324`
- structural performance median `186.61ms`, events `539`
- calculator `137/137` (`1` skip)
- optimizer `374/374`
- bridge `31/31` (`1` skip)
- site `385/385`
- golden `29/29`
- doclint characters `199`, implementation keys `309`, exceptions `18`

performance threshold는 변경하지 않았다.

상세는 `VOLUME_LIVE_AMMO_LAZY_RANK_CHECKPOINT_20260906.md` 참고.

## 5. current phase

계속 **false-supported safety closure → semantics restoration** 단계다.

완료된 주요 restoration:

1. sparse same-timestamp actor transaction
2. lazy dynamic-rank first-read resolution
3. finite named reference-stack capture
4. full-burst conditional permanent passive
5. full-burst-end named self removal dependency first slice
6. roster-static false B1 remover reachability proof
7. exact generic harmful multi-stack decrement
8. Maid Mast reachable stack-3 stun/removal/cadence/burst lifecycle
9. exact same-event live max-ammo → 100% refill transaction
10. exact lazy `LOWEST_ATK_BURST3:1` caster-based charge-speed cadence delivery

여전히 broad fail-closed:

- generic stun/control family
- generic named removers
- permanent/live reference-stack generic semantics
- broad multi-stack / on-attack / hit-count remover families
- unsupported weapon replacement families
- unrelated HP/heal chronology
- generic live max-ammo refill family
- generic dynamic rank cadence family

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 6. 다음 단일 checkpoint

**Little Mermaid producer/mutator/sequential-damage 결합 lifecycle**

원칙:

- 먼저 Moris에서 producer → mutator → sequential damage dependency 전체를 trace
- isolated effect만 보고 blocker를 제거하지 않음
- scorer/runtime/dispatcher가 공유할 compile-time ownership proof를 먼저 정의
- neighboring generic family는 fail closed 유지
- focused + negative regression 후에만 public frontier 재계산

그 다음 후보:

1. Crown `로얄 에타이어 4` normal/skill shared recipient/lifetime semantics
2. frontier pressure 재계산 후 다음 checkpoint 선정

## 7. cleanup / final canonical gate

Volume checkpoint의 temporary probe는 최종 promotion에서 모두 제거한다.

제거 대상:

- `.github/workflows/tmp-volume-probe.yml`
- `.github/tmp_volume_patch.py`

최종 `.github/workflows`는 반드시:

- `ci.yml`
- `pages.yml`

두 파일만 남긴다.

이 handoff commit 뒤 clean HEAD canonical `ci.yml` 전체 gate를 한 번 더 확인한다. 최종 run ID를 다시 문서에 쓰는 doc-only commit loop는 만들지 않는다. 재개 시 branch HEAD와 최신 successful canonical run을 먼저 확인한다.
