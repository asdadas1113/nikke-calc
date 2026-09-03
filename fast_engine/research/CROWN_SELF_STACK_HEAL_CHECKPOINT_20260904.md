# Crown self-stack heal bridge checkpoint — 2026-09-04

## 1. 결론

기존 coverage frontier에서 Crown `로얄 에타이어 4`의 `event:heal_received`를 일반 heal chronology 문제로 보고 보류했던 판단은 broad 의미에서는 유지한다.

다만 실제 public corpus를 provider 단위로 다시 추적한 결과, 외부 회복원이 없는 Crown 팀에서는 다음의 훨씬 좁은 self-contained chain만 소유하면 안전하게 인증할 수 있었다.

`hit_count:43`
→ self named stack `릴렉스` +1
→ `stack_reach:릴렉스:20`
→ self named stack reset
→ instant self `heal_hp_pct`
→ recipient `event:heal_received`
→ Crown `로얄 에타이어 4` 7초 `atk_dmg_pct`

따라서 Fast는 **일반 HP/heal simulator를 추가하지 않고**, 이 좁은 generic shape만 permanent 지원한다.

character-name whitelist, fitted coefficient, global 1/60 loop는 사용하지 않았다.

## 2. provider safety split

표준 public corpus에서 Crown의 `heal_received` consumer를 조사한 결과 다음 두 부류가 분리됐다.

### self-chain만 Crown에 도달하는 팀

- `레이드_델타`
- `레이드_루주`
- `레이드_라피앨리스`

이 세 팀에서는 Crown blocker를 제거한다.

### 외부 heal/lifesteal provider가 Crown에 도달할 수 있는 팀

- `스쿼드1`
- `스쿼드5`
- `레이드_일레그`
- `레이드_아스카루드밀라`

이 네 팀에서는 `로얄 에타이어 4`의 `normal_delivery` / `skill_state_delivery` blocker를 계속 유지한다.

대표 external-heal standardized roster:

`리틀 머메이드 / 나가 / 크라운 / 아스카 : WILLE / 루드밀라 : 윈터 오너`

즉 support 판정은 Crown 이름이 아니라 **consumer에게 도달 가능한 모든 heal/lifesteal provider가 좁은 self-stack-heal shape로 증명되는지**로 결정한다.

## 3. Moris semantic probe

표준 `레이드_델타`, 180초 production score weapon path에서 측정했다.

- Moris Crown 43-hit threshold count: `234`
- Fast threshold signal count: `234`
- 첫 threshold Fast-Moris 차이: 약 `-0.0072024464s`
- Moris Crown self-heal count: `11`
- Fast `stack_reach:릴렉스:20`: `11`
- Fast `event:heal_received`: `11`
- `로얄 에타이어 3` activations: `11`
- `로얄 에타이어 4` activations: `11`
- 180초 residual `릴렉스` stack: `14`
- heal timestamp max absolute difference: 약 `0.1790818s`
- Fast events processed: `2403`

`stack_reach`와 self-heal은 같은 edge에서 one-for-one으로 연결됐다.

초기 plain `BurstRuntime` probe에서 9회만 관측된 값은 production scoring path의 오류가 아니었다. `StaticNormalAttackObserver`가 붙지 않아 Crown의 dynamic reload/rapid weapon path를 생략한 진단 harness 오류였고, 실제 score runtime에서는 11/11이 맞았다.

## 4. permanent implementation

Engine/runtime:

- `6a4c8346062eb3284ae34558d93675184b4ab154` — `fix: support self-stack heal-received bridge`

변경 범위:

- `fast_engine/engine/dispatcher.py`
- `fast_engine/engine/score.py`
- regression tests only

지원하는 generic 의미:

1. downstream `stack_reach` provider로 실제 사용되는 permanent self named-stack marker materialization
2. narrow self `remove_named_buff` reset
3. narrow self `heal_hp_pct` → recipient `event:heal_received` dispatch
4. score certification 시 competing external heal/lifesteal provider가 없음을 증명

비실행 metadata인 `note`만 shape 검사에서 무시한다.

지원하지 않는 것:

- arbitrary external heal chronology
- lifesteal chronology
- HP loss / current HP simulation
- broad `heal_received` enable

## 5. regression 결과

production 승격 전 full Fast suite:

- `221 tests` pass
- 180초 structural score median 약 `88.18 ms`

추가 production regression:

- self-only Crown roster는 blocker 제거
- Naga external-heal roster는 fail closed 유지
- 860 raw `hit_count` 입력에서 정확히 20번째 `릴렉스` 후 reset → self-heal → heal-received consumer가 1회 연결
- known DEF55 near-tie order 유지

최종 dedicated audit regression:

- `7/7` pass

## 6. public ranking audit

첫 audit에서 기존 harness bug도 발견했다.

`public_ranking_probe.py`는 source cases 24개를 유지하면서 ranking candidate는 exact ordered membership 기준 23개로 dedupe한다고 문서화했지만 실제 코드는 24개 모두를 validator에 넘겨 duplicate guard에 걸렸다.

Permanent harness fixes:

- `27b389ceec3f5a5ecf2b6c28b0091aa36092ebb3` — `fix: dedupe public ranking observations by membership`
- `5818329270962ef9ec46c8e259f9d79dd787d726` — `test: cover public ranking membership dedupe`

계약:

- source accounting: 24 유지
- ranking observations: exact ordered membership 23
- duplicate source memberships가 공통 standardized scenario에서 서로 다른 deterministic score/safety evidence를 내면 fail closed

최종 public audit:

- source teams: `24`
- unique memberships: `23`
- certified: `2`
- coverage gaps: `21`
- clean relative error median: `+0.0626832%`
- min: `+0.0349533%`
- max: `+0.0904131%`
- clean pairwise accuracy: `1.0`
- clean top-N recall: `1.0`

certified teams는 그대로:

- `레이드_레드후드퀀시`
- `컨트롤_미란다미하라`

즉 Crown bridge는 end-to-end certified membership 수를 즉시 늘리지는 않았다. 그러나 self-only 세 팀에서 Crown root blocker는 정확히 제거됐고, external-provider 네 팀은 안전하게 막힌 채 유지됐다.

## 7. self-only 세 팀의 남은 root

### `레이드_델타`

Crown blocker 제거 후:

- Little Mermaid `거품 난사` — `sequential_damage:10`
- Asuka `섬멸` — `bonus_damage`

### `레이드_루주`

Crown blocker 제거 후에도 Cinderella HP-derived/charge state와 Maiden delivery/HP/sequential damage 계열이 남는다.

### `레이드_라피앨리스`

Crown blocker 제거 후에도 Alice control/pierce, cadence, Little Mermaid sequential damage 계열이 남는다.

따라서 이번 채택은 coverage 숫자 증가가 아니라 **검증된 generic blocker root 하나 제거**로 기록한다.

## 8. 최종 검증

production public audit workflow: success

canonical CI on the audited production tree: success

canonical CI에서 다음이 모두 통과했다.

- Fast sub-suites
- engine unit tests
- optimizer unit tests
- bridge smoke
- browser site tests
- golden snapshot 29개

`master`는 수정/병합하지 않았다.

## 9. 다음 frontier

Crown self-only chain은 더 이상 skip 대상이 아니다.

계속 보류:

- arbitrary/external heal-received chronology
- Little Mermaid `squad_ammo_consume`
- broad weapon-change
- unsafe recipient를 무시한 reload/max-ammo broad enable
- broad bonus_damage enable

다음에는 post-Crown unique 21-gap blocker들을 다시 conceptual root로 묶고, 이미 trigger chronology가 소유된 작은 repeated `normal_delivery` / `skill_state_delivery` / `skill_damage` slice를 우선 찾는다.
