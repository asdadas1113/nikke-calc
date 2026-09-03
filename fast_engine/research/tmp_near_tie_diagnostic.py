from __future__ import annotations

import json
from unittest.mock import patch

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import BurstMachine, compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers

CASES = {
    "MM": (
        "미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인",
    ),
    "RHQ": (
        "라피 : 레드 후드", "레드 후드", "프리카", "민트", "퀀시 : 이스케이프 퀸",
    ),
}
DURATION = 180.0
CONFIG = {"duration": DURATION, "first_burst_time": 3.0, "rng_mode": "expected"}
ENEMY = dict(DEFAULT_ENEMY)
ENEMY.update({"def": 55000.0, "code": "작열", "core_px": 10.0})
PROFILE = EnemyStaticProfile(
    defense=55000.0,
    element="작열",
    core_uptime=1.0,
    core_px=10.0,
    duration=DURATION,
)


def run_case(label: str, names: tuple[str, ...]) -> dict:
    squad = spec.build_squad(list(names))
    compiled = compile_moris_squad(squad)
    blockers = static_score_blockers(compiled)
    assert blockers == (), (label, blockers)
    policy = compile_burst_policy(squad, compiled, dict(CONFIG))

    moris = simulate(
        squad,
        config=spec.build_config(squad, dict(CONFIG)),
        enemy=dict(ENEMY),
        seed=42,
        verbose=True,
    )

    fast_casts: list[tuple[float, str, str, int]] = []
    old_cast = BurstMachine._cast_signals

    def traced_cast(machine, actor, stage, now):
        fast_casts.append((
            float(now),
            machine.squad.members[actor].name,
            str(stage),
            int(machine.cycle_count),
        ))
        return old_cast(machine, actor, stage, now)

    with patch.object(BurstMachine, "_cast_signals", new=traced_cast):
        fast = score_static_squad(
            compiled,
            policy,
            PROFILE,
            duration=DURATION,
        )

    moris_casts = [
        (float(row.t), row.caster, row.event)
        for row in (moris.log.burst_log if moris.log else [])
        if "사용" in row.event
    ]
    moris_fb = [
        (float(row.t), row.event)
        for row in (moris.log.burst_log if moris.log else [])
        if row.event.startswith("full_burst")
    ]

    fast_chars = {
        name: float(value)
        for name, value in zip(compiled.names, fast.char_total)
    }
    moris_chars = {name: float(moris.char_total.get(name, 0.0)) for name in compiled.names}
    char_rows = []
    for name in compiled.names:
        m = moris_chars[name]
        f = fast_chars[name]
        char_rows.append({
            "name": name,
            "moris": m,
            "fast": f,
            "delta": f - m,
            "relative_error": (f / m - 1.0) if m else None,
        })

    return {
        "label": label,
        "members": list(compiled.names),
        "moris_total": float(moris.squad_total),
        "fast_total": float(fast.squad_total),
        "relative_error": float(fast.squad_total) / float(moris.squad_total) - 1.0,
        "events_processed": int(fast.events_processed),
        "char_rows": char_rows,
        "moris_casts": moris_casts,
        "fast_casts": fast_casts,
        "moris_full_burst": moris_fb,
    }


def main() -> None:
    rows = {label: run_case(label, names) for label, names in CASES.items()}
    mm = rows["MM"]
    rhq = rows["RHQ"]
    moris_margin = (
        (mm["moris_total"] - rhq["moris_total"])
        / max(mm["moris_total"], rhq["moris_total"])
    )
    fast_margin = (
        (mm["fast_total"] - rhq["fast_total"])
        / max(mm["fast_total"], rhq["fast_total"])
    )
    print("MARGIN=" + json.dumps({
        "moris": moris_margin,
        "fast": fast_margin,
        "delta": fast_margin - moris_margin,
    }, ensure_ascii=False, sort_keys=True))
    for label in ("MM", "RHQ"):
        row = rows[label]
        print("CASE=" + json.dumps({
            key: row[key]
            for key in (
                "label", "members", "moris_total", "fast_total",
                "relative_error", "events_processed", "char_rows",
            )
        }, ensure_ascii=False, sort_keys=True))
        print(f"{label}_MORIS_CASTS=" + repr(row["moris_casts"]))
        print(f"{label}_FAST_CASTS=" + repr(row["fast_casts"]))
        print(f"{label}_MORIS_FB=" + repr(row["moris_full_burst"]))


if __name__ == "__main__":
    main()
