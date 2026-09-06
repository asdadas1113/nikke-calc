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
2. `fast_engine/research/CROWN_HEAL_RECEIVED_SHARED_LIFETIME_CHECKPOINT_20260906.md`
3. `fast_engine/research/LITTLE_MERMAID_REPLACEMENT_SQUAD_AMMO_CHECKPOINT_20260906.md`
4. `fast_engine/research/VOLUME_LIVE_AMMO_LAZY_RANK_CHECKPOINT_20260906.md`
5. `fast_engine/research/MAID_MAST_HANGOVER_LIFECYCLE_CHECKPOINT_20260906.md`
6. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`

## 1. latest completed semantic checkpoint

**Crown `로얄 에타이어 4` heal-received recipient/lifetime semantics 완료.**

semantic production commit:

- `be702b01f8230e985fc7301ebc9decc43a6d3e40` — `Fast: own Crown heal-received lifetime and zero-core guard`

public certification target:

- `레이드_아스카루드밀라`

기존 target blocker:

- `normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct`
- `skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct`

둘 다 제거됐다.

### Moris oracle

`로얄 에타이어 4`는 all-allies `atk_dmg_pct +20.99%`, 7초, `heal_received` trigger다.

Crown의 기존 self stack-heal chain은 reachable provider다. 추가로 나가 `우정의 서포트 2`가 `allies_lowest_hp:2` heal provider로 보이지만, patternless full-HP tie에서 Moris actual target resolver는 항상:

- `리틀 머메이드`
- `나가`

를 선택한다. Crown은 first two 밖이므로 이 exact roster에서는 나가 heal이 Crown에게 도달하지 않는다.

### compile-time ownership

Fast는 full-HP rank tie가 변하지 않는다고 명시적으로 증명할 수 있을 때만 exact `LOWEST_HP:N` provider edge를 unreachable로 제외한다.

HP/heal/life 관련 unknown stat, current/max HP mutation, wider target count, external all-allies heal 등은 proof를 철회한다. unreachable provider를 제외한 뒤에도 모든 reachable provider가 기존 owned self stack-heal chain이어야 한다.

따라서 generic external heal/lifesteal family는 열지 않았다.

### normal / skill shared lifetime

기존 timed effect store 하나가 all-allies `atk_dmg_pct` lifetime을 보유하고 `DamageTermResolver`의 normal/skill 두 path가 같은 state를 읽는다.

synthetic refresh contract:

- t=1 activation
- t=2 refresh
- t=8.5 active
- t=9.0 expired
- normal / skill 둘 다 base 대비 `1.2099x`

### zero-core hidden gate

Crown blocker 제거 후 루드밀라 : 윈터 오너의 dynamic weapon + `core_hit_count` guard가 zero-core profile에서도 먼저 발동하는 hidden gate가 드러났다.

explicit `core_px <= 0` 또는 core uptime/effective core rate 0에서는 core-hit event가 구조적으로 unreachable이므로 조기 종료한다. nonzero core에서는 기존 fail-closed guard를 그대로 유지한다.

상세는 `CROWN_HEAL_RECEIVED_SHARED_LIFETIME_CHECKPOINT_20260906.md` 참고.

## 2. fail-closed safety

Crown 신규 proof는 다음에서 철회된다.

- `LOWEST_HP` count가 owner까지 넓어짐
- current/max HP 또는 unknown HP-rank mutation 존재
- provider parameters/conditions/tick/max-trigger 등 exact shape 이탈
- external all-allies heal
- generic lifesteal/reachable external heal
- nonzero core dynamic `core_hit_count`

따라서 Crown `로얄 에타이어 4` blocker는 현재도 다음 public membership에서 남는다.

- `스쿼드1`
- `스쿼드5`
- `레이드_일레그`

이 셋은 `레이드_아스카루드밀라`와 동일한 unreachable-provider proof로 제거할 수 없는 실제 reachable provider/dependency가 있으므로 의도적인 fail closed다.

기존 broad generic weapon-change, stun/remove, live-rank/live-ammo, squad-ammo family도 계속 fail closed다.

## 3. current public frontier

canonical filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외
- exact ordered membership dedupe

fresh production audit:

- source cases `24`
- unique memberships `23`
- certified **5**
- gaps **18**

certified:

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
- weapon change `12`
- cadence `57`
- control `4`
- periodic grid `1`

직전 Little Mermaid checkpoint 대비:

- certified `4 → 5`
- gaps `19 → 18`
- normal delivery `47 → 46`
- skill-state delivery `49 → 48`
- 나머지 unchanged

production 180초 `레이드_아스카루드밀라` audit:

- run `34024061683` / job `101461785941`
- squad total `2294472196.185189`
- events processed `4736`
- unsupported `()`

## 4. validation completed

Crown 관련 focused staged gate:

- `30/30` success

staged full Fast:

- `338/338` success
- RAPI parity unchanged

pre-cleanup canonical CI:

- run `34024177621`
- job `101462096683`
- result: success
- Fast damage `229/229`
- Fast complete discovery `338/338`
- structural performance median `189.93ms`, events `539`
- full-discovery structural median `188.93ms`, events `539`
- RAPI parity reference `236373847.0`, Fast `236465053.42473748`, relative error `0.0003858566668650809`
- calculator `137/137` (`1` skip)
- optimizer `374/374`
- bridge `31/31` (`1` skip)
- site `385/385`
- golden `29/29`
- doclint characters `199`, implementation keys `309`, exceptions `18`

performance threshold는 변경하지 않았다.

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
14. immutable full-HP tie 아래 exact unreachable `LOWEST_HP:N` heal-provider edge proof
15. `heal_received` all-allies timed damage state의 normal/skill shared lifetime ownership
16. zero-core profile에서 structurally unreachable `core_hit_count` early-return

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 6. post-Crown frontier pressure / 다음 단일 checkpoint

fresh pressure audit에서 가장 많이 반복되는 **단일 exact blocker**는:

- `weapon_change:목단:정정당당 승부다!` — **5 public memberships**

이다.

Snow White : Heavy Arms는 actor 단위로 28 blockers가 남지만 여러 cadence/delivery/removal/sequential-damage family의 합계이므로 하나의 primitive로 취급하지 않는다.

다음 단일 checkpoint:

**목단 `정정당당 승부다!` weapon-change lifecycle**

재개 순서:

1. `정정당당 승부다!` blocker가 있는 public membership 5개 전수 수집
2. Moris에서 weapon-change start/end와 변경 무기 cadence를 trace
3. 해당 state를 보는 normal 5-hit additional damage/self-state dependency가 있으면 한 lifecycle graph로 같이 추적
4. scorer/runtime/dispatcher-shared compile-time ownership proof 정의
5. neighboring generic weapon-change family fail-closed negative regression
6. focused gate → full Fast discovery → canonical CI → frontier 재계산

캐릭터명 runtime 분기를 만들지 않고 generic weapon-change를 넓게 열지 않는다.

## 7. cleanup / final canonical gate

Crown checkpoint 종료 시 모든 임시 probe/helper/trigger를 제거한다.

최종 `.github/workflows`는 반드시:

- `ci.yml`
- `pages.yml`

두 파일만 남긴다.

cleanup/docs 뒤 **clean HEAD canonical `ci.yml` 전체 gate를 한 번 더 성공 확인**하고 종료한다. 최종 run ID를 기록하기 위한 추가 doc-only commit은 만들지 않는다. 다음 재개 시 branch HEAD, `master`, 최신 successful clean canonical run을 먼저 확인한다.
