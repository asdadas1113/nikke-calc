from pathlib import Path

checkpoint = Path('fast_engine/research/PERIODIC_ENEMY_RECEIVED_DAMAGE_CHECKPOINT_20260905.md')
text = checkpoint.read_text(encoding='utf-8')
old = '''## 8. canonical CI

production promotion에서 full Fast `262/262`까지 검증했다.

cleanup 뒤 `.github/workflows`를 `ci.yml`, `pages.yml`만 남긴 clean HEAD에서 canonical CI를 다시 실행하고 최종 run/job/count를 이 절에 기록한다.
'''
new = '''## 8. canonical CI

production promotion에서 full Fast `262/262`까지 검증한 뒤, 조사용 temp workflow/scripts를 제거한 clean tree에서 canonical CI를 다시 실행했다.

clean cleanup HEAD:

- `38ce5d1d342afc82490769f76c3663cf3476fd9e`
- `.github/workflows`: `ci.yml`, `pages.yml` only

canonical trigger HEAD:

- `d837729a42d857a73e6d840fa6582be7c13c0662`

canonical CI:

- run `33933054253`
- job `101215498281`
- result `success`
- Fast damage `155/155`
- calculator `137/137` (1 skip)
- optimizer `374/374`
- bridge `31/31` (1 skip)
- site `385/385`
- golden snapshot `29/29`
- Fast static 180s score median `101.28ms` (`events=368`)

따라서 Helm periodic enemy checkpoint는 semantic A/B / production promotion / permanent regression / standardized ranking / clean canonical CI까지 모두 닫혔다.

canonical CI를 발생시키기 위한 `PERIODIC_ENEMY_CANONICAL_CI_TRIGGER_20260905.md`는 최종 handoff 정리에서 제거한다.
'''
if old not in text:
    raise SystemExit('checkpoint canonical section marker not found')
checkpoint.write_text(text.replace(old, new, 1), encoding='utf-8')

handoff = Path('fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md')
text = handoff.read_text(encoding='utf-8')
old = '''## 9. CI / cleanup 진행

이번 Helm periodic enemy production semantic commit은 `4a6cbe388cd0ef32ec07e5b825078fe457619181`다.

promotion run `33932866252` / job `101214901667`에서 full Fast `262/262` 및 production diff whitelist까지 통과했다.

이번 finalizer에서 checkpoint/handoff/LESSONS를 갱신하고 조사용 temp workflow/scripts를 제거한다. cleanup 뒤 `.github/workflows`에는 `ci.yml`, `pages.yml`만 남겨야 한다.

clean HEAD canonical CI 결과를 확보한 뒤 이 절을 최종 완료 상태로 갱신한다.

`master`는 그대로 둔다.
'''
new = '''## 9. CI / cleanup 완료

이번 Helm periodic enemy production semantic commit은 `4a6cbe388cd0ef32ec07e5b825078fe457619181`다.

promotion run `33932866252` / job `101214901667`:

- exact candidate apply success
- focused production regression success
- full Fast `262/262`
- production diff whitelist success
- production commit/push success

checkpoint/handoff/LESSONS 정리와 조사용 temp workflow/scripts 제거 후 clean cleanup HEAD는:

- `38ce5d1d342afc82490769f76c3663cf3476fd9e`

이 시점 `.github/workflows`에는 `ci.yml`, `pages.yml`만 남았다.

clean tree canonical CI를 docs-only trigger HEAD `d837729a42d857a73e6d840fa6582be7c13c0662`에서 실행했다.

canonical CI:

- run `33933054253`
- job `101215498281`
- result `success`
- Fast damage `155/155`
- calculator `137/137` (1 skip)
- optimizer `374/374`
- bridge `31/31` (1 skip)
- site `385/385`
- golden snapshot `29/29`
- Fast static 180s score median `101.28ms` (`events=368`)

따라서 Helm periodic enemy checkpoint는 완전히 닫혔다. canonical trigger 문서는 이 final handoff commit에서 제거한다.

### 다음 재개 지점

coverage expansion을 계속한다. unique-23 frontier를 다시 fresh audit하고 **다음 작은 generic ownership 하나만** 고른다.

이미 보류 근거가 확인된 다음 축은 우회하지 않는다.

- Ada `effect_interval` — dynamic periodic deadline rescheduling
- Neon : Vision Eye `초화력` — gauge chronology 선행 필요
- Little Mermaid `squad_ammo_consume`
- Crown external `heal_received`
- Mihara/D executable global `squad_body_hit`
- broad/cross-class weapon change
- unsafe reload/max-ammo
- HP-derived state / generic bonus-damage broad enable

다음 slice도 real Moris semantic probe -> existing Fast runtime reuse proof -> negative fail-closed case -> focused/full Fast -> 필요 시 standardized ranking 순으로 진행한다.

`master`는 수정하거나 병합하지 않는다.
'''
if old not in text:
    raise SystemExit('handoff final section marker not found')
handoff.write_text(text.replace(old, new, 1), encoding='utf-8')
