from __future__ import annotations

from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers

MM = ("미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인")
RHQ = ("라피 : 레드 후드", "레드 후드", "프리카", "민트", "퀀시 : 이스케이프 퀸")
DURATION = 180.0
CFG = {"duration": DURATION, "first_burst_time": 3.0, "rng_mode": "expected"}


def score(names, *, defense: float, code: str, core_px: float):
    squad = spec.build_squad(list(names))
    compiled = compile_moris_squad(squad)
    blockers = static_score_blockers(compiled)
    if blockers:
        raise RuntimeError(blockers)
    policy = compile_burst_policy(squad, compiled, dict(CFG))
    enemy = dict(DEFAULT_ENEMY)
    enemy.update({"def": defense, "code": code, "core_px": core_px})
    profile = EnemyStaticProfile(
        defense=defense,
        element=code,
        core_uptime=1.0,
        core_px=core_px,
        duration=DURATION,
    )
    moris = simulate(
        squad,
        config=spec.build_config(squad, dict(CFG)),
        enemy=enemy,
        seed=42,
        verbose=False,
    )
    fast = score_static_squad(compiled, policy, profile, duration=DURATION)
    return float(moris.squad_total), float(fast.squad_total)


def margin(a: float, b: float) -> float:
    return (a - b) / max(a, b)


def check(label: str, *, defense: float, code: str, core_px: float):
    mm_m, mm_f = score(MM, defense=defense, code=code, core_px=core_px)
    rhq_m, rhq_f = score(RHQ, defense=defense, code=code, core_px=core_px)
    m = margin(mm_m, rhq_m)
    f = margin(mm_f, rhq_f)
    agree = (m >= 0.0) == (f >= 0.0)
    print(
        f"ROW|{label}|def={defense:g}|code={code}|core={core_px:g}"
        f"|m={m:+.8%}|f={f:+.8%}|agree={agree}"
        f"|mm_err={mm_f / mm_m - 1:+.8%}|rhq_err={rhq_f / rhq_m - 1:+.8%}"
    )
    if not agree:
        raise AssertionError(f"ranking mismatch: {label}: Moris={m:+.8%}, Fast={f:+.8%}")
    return m, f


print("CORE_GRID")
for core in (0, 10, 20, 30, 40, 52):
    check(f"core-{core}", defense=60000.0, code="작열", core_px=float(core))

print("DEF_GRID")
for defense in (0, 20000, 31784, 40000, 50000, 55000, 60000, 65000, 70000, 80000, 90000):
    check(f"def-{defense}", defense=float(defense), code="작열", core_px=10.0)

print("CODE_GRID")
for code in ("작열", "수냉", "전격", "철갑", "풍압"):
    check(f"code-{code}", defense=60000.0, code=code, core_px=10.0)

print("ALL_RANKING_ROWS_AGREE")
