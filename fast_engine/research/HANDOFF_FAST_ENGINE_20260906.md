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
2. `fast_engine/research/LITTLE_MERMAID_REPLACEMENT_SQUAD_AMMO_CHECKPOINT_20260906.md`
3. `fast_engine/research/VOLUME_LIVE_AMMO_LAZY_RANK_CHECKPOINT_20260906.md`
4. `fast_engine/research/MAID_MAST_HANGOVER_LIFECYCLE_CHECKPOINT_20260906.md`
5. `fast_engine/research/MAID_MAST_GENERIC_STACK_DECREMENT_CHECKPOINT_20260906.md`
6. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
7. `fast_engine/research/FINITE_REFERENCE_STACK_CAPTURE_CHECKPOINT_20260906.md`
8. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`

## 1. latest completed semantic checkpoint

**Little Mermaid enemy replacement + global squad-ammo sequential-damage lifecycle 완료.**

semantic production commit:

- `ab3243ac3a83b3b0e7526b3a5f3b2d51e0c7c019` — `Fast: own Little Mermaid replacement and squad-ammo lifecycle`

public certification target:

- `레이드_델타`

기존 마지막 두 blocker:

- `normal_state:리틀 머메이드:터진 거품 3:remove_named_buff`
- `skill_damage:리틀 머메이드:거품 난사:sequential_damage:10`

둘 다 제거됐다.

### enemy replacement ownership

Moris trace에서 Little Mermaid 50번째 hit는 `2.05s`다.

같은 timestamp에서:

1. `터진 거품` received-damage replacement 생성
2. finite enemy stun sibling 생성
3. 원본 `거품` 제거

Fast는 source/replacement/control/remover의 exact actor-order graph, 동일 hit gate, 동일 target-state dependency, 외부 observer 부재를 compile-time에서 증명할 때만 remover를 실행한다. generic stun/remove family는 열지 않았다.

### global squad-ammo ownership

Moris `레이드_델타` crossings:

- 500발 `4.133333333333324s`
- 1000발 `6.033333333333317s`
- 1500발 `7.93333333333331s`

각 crossing에서 `거품 난사`는 exact 10 hit이며, `ammo 감소 → squad_ammo signal/skill damage → crossing normal shot damage` 순서다.

Fast는 전원 certified non-clip rapid인 squad에서만 다음 global modulo crossing 하나를 sparse하게 예측한다. 모든 shot을 scheduler event로 만들지 않는다.

### rapid nominal-deadline correction

첫 staged path는 24/s SMG 50번째 hit를 `2.041666...s`로 냈다. Moris는 명목 `next_fire_time`을 누적하고 실제 발사는 첫 60Hz 관찰 tick에서 하므로 `2.05s`다.

Fast는 이 exact squad-ammo slice에만 nominal `fire_deadline`을 보존하고 기존 `moris_observed_tick()`으로 의미 있는 boundary만 snap한다. global 60Hz loop는 추가하지 않았다.

## 2. fail-closed safety

Little Mermaid replacement proof는 다음에서 철회된다.

- source/replacement value 또는 polarity 불일치
- source/replacement/control/remover actor order 변경
- 서로 다른 hit-count threshold
- source named-state gate 불일치
- remover target name ambiguity
- 외부 named-state mutator/observer
- `target_stunned` consumer
- 관련 state-end consumer

`squad_ammo_consume` proof는 다음에서 철회된다.

- squad actor 중 하나라도 certified rapid runtime 밖
- clip/charge/unsupported fire mode 혼합
- weapon control 존재
- infinite ammo 가능성
- non-NOP squad-ammo consumer가 둘 이상
- exact fixed `sequential_damage:N` / 단일 modulo trigger가 아님
- trigger-count reduction 개입

따라서 `레이드_일레그`의 `squad_ammo_consume:100` family는 계속 fail closed다.

기존 broad generic stun/remove/reference-stack/weapon-replacement/live-rank/live-ammo family도 계속 fail closed다.

## 3. current public frontier

canonical filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외
- exact ordered membership dedupe

fresh production audit:

- source cases `24`
- unique memberships `23`
- certified **4**
- gaps **19**

certified:

- `레이드_레드후드퀀시`
- `레이드_델타`
- `레이드_볼륨`
- `컨트롤_미란다미하라`

blocker families:

- normal delivery `47`
- normal state `16`
- skill damage `25`
- skill-state delivery `49`
- weapon change `12`
- cadence `57`
- control `4`
- periodic grid `1`

직전 Volume checkpoint 대비:

- certified `3 → 4`
- gaps `20 → 19`
- normal state `22 → 16`
- skill damage `27 → 25`
- 나머지 unchanged

## 4. validation completed

신규 Little Mermaid contract 6개를 포함한 focused promotion:

- `26/26` success

staged full Fast:

- `330/330` success
- performance median `132.59ms`, events `539`
- RAPI parity unchanged

pre-cleanup canonical CI:

- run `34020420109`
- job `101451859865`
- result: success
- Fast damage `221/221`
- Fast complete discovery `330/330`
- structural performance median `167.08ms`, events `539`
- calculator `137/137` (`1` skip)
- optimizer `374/374`
- bridge `31/31` (`1` skip)
- site `385/385`
- golden `29/29`
- doclint characters `199`, implementation keys `309`, exceptions `18`

performance threshold는 변경하지 않았다.

상세는 `LITTLE_MERMAID_REPLACEMENT_SQUAD_AMMO_CHECKPOINT_20260906.md` 참고.

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
11. exact enemy received-damage replacement/remover lifecycle
12. all-certified-rapid global ammo modulo → sequential-damage pre-shot lifecycle
13. rapid nominal fire-deadline → sparse Moris tick observation for that exact slice

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 6. 다음 단일 checkpoint

**Crown `로얄 에타이어 4` normal/skill shared recipient/lifetime semantics**

재개 순서:

1. Crown public memberships와 exact blocker 전수 수집
2. Moris에서 `로얄 에타이어 4` recipient 선택 시각과 lifetime을 trace
3. normal attack과 skill damage가 같은 recipient/lifetime state를 실제로 공유하는지 확인
4. scorer/runtime/dispatcher 공용 compile-time ownership proof 정의
5. neighboring target/lifetime family fail-closed negative regression
6. focused gate → full Fast discovery → canonical CI → frontier

Little Mermaid나 다른 coverage를 동시에 넓히지 않는다.

## 7. cleanup / final canonical gate

Little Mermaid 임시 probe/helper/trigger는 이 handoff와 함께 모두 제거한다.

최종 `.github/workflows`는 반드시:

- `ci.yml`
- `pages.yml`

두 파일만 남긴다.

이 cleanup/docs commit 뒤 clean HEAD canonical `ci.yml` 전체 gate를 한 번 더 확인한다. 최종 run ID를 다시 문서에 쓰는 doc-only commit loop는 만들지 않는다. 재개 시 branch HEAD와 최신 successful canonical run을 먼저 확인한다.
