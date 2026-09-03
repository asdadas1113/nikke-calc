# Fast Engine 작업 인계 — 2026-09-04

## 0. 재개 지점

저장소: `asdadas1113/nikke-calc`

작업 브랜치: `fast-engine-phase2-20260901`

**`master`는 수정하거나 병합하지 않는다.**

가장 먼저 읽을 문서:

1. `fast_engine/research/HANDOFF_FAST_ENGINE_20260904.md`
2. `fast_engine/research/CROWN_SELF_STACK_HEAL_CHECKPOINT_20260904.md`
3. `fast_engine/research/COVERAGE_FRONTIER_CHECKPOINT_20260904.md`
4. `fast_engine/research/TIMING_SEMANTICS_RANKING_CHECKPOINT_20260904.md`
5. `fast_engine/research/HANDOFF_FAST_ENGINE_20260903.md`

현재 permanent 핵심 commits:

- `6a4c8346062eb3284ae34558d93675184b4ab154` — `fix: support self-stack heal-received bridge`
- `46af96866b9462ec22455b9c9f5121cfa3b35bdd` — `fix: support last-bullet damage delivery`
- `0f522925b2cac86ab74329a9ce4d02347f739abe` — `fix: align Fast timing with Moris outer ticks [timing-apply]`
- `10e3954ae864e2139ae6a32879393504a071b6e0` — adjacent-target regression correction
- `8a12ee8c8ef8c0f7d05525f0f1c71176306c167e` — static adjacent-target scope correction
- `a5b247b08c30dbf89348a0b263d502d0f06cf5f9` — runtime adjacent-target correction
- `28428dd601ae3ce64a219188afd894b1242a5eb4` — self-state conditional passive sync
- `7695efcff56bd59a5e352a1462f4bda9e61cefed` — self-stack conditional passive sync

public ranking harness fixes:

- `27b389ceec3f5a5ecf2b6c28b0091aa36092ebb3` — exact membership dedupe before ranking validation
- `5818329270962ef9ec46c8e259f9d79dd787d726` — dedupe contract regression

---

## 1. 현재 phase

certified pair의 static ranking hard case는 닫혔고, 현재는 **coverage expansion** 단계다.

Fast-certified real public memberships:

- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

표준 public accounting:

- source cases: `24`
- exact ordered-membership unique candidates: `23`
- certified memberships: `2`
- coverage gaps: `21`

24→23은 coverage 변화가 아니라 duplicate ordered membership 제거다.

최종 production public audit:

- clean relative error median: `+0.0626832%`
- min: `+0.0349533%`
- max: `+0.0904131%`
- pairwise accuracy: `1.0`
- top-N recall: `1.0`

---

## 2. timing 상태

DEF/core near-tie inversion은 generic Moris/Fast timing semantics 수정으로 닫혔다.

정식 runtime에 반영된 핵심:

1. Moris repeated-add outer-frame timestamp observer
2. burst ready check `-1e-9` epsilon contract
3. finite effect true-expiry semantics
4. dynamic charge weapon-change existing magazine inheritance
5. inherited magazine 소진 후 next outer-tick refill edge
6. max-ammo/reload-only 변화가 in-flight charge를 restart하지 않는 semantics

정식 ranking stress:

- core grid `6/6`
- DEF grid `11/11`
- enemy-code grid `5/5`

known DEF55 near-tie regression은 현재도 통과한다.

중요:

- global 1/60 combat loop 없음
- character-name hack 없음
- fitted coefficient 없음
- Moris `calculator/` semantics 변경 없음

MG v2 / phase guard / frame-expiry 실험은 별도 temporary diagnostics이며 permanent runtime에 들어가지 않았다.

---

## 3. 첫 coverage 확장 — `last_bullet`

Privaty `LD 어설트 2/3`에서 post-shot `last_bullet` damage delivery를 generic하게 열었다.

- runtime `46af968...`
- regression `4a3d6f1...`
- Moris/Fast LD2 activation `6 vs 6`
- damage relative error 약 `-0.00006991%`
- named enemy state `타겟 지정` gating도 expiry 포함 정상

public blocker는 네 팀에서 제거됐지만 다른 blockers가 남아 certified count는 그대로 2다.

---

## 4. Crown `heal_received` 재검토 — 좁은 self-chain 채택

이전 `COVERAGE_FRONTIER_CHECKPOINT_20260904.md`의 Crown 보류는 **arbitrary heal chronology에 대해서는 여전히 맞다.**

후속 provider audit에서 self-only Crown 팀은 다음 generic chain만 소유하면 된다는 것을 확인했다.

`hit_count:43`
→ `릴렉스` self stack
→ 20 stack reach
→ self reset
→ self `heal_hp_pct`
→ recipient `event:heal_received`
→ `로얄 에타이어 4`

production commit:

- `6a4c8346062eb3284ae34558d93675184b4ab154`

표준 `레이드_델타` 180초 score-runtime parity:

- Moris 43-hit thresholds: `234`
- Fast: `234`
- Moris self-heals: `11`
- Fast stack-reach/heal-received: `11/11`
- `로얄 에타이어 3/4`: `11/11`
- max heal timestamp absolute diff: 약 `0.1790818s`
- residual `릴렉스` stack: `14`

self-only Crown teams에서 blocker 제거:

- `레이드_델타`
- `레이드_루주`
- `레이드_라피앨리스`

외부 heal/lifesteal provider 가능 팀은 계속 fail closed:

- `스쿼드1`
- `스쿼드5`
- `레이드_일레그`
- `레이드_아스카루드밀라`

따라서 **Crown self-only chain은 더 이상 skip 대상이 아니지만, arbitrary/external heal chronology는 계속 미지원**이다.

세부 근거는 `CROWN_SELF_STACK_HEAL_CHECKPOINT_20260904.md` 참조.

---

## 5. Crown 이후 public blocker 상태

최종 unique-23 blocker-family counts:

- `skill_state_delivery`: `71`
- `cadence`: `68`
- `normal_delivery`: `68`
- `skill_damage`: `29`
- `weapon_change`: `12`
- `control`: `8`
- `normal_state`: `7`

unsupported families: `0`

Crown bridge로 certified membership 수는 바로 늘지 않았다.

self-only Crown 세 팀의 다음 blockers:

### `레이드_델타`

- Little Mermaid `거품 난사` — `sequential_damage:10`
- Asuka `섬멸` — `bonus_damage`

### `레이드_루주`

- Cinderella HP-derived / charge state
- Maiden delivery / HP-derived / sequential damage

### `레이드_라피앨리스`

- Alice control / pierce
- cadence
- Little Mermaid sequential damage

---

## 6. public ranking harness 계약

`public_ranking_probe.py`는 source accounting과 ranking candidate identity를 분리한다.

- source rows는 24개 모두 계산/보존
- ranking validator에는 exact ordered membership 23개만 전달
- duplicate source memberships가 standardized scenario에서 서로 다른 deterministic score/safety evidence를 내면 assertion으로 fail closed

이 수정은 coverage 숫자를 인위적으로 바꾸는 것이 아니라 기존 문서 계약을 코드에 맞춘 것이다.

---

## 7. 검증 상태

Crown production 승격 전:

- Fast full suite `221 tests` pass
- structural 180s score median 약 `88.18ms`

최종 production public audit:

- source24 / unique23 / certified2 / gaps21
- pairwise `1.0`
- top-N recall `1.0`
- Crown intended self-only/external split 확인
- dedicated Crown + near-tie + dedupe regression `7/7` pass

최종 canonical CI도 success:

- Fast sub-suites
- engine unit tests
- optimizer unit tests
- bridge smoke
- browser site tests
- golden snapshot 29개

모두 통과했다.

---

## 8. 계속 보류하는 축

다음은 broad-enable하지 않는다.

- arbitrary/external `heal_received` chronology
- Little Mermaid `squad_ammo_consume`
- broad weapon-change
- unsafe recipient를 무시한 reload/max-ammo broad enable
- broad `bonus_damage`
- HP-derived state를 근거 없이 상수화

Little Mermaid `squad_ammo_consume`는 real 180초에서 Moris 34,587 vs Fast physical shots 34,476이었고 일부 500-shot crossing이 약 +0.6~0.7초 늦어지는 구간이 있어 보류했다.

---

## 9. 다음 단일 checkpoint

**post-Crown blocker frontier를 다시 정적 재분류한다.**

순서:

1. unique 21 gap teams의 remaining blockers를 trigger/target/condition/provider root로 묶는다.
2. raw family count가 아니라 여러 팀에서 반복되면서 chronology가 이미 Fast에 존재하는 root를 우선한다.
3. HP chronology / weapon replacement / team-global ammo chronology를 새로 요구하는 축은 건너뛴다.
4. real effect shape probe → Moris semantic/parity → 최소 generic implementation → focused regression.
5. certified membership이 실제 증가하면 standardized public audit + ranking validation을 즉시 다시 실행한다.

현재 우선 탐색 방향은 repeated `normal_delivery` / `skill_state_delivery` / 작은 `skill_damage` slice다.

**optimizer production integration은 아직 하지 않는다.**

---

## 10. 고정 설계 원칙

- Fast는 broad scorer이지 Moris 2.0이 아니다.
- unsupported comparison-critical mechanic은 fail closed.
- character-name hack 금지.
- result-fitting coefficient 금지.
- global 1/60 combat loop 금지.
- state-relevant하지 않은 global per-shot/per-pellet scheduling 금지.
- Fast parity를 위해 Moris `calculator/` semantics를 변경하지 않는다.
- static enemy scope 유지.
- engine은 candidate generation을 결정하지 않는다.
- unsupported coverage를 numeric score로 위장하지 않는다.

---

## 11. cleanup 상태

Crown 조사에만 사용한 temporary probe/helper/workflow는 이번 checkpoint에서 제거한다.

별도 timing/river 연구에 쓰이는 temporary diagnostics는 그 연구 checkpoint가 닫힐 때까지 유지한다.

`master`는 그대로 둔다.
