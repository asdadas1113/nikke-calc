# Fast Engine 작업 인계 — 2026-09-05

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md`
2. `fast_engine/research/PATTERNLESS_SQUAD_PART_HIT_CHECKPOINT_20260905.md`
3. `fast_engine/research/PERIODIC_ENEMY_RECEIVED_DAMAGE_CHECKPOINT_20260905.md`
3. `fast_engine/research/STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md`
3. `fast_engine/research/FULL_CHARGE_HIT_CHARGE_SPEED_CHECKPOINT_20260905.md`
4. `fast_engine/research/PERIODIC_FINITE_SELF_CRIT_CHECKPOINT_20260905.md`
5. `fast_engine/research/TOVE_AMMO_PCT_NAMED_EVENT_CHECKPOINT_20260905.md`
6. `fast_engine/research/ADA_CHARGE_HOLD_CONTROL_CHECKPOINT_20260905.md`
7. `fast_engine/research/ADA_ONE_SHOT_CHARGE_SPEED_CHECKPOINT_20260905.md`
8. `fast_engine/research/PATTERNLESS_ENCOUNTER_EVENT_CHECKPOINT_20260905.md`
9. `fast_engine/research/COVERAGE_FRONTIER_CHECKPOINT_20260904.md`
10. `fast_engine/research/CROWN_SELF_STACK_HEAL_CHECKPOINT_20260904.md`
11. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`

현재 최신 production semantic commit:

- `745d9f1afcf10d092bb58bf9e0235724a5c41946` — patternless `squad_part_hit` blocker hygiene

직전 production semantic commit:

- `37a7da91974222ab49bb0ef6b869d06a34100a4d` — post-shot `full_charge_hit` next-bullet lifetime delivery

직전 주요 semantic commit:

- `4a6cbe388cd0ef32ec07e5b825078fe457619181` — fixed-grid periodic enemy `received_dmg_pct` certification
- `8880049678c9270de8d7b98c456b93fa00a67502` — recipient-scoped `stat_applied` finite self `charge_speed_pct` certification

직전 주요 production commits:

- `73145b1862ce474bd78a5674916cfd7ec6a05f1e` — pure charge `own_full_burst` hold ownership
- `f70871e36ddf28a2474e7e25d6d7254cf9fe26cd` — Ada one-shot charge-speed lifetime
- `4c78a27f024074a9e19391efc3d4ed6125c2d667` — patternless unreachable encounter-event blocker 제거
- `68d8dea58e4b05a630fc1d6545dcb905a7c7cfa8` — finite self-state-end + enemy named-stack damage/remove
- `6a4c8346062eb3284ae34558d93675184b4ab154` — Crown self-stack heal-received bridge
- `46af96866b9462ec22455b9c9f5121cfa3b35bdd` — last-bullet damage delivery
- `0f522925b2cac86ab74329a9ce4d02347f739abe` — Moris outer-tick timing alignment

---

## 0A. 최신 완료 — patternless `squad_part_hit` blocker hygiene

D : 킬러 와이프 `타겟 섬멸 코어`를 anchor로, 표준 patternless enemy에서 도달 불가능한 `squad_part_hit` consumer를 comparison-critical blocker에서만 제외했다.

production:

- `745d9f1afcf10d092bb58bf9e0235724a5c41946`

중요한 경계:

- runtime `squad_part_hit` ownership을 추가한 것이 아니다.
- 해당 effect는 dispatcher executable로 승격하지 않았다.
- global `squad_body_hit`은 계속 fail closed다.

Moris A/B (`33942161302 / 101241562693`):

- 기본 enemy `has_parts=False`: `타겟 섬멸 코어` activation `0`
- 같은 enemy에 `has_parts=True`: activation `349`
- public delta는 D part-hit normal/skill blocker 정확히 2개만 제거
- added blocker 없음
- Fast damage `158/158`

promotion (`33942326300 / 101242018963`):

- focused `4/4`
- Fast damage `159/159`
- public `23 unique / 2 certified / 21 gaps`
- `레이드_미하라에이다` `8 -> 6` blockers

상세:

- `fast_engine/research/PATTERNLESS_SQUAD_PART_HIT_CHECKPOINT_20260905.md`

---

## 0B. 직전 완료 — post-shot full-charge next-bullet lifetime

D : 킬러 와이프 `캄 스나이핑`의 `full_charge_hit:3 -> duration_bullets:1`을 generic post-shot next-bullet lifetime으로 좁게 열었다.

production logic:

- `37a7da91974222ab49bb0ef6b869d06a34100a4d`

permanent regression:

- `968b2a83cef745d612759dbc31af5db5c34f8c72`

Moris/Fast probe에서 activation은 `3.80s`, `8.00s`로 일치했고 Fast의 lifetime 제거는 각각 다음 탄 `5.20s`, `9.3833s`에서 일어났다. triggering shot 자체에는 적용되지 않는다.

post-patch frontier에서 D `캄 스나이핑` blocker 1개만 제거됐고 `normal_delivery 43 -> 42`, 다른 family는 변하지 않았다.

---

## 1. 현재 phase / public accounting

현재는 **coverage expansion** 단계다.

Fast-certified real public memberships:

- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

표준 public accounting:

- source cases: `24`
- unique ordered memberships: `23`
- certified: `2`
- coverage gaps: `21`

latest standardized public ranking은 Helm periodic enemy candidate gate에서 실제 재실행했고 certified universe는 여전히 2개다.

- clean relative error median: `+0.0626832%`
- min: `+0.0349533%`
- max: `+0.0904131%`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`

Helm periodic enemy gate run `33932690769`에서 ranking probe를 재실행했고 certified universe는 이후에도 2개로 유지됐다. 최신 fresh frontier는 cadence `63`, normal delivery `41`, skill-state delivery `43`, skill damage `27`, weapon change `12`, normal state `7`, control `6`, periodic grid `1`이다.

optimizer production integration은 아직 하지 않는다.

---

## 1A. 최신 완료 — periodic enemy received damage

Helm : Aquamarine `이지스 캐논 견제 사격 2`를 anchor로 fixed-grid finite enemy `received_dmg_pct` stack을 좁게 generic certification했다.

production:

- `4a6cbe388cd0ef32ec07e5b825078fe457619181`

새 periodic scheduler는 만들지 않았다. 기존 Moris-observed fixed periodic scheduler, enemy ActiveEffectStore, DamageTermResolver를 재사용한다. 전격 enemy에서 4초 periodic activation 6회와 stack/value가 Moris와 exact match했고, 작열 enemy에서는 양쪽 모두 0회였다.

A/B run `33932690769` / job `101214374980`:

- focused `21/21`
- full Fast `262/262`
- standardized ranking probe success
- normal delivery `44 -> 43`
- skill-state delivery `45 -> 44`

promotion run `33932866252` / job `101214901667`:

- focused success
- full Fast `262/262`
- diff whitelist success
- production commit/push success

Ada `effect_interval`은 dynamic periodic deadline rescheduling 문제라 계속 fail closed다. Neon `초화력`은 gauge chronology가 필요해 보류한다.

상세:

- `fast_engine/research/PERIODIC_ENEMY_RECEIVED_DAMAGE_CHECKPOINT_20260905.md`

---

## 1B. 직전 완료 — recipient stat-applied charge speed

Brady `나누고 싶은 맛`을 anchor로 recipient-scoped `event:stat_applied:split_dmg_pct` 뒤 finite self `charge_speed_pct`를 좁게 generic certification했다.

production:

- `8880049678c9270de8d7b98c456b93fa00a67502`

Moris는 `dot_dmg_pct`/`split_dmg_pct` buff가 실제 ally recipient에게 적용된 직후 같은 시각 recipient-scoped `stat_applied` event를 notify한다. Fast도 기존 actor-scoped dispatcher를 재사용하며, source provider가 해당 recipient에게 실제로 도달 가능하고 모든 가능한 source가 executable임을 별도 proof한다.

public `레이드_앨리스브래디`에서는 split provider가 있고 dot provider가 없으므로 `not_self_state:머물고 싶은 맛`을 immutable true로 증명할 수 있다. synthetic opposite source를 추가하면 즉시 fail closed한다. Brady의 dot branch와 두 opposing remove effect는 계속 닫혀 있다.

A/B run `33929600782` / job `101205337651`:

- Fast/Moris split activation 5개 시각 exact match
- focused success
- full Fast `254/254`
- standardized ranking probe success
- cadence blocker family `64 -> 63`

production promotion run `33929914438` / job `101206236343`:

- focused production `33/33`
- full Fast `258/258`
- production diff whitelist success
- production commit/push success

상세:

- `fast_engine/research/STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md`

---

## 1C. 그 이전 완료 — full-charge-hit self charge speed

신데렐라 `무결한 유리 2`를 anchor로 raw `full_charge_hit` 뒤 영구 self `charge_speed_pct`를 좁게 generic certification했다.

production:

- `721cd9a8720766c14a814eb8973ca5cd685d7c73`

새 global shot loop를 만들지 않았다. 기존 dynamic charge runtime의 물리 shot boundary를 재사용하며 ordering은 `shot/score -> full_charge_hit -> effect activation -> cadence sync`다.

A/B run `33924314982` / job `101189364921`에서 Moris와 Fast activation sequence가 직접 일치했다. 첫 shot은 약 `1.0s`, 이후 +100% charge speed 활성화 뒤 간격은 약 `0.333333s`다.

production promotion run `33924481342` / job `101189880430`:

- focused new regression `3/3`
- existing one-shot charge-speed `6/6`
- public scope success
- full Fast `254/254`
- production commit/push success

public cadence blocker family는 `66 -> 64`, accounting은 `23 unique / 2 certified / 21 gaps`로 유지됐다. 따라서 ranking probe는 재실행하지 않았다.

상세:

- `fast_engine/research/FULL_CHARGE_HIT_CHARGE_SPEED_CHECKPOINT_20260905.md`

---

## 1D. 그 이전 완료 — finite periodic self crit

스노우 화이트 `세븐스 드워프 : V&VI 2`를 anchor로 fixed-grid finite self `crit_rate` periodic state를 좁게 generic certification했다.

production:

- `fee2fe343cf75861185dd780d9191bbf6f48da8f`

지원 shape는 self / beneficial `crit_rate` / finite duration / one stack / exactly one `during_full_burst` condition / exactly one fixed periodic trigger다. 기존 periodic scheduler와 ActiveEffectStore를 재사용하며 새 frame loop를 만들지 않았다.

Moris 70s trace의 successful activation 3개와 Fast가 정확히 같은 outer-tick 시각을 냈다: `30.016666666666243`, `45.016666666665394`, `60.01666666666454`.

runner-only A/B run `33922544009` / job `101183863415`:

- focused `3/3`
- existing periodic `8/8`
- full Fast `251/251`
- public helper match exactly one effect
- public `23 unique / 2 certified / 21 gaps`

promotion run `33922753827` / job `101184510974`도 focused / public scope / full Fast / commit 모두 success.

제거된 blocker는 `레이드_헬름아쿠아스노우`의 Snow White periodic crit normal/skill delivery 2개뿐이다. Helm Aqua periodic enemy state와 Snow White weapon-change/pierce blocker는 그대로 남겼다.

상세:

- `fast_engine/research/PERIODIC_FINITE_SELF_CRIT_CHECKPOINT_20260905.md`

---

## 2. 최신 완료 — percent-ammo instant named event

토브 `급조 탄환 -> 임시 개조 2`에서 작은 generic gap을 닫았다.

실제 shape:

- provider `급조 탄환`: `instant / ammo_charge_pct`, self, reducible `hit_count:10`
- consumer `임시 개조 2`: `buff / crit_dmg +5.24`, all allies, 5s, `event:급조 탄환`

Moris의 `handle_ammo_charge_pct`는 refill 성공 뒤 `event:{effect.name}`을 같은 caster로 notify한다. 반면 `ammo_charge_flat` handler에는 이 notify가 없다.

따라서 Fast도 정확히 다음만 지원한다.

- 성공한 `ammo_charge_pct` instant의 named-event emission
- same-actor, executable, non-negative pct provider를 named-event source로 runtime/score에서 증명
- consumer는 direct-damage-runtime-supported buff로 제한

`ammo_charge_flat` named provider는 계속 fail closed다. flat까지 넓히면 Moris 의미론과 달라진다.

production:

- `47e8c47278bbd9125b42a8f08bde632638796026`

permanent regression:

- `fast_engine/tests/test_damage_ammo_pct_named_event.py`
- `fast_engine/tests/test_named_buff_event_runtime.py` Tove expectation 갱신

runner-only A/B:

- run `33912561440`
- job `101152127477`
- focused `16/16`
- full Fast `248/248`

post-promotion validation:

- HEAD `d21c68517f83dee638d8ca566291534e1c23712f`
- run `33912764211`
- job `101152802424`
- focused `16/16`
- full Fast `248/248`
- public `23 unique / 2 certified / 21 gaps`

제거된 public blockers (`레이드_소다`, `스쿼드3`):

- `normal_delivery:토브:임시 개조 2:crit_dmg`
- `skill_state_delivery:토브:임시 개조 2:crit_dmg`

다음 Tove cadence blockers는 의도적으로 남아 있다.

- `cadence:토브:급조 탄환:ammo_charge_pct`
- `cadence:토브:임시 개조:max_ammo_flat`
- `cadence:토브:개조 성공 2:attack_speed_pct`

즉 named-event delivery와 provider cadence certification을 섞지 않았다.

첫 cleanup HEAD `c7e55390cb8c9385e37e8237cd3d08d0a1ccb127`의 canonical CI run `33913173810`은 workflow 전체, bridge `31`, site `385`, golden `29/29`까지 통과했다. 다만 CI가 Fast damage를 `test_damage*.py`로 선택 실행하므로 당시 이름 `test_ammo_pct_named_event.py`는 canonical Fast 단계에 직접 포함되지 않는 것을 마지막 점검에서 발견했다.

A/B와 post-promotion full Fast suite에서는 이미 새 3개 regression을 실행했으므로 기능 검증 실패는 아니었다. CI 계약을 완결하기 위해 테스트 내용은 그대로 두고 파일명을 `test_damage_ammo_pct_named_event.py`로 옮겼다.

rename 이후 HEAD `c733e810795ebb14046bda87ebdf30a698428187`의 canonical CI run `33913678178`에서 `Fast — damage`는 **141 tests**를 실행해 기존 138개 + 새 3개 regression이 실제 discovery되는 것을 확인했고 전부 통과했다. 같은 run에서 calculator 137 tests(1 skip), optimizer 374 tests, bridge 31 tests(1 skip), site 385 tests, golden snapshot 29/29도 모두 통과했다.

상세:

- `fast_engine/research/TOVE_AMMO_PCT_NAMED_EVENT_CHECKPOINT_20260905.md`

---

## 3. 미하라 control 진단 — no patch

`컨트롤_미란다미하라`와 `레이드_미하라에이다`의 `미하라 : 본딩 체인` weapon/control 자체는 동일하다.

team-dependent safety 차이는 D : 킬러 와이프 `타겟 섬멸 ATK`에서 나온다.

- stat: `atk_caster_based_pct`
- value: `12.19`
- duration: `10s`
- target: `self`
- condition: `target_state:타겟 섬멸`
- trigger: `body_hit_count:1` -> `squad_body_hit`

Moris `notify_team_hit()`은 스쿼드 어느 아군이 본체를 명중해도 consumer를 확인하고, activation caster를 실제 attacker로 넘긴다. 따라서 target `self`는 D가 아니라 그 공격자를 뜻한다.

기본 `enemy.has_parts=False`에서는 비코어 본체 명중마다 이 chronology가 발생한다.

결론:

- 미하라 control blocker를 단순 완화하면 오답이다.
- executable global `squad_body_hit` consumer는 기존 rapid score fail-closed를 유지한다.
- `레이드_미하라에이다`의 `control:미하라 : 본딩 체인`은 정상적인 coverage gap이다.

---

## 4. 직전 완료 — Ada charge ownership

Ada 이름 특례 없이 pure charge `own_full_burst` hold를 좁게 generic certification했다.

production:

- `73145b1862ce474bd78a5674916cfd7ec6a05f1e`

지원 shape:

- charge weapon
- non-clip
- control의 유일한 key가 `hold`
- `hold.policy == own_full_burst`
- optional non-negative `lead`

mixed control은 계속 fail closed다.

Ada 두 public team에서 Ada 자체 blocker는 모두 제거됐지만 다른 blocker 때문에 certified count는 증가하지 않았다.

상세:

- `fast_engine/research/ADA_CHARGE_HOLD_CONTROL_CHECKPOINT_20260905.md`

---

## 5. 기타 최근 완료

### Ada one-shot charge-speed lifetime

- production `f70871e36ddf28a2474e7e25d6d7254cf9fe26cd`
- self `charge_speed_pct`
- exactly `burst_cast`
- `duration_bullets:1`
- existing physical-shot / post-shot bullet-consume runtime 재사용

### patternless encounter events

- production `4c78a27f024074a9e19391efc3d4ed6125c2d667`
- static patternless enemy에서 unreachable인 `enemy_death`, `event:part_destroy`만 score blocker에서 제외
- runtime을 broad-enable하지 않음
- Crown external heal 등 다른 named events는 fail closed 유지

---

## 6. 현재 frontier / 계속 보류하는 축

가까운 public gap을 blocker 수만 보고 broad-enable하지 않는다.

특히 다음은 이미 보류 근거가 있다.

- Little Mermaid `거품 난사` — team-global `squad_ammo_consume:500`; Fast/Moris crossing chronology mismatch
- Crown `로얄 에타이어 4` — arbitrary/external `heal_received`
- Mokdan `정정당당 승부다!` — broad weapon change
- Nayuta `기억 연소` — cross-class `SMG -> RL`
- unsafe recipient를 무시한 reload/max-ammo
- HP-derived state 상수화
- generic `bonus_damage` family
- executable global `squad_body_hit`
- arbitrary multi-bullet cadence lifetime
- mixed charge controls

현재 closest public membership `레이드_델타`는 Little Mermaid `거품 난사` 하나만 남았지만 위 이유로 억지 certification하지 않는다.

---

## 7. 다음 단일 checkpoint

최신 production semantic은 patternless `squad_part_hit` blocker hygiene까지 완료됐다.

다음에는 현재 HEAD에서 unique-23 frontier를 다시 fresh audit하고 **비보류 small generic ownership 하나만** 고른다.

현재 낮은 blocker 팀은 이미 보류 근거가 있는 축 비중이 높으므로 blocker 수만 보고 열지 않는다. 특히 다음은 그대로 우회한다.

- Little Mermaid `squad_ammo_consume`
- Crown arbitrary/external `heal_received`
- executable global `squad_body_hit`
- Ada `effect_interval` dynamic periodic deadline rescheduling
- Neon : Vision Eye gauge chronology
- broad/cross-class weapon change
- unsafe reload/max-ammo
- HP-derived state / generic bonus-damage broad enable

다음 slice도 real Moris semantic probe -> existing Fast runtime reuse proof -> negative fail-closed case -> focused/full Fast -> 필요 시 standardized ranking 순으로 진행한다.

---

## 8. 고정 원칙

- Fast는 broad scorer이지 Moris 2.0이 아니다.
- comparison-critical unsupported는 fail closed.
- character-name hack 금지.
- fitted coefficient 금지.
- global 1/60 combat loop 금지.
- state-relevant하지 않은 global per-shot/per-pellet scheduling 금지.
- Fast parity를 위해 Moris `calculator/` semantics를 변경하지 않는다.
- static enemy scope 유지.
- engine은 candidate generation을 결정하지 않는다.
- unsupported coverage를 numeric score로 위장하지 않는다.

---

## 9. CI / cleanup 완료

최신 production semantic commit:

- `745d9f1afcf10d092bb58bf9e0235724a5c41946` — patternless `squad_part_hit` blocker hygiene

semantic cleanup HEAD:

- `41d9d6630c303ae13435fa00e4c391683e15648f`

clean canonical CI:

- run `33942375704`
- job `101242188029`
- result `success`
- Fast damage `159/159`
- calculator `137/137` (1 skip)
- optimizer `374/374`
- bridge `31/31` (1 skip)
- site `385/385`
- golden snapshot `29/29`

checkpoint 문서 commit:

- `68c96ce88c7a23f29612cfc911875e30515c8305`

이 HEAD의 canonical CI도 `33942586974 / 101242734277`에서 전체 `success`다.

`.github/workflows`는 handoff 갱신용 임시 workflow까지 제거한 뒤 `ci.yml`, `pages.yml`만 남겨야 한다.

### 다음 재개 지점

coverage expansion을 계속한다. current HEAD에서 unique-23 frontier를 fresh audit하고 **비보류 small generic ownership 하나만** 새로 선정한다.

`master`는 수정하거나 병합하지 않는다.
