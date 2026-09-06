from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dynamic_reload import DynamicRapidReloadRuntime
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers

counts = Counter()
times = defaultdict(float)
orig_weapon = DynamicRapidReloadRuntime._weapon
orig_predict = DynamicRapidReloadRuntime._predict_next_boundary
orig_sync = DynamicRapidReloadRuntime.sync

def wrap_weapon(self, actor, now):
    name = self.squad.members[actor].name
    counts[("weapon", name)] += 1
    t0 = perf_counter()
    try:
        return orig_weapon(self, actor, now)
    finally:
        times[("weapon", name)] += perf_counter() - t0

def wrap_predict(self, actor):
    name = self.squad.members[actor].name
    counts[("predict", name)] += 1
    t0 = perf_counter()
    try:
        return orig_predict(self, actor)
    finally:
        times[("predict", name)] += perf_counter() - t0

def wrap_sync(self, now):
    counts[("sync", "all")] += 1
    t0 = perf_counter()
    try:
        return orig_sync(self, now)
    finally:
        times[("sync", "all")] += perf_counter() - t0

DynamicRapidReloadRuntime._weapon = wrap_weapon
DynamicRapidReloadRuntime._predict_next_boundary = wrap_predict
DynamicRapidReloadRuntime.sync = wrap_sync

case = snapshot.SQUADS["스쿼드4"]
squad = spec.build_squad(list(case["members"]))
compiled = compile_moris_squad(squad)
assert static_score_blockers(compiled) == ()
print("MEMBERS", tuple(m.name for m in compiled.members), flush=True)
print(
    "RAPID_WEAPON_CHANGE_ACTORS",
    tuple(
        compiled.members[e.actor].name
        for e in compiled.effects
        if e.effect_type == "weapon_change"
    ),
    flush=True,
)

duration = 20.0
cfg = spec.build_config(squad, {
    "duration": duration,
    "first_burst_time": 3.0,
    "rng_mode": "expected",
})
policy = compile_burst_policy(squad, compiled, cfg)
enemy = EnemyStaticProfile(defense=31784.0, duration=duration, core_px=0.0)
t0 = perf_counter()
score = score_static_squad(compiled, policy, enemy)
print("SCORE", perf_counter() - t0, score.events_processed, score.squad_total, score.unsupported, flush=True)
for key, value in sorted(counts.items()):
    print("COUNT", key, value, "TIME", times[key], flush=True)
