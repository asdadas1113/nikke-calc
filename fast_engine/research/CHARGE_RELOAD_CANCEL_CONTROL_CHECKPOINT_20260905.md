# Fast Engine checkpoint — charge reload cancel-on-full — 2026-09-05

## 1. 목적

홍련 : 흑영의 weapon control `reload.cancel_on_full`을 캐릭터 이름 특례 없이 좁은 generic charge control로 소유한다.

지원 범위는 다음 exact shape뿐이다.

- charge weapon
- non-clip
- control top-level key가 정확히 `reload` 하나
- reload key가 정확히 `cancel_on_full` 하나
- `cancel_on_full == True`

다음은 계속 fail closed다.

- `cancel_on_full=False`
- 추가 reload policy가 섞인 control
- `hold` 등 다른 control과 혼합된 shape
- non-charge / clip weapon
- 홍련 : 흑영 `화무십일홍 · 수라 2`의 별도 `ammo_charge_pct` cadence semantics

---

## 2. Moris 의미론

`calculator/timeline.py`의 실제 계약을 추적했다.

탄약 회복으로 현재 탄창이 full에 도달했을 때만, 명시적 `reload.cancel_on_full` control이 켜져 있고 실제 재장전 중이면 reload를 취소한다.

취소 시:

- 탄약 회복으로 채운 ammo는 유지
- 재장전 상태 종료
- `full_reload` event를 발생시키지 않음
- 추가 장전을 하지 않음
- post-reload delay를 넣지 않음
- 즉시 다음 charge/shot 진행 가능

따라서 global frame loop가 필요한 기능이 아니라 ammo-refill callback의 sparse boundary다.

---

## 3. public 기본 상태에서의 reachability

`레이드_볼륨`, `스쿼드4`의 기존 public 설정을 Moris로 확인했다.

- `레이드_볼륨`: Scarlet ammo log 373개, 최소 ammo 5, reload log 0
- `스쿼드4`: Scarlet ammo log 377개, 최소 ammo 9, reload log 0
- 두 팀 모두 control 제거 counterfactual과 squad total / Scarlet damage가 exact same

현재 public default에서는 inert하지만, blocker만 특례 제거하지 않고 실제 active semantics를 구현했다.

---

## 4. active real-character Moris probe

실제 홍련 : 흑영을 사용해 reload-cancel boundary가 발생하는 케이스를 만들었다.

`레이드_볼륨` 기반 probe에서만 홍련 : 흑영 cube를 `렐릭 베어 큐브`로 바꾸고 25초 horizon, first burst `16s`를 사용했다.

Moris 결과:

- reload start: `15.050000000000328`
- control ON cancel: `16.40000000000035`
- control OFF normal reload completion: `16.466666666667013`

control ON에서는 이후 Scarlet shot들이 약 `0.0666667s` 앞당겨졌다.

- ON: `22.1667, 22.6833, 23.2000, 23.7167, 24.2333, 24.7500`
- OFF: `22.2333, 22.7500, 23.2667, 23.7833, 24.3000, 24.8167`

probe: `33943966580 / 101246564539`

---

## 5. Fast 구현

production semantic commit:

- `1902a71a4283528f3bea009ee4d3af6aba476a13` — `Fast: support charge reload cancel-on-full`

변경:

- `fast_engine/engine/weapon.py`: exact control recognizer 추가
- `fast_engine/engine/dynamic_weapon.py`: 기존 ammo-refill boundary에서 full refill 중 active reload만 cancel하고 즉시 charge 복귀
- `fast_engine/engine/score.py`: charge actor safety에 exact pure reload-cancel control 연결

새 global shot/frame scheduler는 만들지 않았다.

---

## 6. A/B / fail-closed gate

isolated candidate A/B:

- run `33944142980`
- job `101247048906`
- result `success`

검증:

- synthetic active reload + full refill -> 즉시 charging 복귀
- partial refill -> 계속 reloading
- `False`, extra reload key, mixed reload+hold -> 모두 fail closed
- focused existing regression `31/31`
- full Fast damage `159/159` (신규 permanent test 추가 전)

standardized ranking:

- certified universe `2` 유지
- clean relative error median `+0.0626832%`
- min `+0.0349533%`
- max `+0.0904131%`
- pairwise accuracy `1.0`
- top-N recall `1.0`

---

## 7. public frontier delta

before -> after:

- cadence `63 -> 59`
- control `6 -> 4`

다른 family 유지:

- skill-state delivery `43`
- normal delivery `41`
- skill damage `27`
- weapon change `12`
- normal state `7`
- periodic grid `1`

accounting은 `24 source / 23 unique / 2 certified / 21 gaps`로 유지됐다.

`레이드_볼륨`: `5 -> 1 blockers`.

남은 blocker:

- `cadence:홍련 : 흑영:화무십일홍 · 수라 2:ammo_charge_pct`

`스쿼드4`: `6 -> 4 blockers`.

남음:

- `weapon_change:목단:정정당당 승부다!`
- `cadence:마스트 : 로망틱 메이드:파이레츠 스피릿 2:reload_speed_pct`
- `cadence:홍련 : 흑영:화무십일홍 · 수라 2:ammo_charge_pct`
- `cadence:앵커 : 이노센트 메이드:말미잘(모양) 파스타 3:reload_speed_pct`

총 6 blockers가 줄었다.

---

## 8. promotion / canonical CI

promotion:

- run `33944366703`
- job `101247674155`
- focused new regression `3/3`
- focused related regression `31/31`
- Fast damage `162/162`
- exact public frontier gate success
- production commit/push success

clean semantic cleanup HEAD:

- `fe13e3f2ae717c056167e0f4ec94cded69d633bc`

canonical CI:

- run `33944434610`
- job `101247870805`
- result `success`
- Fast damage `162/162`
- calculator `137/137` (1 skip)
- optimizer `374/374`
- bridge `31/31` (1 skip)
- site `385/385`
- golden snapshot `29/29`
- Fast static 180s median `69.08ms`, events `368`

---

## 9. 다음 경계

`레이드_볼륨`이 one-blocker frontier가 되었지만 남은 `화무십일홍 · 수라 2:ammo_charge_pct`는 이번 slice와 묶지 않았다.

다음에는 current HEAD fresh audit 후 실제 Moris ammo/cadence chronology를 별도 조사한다. one-blocker라는 이유만으로 certification하지 않는다.

기존 deferred 축은 그대로 유지한다.

- Little Mermaid `squad_ammo_consume`
- Crown external `heal_received`
- executable global `squad_body_hit`
- Ada `effect_interval`
- Neon gauge chronology
- broad/cross-class weapon change
- unsafe broad reload/max-ammo
- HP-derived state / generic bonus-damage broad enable

`master`는 수정하거나 병합하지 않는다.
