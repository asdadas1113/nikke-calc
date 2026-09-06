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
2. `fast_engine/research/MAID_MAST_HANGOVER_LIFECYCLE_CHECKPOINT_20260906.md`
3. `fast_engine/research/MAID_MAST_GENERIC_STACK_DECREMENT_CHECKPOINT_20260906.md`
4. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
5. `fast_engine/research/FINITE_REFERENCE_STACK_CAPTURE_CHECKPOINT_20260906.md`
6. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`

## 1. latest completed semantic checkpoint

**Maid Mast reachable stack-3 hangover/removal lifecycle 완료.**

semantic production commit:

- `10f9d52a608cc9c68e6f7183d4868d60314c45e2` — `Fast: own Maid Mast hangover lifecycle`

hardening follow-up:

- `85562b38aec8f890b90a4720a1cc6f895f608158` — Moris/finite-reference/negative contract 추가
- `410332448a61c8f20362a5c007ce7bdc1e8825dd` — condition compiler import correction
- `a0a5a65474f036a8a0167033455062b4e045d472` — contract harness correction

public anchors:

- `레이드_루주`
- `레이드_브리드디젤`

Moris oracle에서 첫 reachable hangover:

- 루주: FB end/stun/removal `39.4`, logical stun end `49.4`
- 브리드디젤: `38.4666666667`, logical stun end `48.4666666667`

Moris separate expire log는 다음 observed 60Hz tick에 나오지만 logical active interval은 정확히 `[start,start+10)`이다.

함께 소유한 의미론:

- 3-stack full-burst-end stun 생성
- same-timestamp paired `취기` removal
- source removal 후 finite stun lifetime 독립 유지
- stun 동안 normal shot suppression
- no catch-up shot debt
- MG warmup/ammo/ongoing reload 보존
- burst candidate exclusion / alternate candidate / sparse earliest-unblock wait
- `파이레츠 하트` conditional passive removal sync
- next B1 `취기=1` + passive restart
- finite captured `scaling_ref=취기` consumer lifetime 유지

runtime은 generic control/remove family를 열지 않는다. exact `certified_stack3_self_stun_remove_lifecycles()` proof를 dispatcher, scorer, dynamic rapid selection이 공유한다.

## 2. fail-closed safety

ownership은 다음에서 철회된다.

- duplicate `취기` provider
- competing stack provider/mutator
- 다른 stun provider
- `stun_immune`
- named/state-end consumer collision
- ambiguous/unsupported target 또는 condition
- unsupported weapon/control shape
- standalone stun/remove family

캐릭터명 runtime hack은 없다.

## 3. current public frontier

canonical filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외
- exact ordered membership dedupe

fresh audit run:

- `34006920000`
- job `101415740830`

결과:

- source cases `24`
- unique memberships `23`
- certified **2**
- gaps **21**

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

직전 checkpoint에서 `normal_state 27 → 25`만 변했다. Anchor-free `레이드_루주`, `레이드_브리드디젤`의 `파이레츠 스피릿 3:remove_named_buff` blocker 2개가 정확히 제거됐다. certified가 2로 유지되는 것은 정상이다.

`레이드_볼륨`의 남은 blockers는 정확히:

- `cadence:홍련 : 흑영:화무십일홍 · 수라 2:ammo_charge_pct`
- `normal_state:리버렐리오:차분한 수심 4:rank_target_timing`

## 4. validation already completed

Moris lifecycle trace:

- 루주/브리드디젤 activation/removal/expiry semantics 확인
- `[start,end)` normal shot 0 확인
- next B1 restart 확인

focused production lifecycle regression:

- semantic promotion 과정에서 existing Maid Mast stack-mutation + new lifecycle suite 모두 success

hardening contract:

- run `34006869114`
- job `101415603964`
- `5/5` success

public frontier:

- run `34006920000`
- job `101415740830`
- `source24 / unique23 / certified2 / normal_state25`

상세는 `MAID_MAST_HANGOVER_LIFECYCLE_CHECKPOINT_20260906.md` 참고.

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

여전히 broad fail-closed:

- generic stun/control family
- generic named removers
- permanent/live reference-stack generic semantics
- broad multi-stack / on-attack / hit-count remover families
- unsupported weapon replacement families
- unrelated HP/heal chronology

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 6. 다음 단일 checkpoint

**`레이드_볼륨` certification attempt**

두 root cause를 하나씩 Moris로 검증한다.

1. `홍련 : 흑영 / 화무십일홍 · 수라 2 / ammo_charge_pct`
2. `리버렐리오 / 차분한 수심 4 / rank_target_timing`

규칙:

- 두 의미론을 각각 독립 trace/audit
- 한 mechanic을 다른 mechanic 편법으로 열지 않음
- 둘 다 안전하게 닫힌 뒤에만 세 번째 certified membership 여부 판단

그 다음:

1. Little Mermaid producer/mutator/sequential-damage 결합 lifecycle
2. Crown `로얄 에타이어 4` normal/skill shared recipient/lifetime semantics
3. frontier pressure 재계산 후 다음 단일 checkpoint 선정

## 7. cleanup / final canonical gate

이번 Maid Mast checkpoint의 temporary probe/workflow는 clean promotion commit에서 전부 제거한다.

최종 `.github/workflows`는 반드시:

- `ci.yml`
- `pages.yml`

두 파일만 남긴다.

이 handoff 작성 시점에는 semantic/focused/frontier 검증까지 완료됐다. clean HEAD canonical `ci.yml` 전체 gate는 cleanup/docs promotion 후 확인하고, 다음 재개 시 그 clean HEAD/run을 기준으로 사용한다.
