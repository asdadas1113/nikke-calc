from __future__ import annotations

from collections import Counter
from pathlib import Path

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers


def record_docs() -> None:
    checkpoint = Path("fast_engine/research/STAT_APPLIED_CHARGE_SPEED_CHECKPOINT_20260905.md")
    text = checkpoint.read_text(encoding="utf-8")
    old = (
        "production semantic promotion 자체는 runner에서 full Fast `258/258`까지 통과했다.\n\n"
        "cleanup 뒤 `.github/workflows`를 `ci.yml`, `pages.yml`만 남긴 clean HEAD에서 canonical CI를 다시 실행한다. "
        "이 절의 최종 run/job/count는 clean canonical 결과가 확보된 뒤 기록한다.\n"
    )
    new = (
        "production semantic promotion 자체는 runner에서 full Fast `258/258`까지 통과했다.\n\n"
        "cleanup commit:\n\n"
        "- `e467103c992786d8259229840005e1d672284bb6` — docs/cleanup finalizer\n"
        "- cleanup 뒤 `.github/workflows`는 `ci.yml`, `pages.yml`만 남았다.\n\n"
        "cleanup commit은 GitHub Actions token push라 recursive canonical CI가 생성되지 않았다. "
        "따라서 docs-only metadata commit `f55579ffd586eee15fa21b79c754b27d3e2959d5`로 동일 production tree의 canonical CI를 직접 실행했다.\n\n"
        "- run: `33931819590`\n"
        "- job: `101211793772`\n"
        "- workflow conclusion: `success`\n"
        "- doclint: success\n"
        "- Fast — damage: `151/151`\n"
        "- calculator: `137/137` (1 skip)\n"
        "- optimizer: `374/374`\n"
        "- bridge: `31/31` (1 skip)\n"
        "- site: `385/385`\n"
        "- golden snapshot: `29/29`\n\n"
        "Brady 신규 `test_damage_stat_applied_charge_speed.py`는 canonical `test_damage*.py` discovery에 포함된 상태로 검증됐다.\n"
    )
    if old not in text:
        if "run: `33931819590`" not in text:
            raise SystemExit("checkpoint canonical marker missing")
    else:
        checkpoint.write_text(text.replace(old, new, 1), encoding="utf-8")

    handoff = Path("fast_engine/research/HANDOFF_FAST_ENGINE_20260905.md")
    h = handoff.read_text(encoding="utf-8")
    marker = "## 9. CI / cleanup 계약\n"
    if marker in h:
        prefix = h.split(marker, 1)[0]
        section = (
            "## 9. CI / cleanup 완료\n\n"
            "이번 Brady checkpoint의 production semantic commit은 `8880049678c9270de8d7b98c456b93fa00a67502`다.\n\n"
            "cleanup finalizer commit:\n\n"
            "- `e467103c992786d8259229840005e1d672284bb6`\n\n"
            "cleanup 뒤 `.github/workflows`에는 `ci.yml`, `pages.yml`만 남았다. recursive CI가 생성되지 않아 "
            "docs-only metadata commit `f55579ffd586eee15fa21b79c754b27d3e2959d5`로 canonical CI를 직접 실행했다.\n\n"
            "canonical CI:\n\n"
            "- run `33931819590`\n"
            "- job `101211793772`\n"
            "- result `success`\n"
            "- Fast damage `151/151`\n"
            "- calculator `137/137` (1 skip)\n"
            "- optimizer `374/374`\n"
            "- bridge `31/31` (1 skip)\n"
            "- site `385/385`\n"
            "- golden `29/29`\n\n"
            "따라서 Brady stat-applied checkpoint는 production / regression / canonical CI까지 닫혔다.\n\n"
            "다음 단일 checkpoint는 section 7대로 cadence `63` unique-23 frontier fresh audit에서 고른다.\n\n"
            "`master`는 그대로 둔다.\n"
        )
        handoff.write_text(prefix + section, encoding="utf-8")
    elif "## 9. CI / cleanup 완료" not in h:
        raise SystemExit("handoff CI marker missing")


def enum_value(value):
    if value is None:
        return None
    return getattr(value, "value", str(value))


def frontier() -> None:
    rows = []
    seen: set[tuple[str, ...]] = set()
    for source_name, case in snapshot.SQUADS.items():
        if str(source_name).startswith("지그_"):
            continue
        members = tuple(str(x) for x in case["members"])
        if len(members) != 5 or any(x.startswith("test_") for x in members):
            continue
        if members in seen:
            continue
        seen.add(members)
        compiled = compile_moris_squad(spec.build_squad(list(members)))
        blockers = tuple(static_score_blockers(compiled))
        rows.append((len(blockers), str(source_name), members, compiled, blockers))

    print("UNIQUE_COUNT", len(rows))
    print("CERTIFIED_COUNT", sum(1 for row in rows if row[0] == 0))
    fam = Counter(b.split(":", 1)[0] for row in rows for b in row[4])
    print("FAMILIES", sorted(fam.items(), key=lambda x: (-x[1], x[0])))
    exact = Counter(b for row in rows for b in row[4])
    print("REPEATED_EXACT")
    for blocker, count in exact.most_common(40):
        if count > 1:
            print(count, blocker)

    for count, source_name, members, compiled, blockers in sorted(rows, key=lambda x: (x[0], x[1])):
        print("\nTEAM", count, source_name, members)
        for blocker in blockers:
            print(" B", blocker)
        if count > 10:
            continue
        print(" EFFECT_SHAPES")
        for effect in compiled.effects:
            cap = effect.capability
            cap_blocks = tuple(getattr(cap, "blockers", ()) or ())
            disposition = enum_value(getattr(cap, "disposition", None))
            if not cap_blocks and str(disposition).lower() == "ready":
                continue
            actor = int(effect.actor)
            member = compiled.members[actor]
            member_name = getattr(member, "name", None) or members[actor]
            triggers = [
                {
                    "mode": enum_value(getattr(rule, "mode", None)),
                    "event": getattr(rule, "event_key", None),
                    "threshold": getattr(rule, "threshold", None),
                    "modulo": getattr(rule, "modulo", None),
                }
                for rule in effect.triggers
            ]
            conditions = [
                {
                    "mode": enum_value(getattr(rule, "mode", None)),
                    "key": getattr(rule, "key", None),
                    "value": getattr(rule, "value", None),
                }
                for rule in effect.condition_rules
            ]
            target = getattr(effect, "target_spec", None)
            print(
                "  E",
                {
                    "actor": member_name,
                    "effect_id": effect.effect_id,
                    "name": effect.name,
                    "type": effect.effect_type,
                    "stat": effect.stat,
                    "value": effect.value,
                    "duration": effect.duration,
                    "duration_bullets": getattr(effect, "duration_bullets", None),
                    "max_stack": effect.max_stack,
                    "target": enum_value(getattr(target, "mode", None)),
                    "target_runtime": getattr(target, "runtime_supported", None),
                    "triggers": triggers,
                    "conditions": conditions,
                    "parameters": effect.parameters,
                    "cap_disposition": disposition,
                    "cap_blockers": cap_blocks,
                },
            )


if __name__ == "__main__":
    record_docs()
    frontier()
