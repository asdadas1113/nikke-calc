from __future__ import annotations

from collections import Counter
from pathlib import Path

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec

COMMON_CONFIG = {"duration": 180.0, "first_burst_time": 3.0, "rng_mode": "expected"}
TARGETS = ("레이드_볼륨", "레이드_이브레이븐")


def run_case(source_name: str):
    members = tuple(str(x) for x in snapshot.SQUADS[source_name]["members"])
    squad = spec.build_squad(list(members))
    config = spec.build_config(squad, dict(COMMON_CONFIG))
    counts = Counter()
    times: dict[str, list[float]] = {}
    original = BuffManager.notify

    def wrapped(self, event, t, caster, **ctx):
        key = str(event)
        if key == "enemy_death" or "part_destroy" in key:
            counts[key] += 1
            times.setdefault(key, []).append(float(t))
        return original(self, event, t, caster, **ctx)

    BuffManager.notify = wrapped
    try:
        result = simulate(squad, config=config, enemy=dict(DEFAULT_ENEMY), seed=42, verbose=False)
    finally:
        BuffManager.notify = original

    buff_hits = Counter()
    log = getattr(result, "log", None)
    if log is not None:
        for event in getattr(log, "buff_events", ()) or ():
            name = str(getattr(event, "name", ""))
            if name in {"프리스타일", "일점 공격"}:
                kind = str(getattr(event, "kind", ""))
                buff_hits[(name, kind)] += 1
    return members, result.squad_total, counts, times, buff_hits


def source_notify_sites():
    rows = []
    for path in (Path("calculator/timeline.py"), Path("calculator/buff_manager.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "enemy_death" in line or "part_destroy" in line:
                rows.append((str(path), lineno, line.strip()))
    return rows


def main():
    print("DEFAULT_ENEMY", DEFAULT_ENEMY)
    print("SOURCE_SITES")
    for row in source_notify_sites():
        print(row)
    for source_name in TARGETS:
        members, total, counts, times, buff_hits = run_case(source_name)
        print("CASE", source_name)
        print("members", members)
        print("score", total)
        print("encounter_event_counts", dict(counts))
        print("encounter_event_times", times)
        print("affected_buff_events", dict(buff_hits))


if __name__ == "__main__":
    main()
