from __future__ import annotations

from pathlib import Path
import signal
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers

class ProbeTimeout(RuntimeError):
    pass

def _alarm(_sig, _frame):
    raise ProbeTimeout("score call exceeded 8s")

signal.signal(signal.SIGALRM, _alarm)

case = snapshot.SQUADS["스쿼드4"]
for duration in (20.0, 30.0, 45.0, 60.0, 90.0, 180.0):
    squad = spec.build_squad(list(case["members"]))
    compiled = compile_moris_squad(squad)
    blockers = static_score_blockers(compiled)
    assert blockers == (), blockers
    cfg = spec.build_config(squad, {
        "duration": duration,
        "first_burst_time": 3.0,
        "rng_mode": "expected",
    })
    policy = compile_burst_policy(squad, compiled, cfg)
    enemy = EnemyStaticProfile(defense=31784.0, duration=duration, core_px=0.0)
    t0 = perf_counter()
    signal.alarm(8)
    try:
        score = score_static_squad(compiled, policy, enemy)
    except ProbeTimeout as exc:
        signal.alarm(0)
        print("DURATION", duration, "TIMEOUT", exc, flush=True)
        break
    else:
        signal.alarm(0)
        print(
            "DURATION", duration,
            "elapsed", perf_counter() - t0,
            "events", score.events_processed,
            "total", score.squad_total,
            "unsupported", score.unsupported,
            flush=True,
        )
