# Fast Engine 작업 인계 — 2026-09-06

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260906.md`
2. `fast_engine/research/MAID_MAST_GENERIC_STACK_DECREMENT_CHECKPOINT_20260906.md`
3. `fast_engine/research/ROSTER_STATIC_NAMED_REMOVE_CHECKPOINT_20260906.md`
4. `fast_engine/research/PRODUCER_MUTATOR_DEPENDENCY_CHECKPOINT_20260906.md`
5. `fast_engine/research/FULL_BURST_CONDITIONAL_PERMANENT_PASSIVE_CHECKPOINT_20260906.md`
6. `fast_engine/research/FINITE_REFERENCE_STACK_CAPTURE_CHECKPOINT_20260906.md`
7. `fast_engine/research/LAZY_DYNAMIC_RANK_TARGET_CHECKPOINT_20260906.md`
8. `fast_engine/research/SPARSE_SAME_TIMESTAMP_ACTOR_TRANSACTION_CHECKPOINT_20260906.md`
9. `fast_engine/research/FALSE_SUPPORTED_SAFETY_REPAIR_CHECKPOINT_20260906.md`
10. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`

## 1. 현재 production 상태

latest semantic production commit:

- `608fe036ed836a35e25736ea9d967bff106af972` — exact generic harmful multi-stack decrement ownership

semantic 후 stale regression expectation 정리:

- `cb00449d74ef5580444a11657029fefc8c617174` — finite-reference public Maid Mast assertion을 새 ownership에 맞게 갱신

직전 semantics restoration:

- `969b75c4ade19c8e2eea1951f38c5d76df4ced62` — roster-static false B1 named-removal reachability proof
- `804cc1eff5ea4c2eac61e68771f8d17c174cb930` — full-burst-end named self removal dependency ownership
- `7df61bd3853cca202808a43d2d155a38a36df450` — full-burst conditional permanent passive ownership
- `2184b253ab22969fff63bc9a95b44aa8a6fc49d9` — finite reference-stack capture ownership
- `cc11c5c08d907001ab6e7841c05da7f3179afa67` — lazy dynamic-rank first-read target ownership
- `0351fb40bd7faae5c62697c22588239b4c6868d4` — sparse same-timestamp actor transaction ownership

직전 safety commits:

- `438eef65426d1ed9e17b871db7cd74e334c8e921` — cross-actor post-shot ordering fail-closed
- `aadfde37ad7be708f6b3d3312ff828844a8a391a` — unsafe dynamic-rank timing fail-closed
- `4c11c2dd4317393c3220b6f0957e12e34e3b6502` — scored-state remover dependency fail-closed

safety guard는 실제 semantics 또는 reachability가 증명된 narrow shape에서만 철회한다.

## 2. 최신 완료 — Maid Mast / Anchor generic harmful-stack decrement

public Maid Mast membership은 5개다.

Anchor 포함:

- `스쿼드4`
- `레이드_앨리스브래디`
- `레이드_볼륨`

Anchor 없음:

- `레이드_루주`
- `레이드_브리드디젤`

`취기`는:

- harmful self `accuracy_pct -20`
- permanent
- max stack 3
- `burst_enter:1`마다 stack 증가

Fast에서 accuracy는 실제 core-hit probability에 사용되므로 stack mismatch는 score mismatch다.

Anchor `불가사리(모양) 오므라이스 3`은:

- instant `debuff_stack_remove`
- all allies
- value 1
- `full_burst_start_count:3`

Moris의 target-less generic decrement는 selected cohort의 active harmful `max_stack > 1` buff를 1 stack 줄이되 minimum 1을 유지한다.

public Anchor+Maid Mast 3조합에서는 이 operation의 possible harmful multi-stack provider가 `취기` 하나뿐이다.

Moris owner-order trace:

- B1 #1 `취기=1`
- B1 #2 `취기=2`
- B1 #3 `취기=3`
- third full-burst start에서 Anchor owner notify 시 정확히 `3 → 2`
- 이후 `2 → 3 → 2` 반복
- full-burst end의 `self_stack_at_least:취기:3` branch는 도달 불가능

Fast patch 전에는 Anchor mutator가 미소유라 stack 3이 그대로 남았다.

production 구현:

### `effects.py`

`decrement_harmful_stackable()` 추가:

- active harmful multi-stack only
- minimum 1 stack
- live reference/state generation 갱신

### `dispatcher.py`

`_generic_allies_harmful_stack_decrement_provider()` 추가.

지원은 다음 exact slice만:

- mutator: all-allies, value 1, no params/condition, `AT_LEAST full_burst_start >=3`
- target cohort 전체 squad
- overlapping harmful multi-stack provider 정확히 하나
- provider: permanent self negative `accuracy_pct`, max stack 3, `burst_enter:1`, globally unique name
- provider 자체 direct-damage runtime shape supported

기존 owner-order full-burst signal broadcast를 사용하므로 global 60Hz loop는 추가하지 않았다.

### `score.py`

`_full_burst_end_stack_condition_unreachable_after_owned_decrement()` 추가.

Anchor decrement로 full-burst end stack 3이 불가능한 exact roster에서만 Maid Mast remover blocker를 제거한다.

`레이드_앨리스브래디`의 아니스 : 스타 `reenter1` effect는 존재하지만 이전 checkpoint의 roster-static B1 proof로 unreachable임이 증명되므로 current proof를 깨지 않는다.

또 `_unsupported_generic_harmful_stack_remove_changes_scored_state()`를 추가했다. 앞으로 exact owned slice가 아닌 target-less generic harmful-stack mutator가 scored multi-stack state를 건드릴 수 있으면 `normal_state:*:debuff_stack_remove`로 fail-closed한다.

상세:

- `fast_engine/research/MAID_MAST_GENERIC_STACK_DECREMENT_CHECKPOINT_20260906.md`

## 3. 아직 열지 않은 Maid Mast path

Anchor 없는:

- `레이드_루주`
- `레이드_브리드디젤`

에서는 Moris에서 실제로:

- `취기` 3 stack이 full-burst end까지 유지
- `숙취` self stun 10초 발동
- `파이레츠 스피릿 3`이 `취기` 제거

Moris timeline에서 stun은 normal shot을 막고 burst candidate에서도 actor를 제외한다.

따라서 remover만 executable로 만들어서는 안 된다. 이 두 public membership의 remover blocker는 계속 유지한다.

## 4. 현재 public frontier

canonical frontier filter:

- `지그_*` source 제외
- 5인 squad
- `test_*` fixture member 제외

latest semantic/test follow-up 기준:

- source cases: `24`
- unique ordered memberships: `23`
- certified: **2**
- gaps: **21**

certified:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

fresh blocker families:

- normal delivery `47`
- normal state `27`
- skill damage `27`
- skill-state delivery `49`
- weapon change `12`
- cadence `59`
- control `4`
- periodic grid `1`

직전 checkpoint 대비:

- normal state `30 → 27`
- 나머지 unchanged
- certified `2 → 2`

사라진 blocker는 Anchor가 함께 있는 3 unique membership의:

`normal_state:마스트 : 로망틱 메이드:파이레츠 스피릿 3:remove_named_buff`

뿐이다.

Anchor 없는 두 membership에서는 같은 blocker가 그대로 남는다.

## 5. 검증

Moris B1/full-burst owner-order trace:

- run `33998405802`
- job `101392837742`

Fast pre-patch divergence probe:

- run `33998638029`
- job `101393436211`

Anchor harmful multi-stack public scope audit:

- run `33998726345`
- job `101393669878`

focused semantic promotion:

- run `33998899663`
- job `101394128608`
- focused regressions success
- semantic commit `608fe036ed836a35e25736ea9d967bff106af972`

public/full promotion after stale-test update:

- run `33999094106`
- job `101394640976`
- frontier exact assertion success
- Fast complete discovery **303/303**
- structural median `124.84 ms`
- samples `[124.78, 166.3, 124.84]`
- events `539`
- RHQ relative error `0.0003858566668650809` (~`+0.0386%`)

## 6. 현재 phase

현재는 **false-supported safety closure → semantics restoration**을 계속한다.

복구 완료:

1. sparse same-timestamp actor transaction
2. lazy dynamic-rank first-read resolution
3. finite named reference-stack capture
4. full-burst conditional permanent ATK passive
5. globally-unambiguous permanent self provider → full-burst-end remover first slice
6. roster-static false B1 remover score reachability proof
7. exact generic harmful multi-stack decrement + resulting stack-3 remover unreachability proof

아직 fail-closed:

1. Maid Mast Anchor-free reachable `숙취` + `파이레츠 스피릿 3` lifecycle
2. 기타 reachable conditional named removers
3. permanent/live reference-stack generic semantics
4. `not_during_full_burst` 및 non-ATK permanent passive
5. Dorothy `광익 3:accuracy_pct`
6. Tove `임시 개조` 같은 unowned providers
7. broad multi-stack / on-attack / hit-count remover families
8. Arcana `추억 남기기` state-machine dependency family
9. generic stun/control cadence semantics

raw coverage expansion이나 optimizer production integration으로 돌아가지 않는다.

## 7. 다음 단일 체크포인트

**Maid Mast reachable stack-3 hangover/removal lifecycle**

첫 public anchors:

- `레이드_루주`
- `레이드_브리드디젤`

먼저 확인할 것:

1. `숙취` self stun의 exact 10초 lifecycle
2. full-burst end 같은 timestamp에서 `숙취`와 `파이레츠 스피릿 3` effect ordering
3. stun 동안 normal-shot suppression
4. stun 동안 burst candidate exclusion
5. `취기` removal 후 stun 지속 독립성
6. 다음 cycle B1/B2 선택에 미치는 영향
7. exact Maid Mast slice만 sparse하게 소유하고 generic stun family는 계속 fail-closed할 수 있는지

remover가 executable이라는 이유만으로 열지 않는다. shot cadence와 burst planning까지 Moris와 일치해야 한다.

## 8. 작업공간 cleanup

이번 checkpoint 종료 commit에서 다음 temporary 파일을 모두 제거한다.

- `.github/workflows/tmp-maid-mast-multistack-audit.yml`
- `fast_engine/research/tmp_maid_mast_multistack_audit.py`
- `fast_engine/research/tmp_maid_mast_b1_trace.py`
- `fast_engine/research/tmp_maid_mast_fast_probe.py`
- `fast_engine/research/tmp_anchor_harmful_stack_scope.py`
- `fast_engine/research/tmp_patch_maid_mast_stack.py`
- `fast_engine/research/tmp_debug_maid_mast_unreachable.py`
- `fast_engine/research/tmp_fix_maid_mast_stack_patch.py`
- `fast_engine/research/tmp_maid_mast_promotion.py`

최종 clean `.github/workflows`는 다시:

- `ci.yml`
- `pages.yml`

만 남겨야 한다.

- branch: `fast-engine-phase2-20260901`
- latest semantic production: `608fe036ed836a35e25736ea9d967bff106af972`
- master: `fb2fd9157aa14499daf6b9f185beb685d4393f90`

이 docs/cleanup commit의 clean HEAD에서 canonical `ci.yml` 전체 gate를 최종 확인한다.
