from __future__ import annotations

import inspect
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers
import fast_engine.engine.score as score_mod
import fast_engine.engine.dynamic_rapid as rapid_mod
from fast_engine.engine.score import StaticNormalAttackObserver
from calculator.timeline import simulate, CharState

PRIVATY_TEAMS = []
print('=== PUBLIC PRIVATY ROSTERS ===', flush=True)
for name, case in snapshot.SQUADS.items():
    members = tuple(case['members'])
    if '프리바티' not in members:
        continue
    squad = spec.build_squad(list(members))
    compiled = compile_moris_squad(squad)
    blockers = tuple(b for b in static_score_blockers(compiled) if '프리바티' in b)
    print('TEAM', name, members, flush=True)
    print('PRIVATY_BLOCKERS', blockers, flush=True)
    print('WEAPON_SHAPES', tuple((m.name, m.weapon.get('weapon_type'), m.weapon.get('fire_mode'), bool(m.weapon.get('is_clip')), bool(m.weapon.get('cover_during_delay')), m.weapon.get('control') or {}) for m in compiled.members), flush=True)
    PRIVATY_TEAMS.append((name, members))

print('=== FAST SCORE GATES ===', flush=True)
for name in [
    '_valid_dynamic_bullet_lifetime',
    '_is_dynamic_reload_score_supported',
    '_is_dynamic_max_ammo_score_supported',
    '_reload_recipient_score_safe',
    '_max_ammo_recipient_score_safe',
    '_rapid_actor_score_safe',
    '_charge_actor_score_safe',
]:
    obj = getattr(score_mod, name, None)
    print('\n###', name, flush=True)
    print(inspect.getsource(obj) if obj else '<missing>', flush=True)

print('\n### StaticNormalAttackObserver.__init__', flush=True)
print(inspect.getsource(StaticNormalAttackObserver.__init__), flush=True)

print('=== DYNAMIC RAPID MRO CADENCE METHODS ===', flush=True)
for cls in rapid_mod.DynamicRapidCadenceRuntime.__mro__:
    if cls is object:
        continue
    print('CLASS', cls.__module__, cls.__name__, flush=True)
    for name in ('sync', '_sync_actor', '_full_ammo', '_start_reload', '_finish_reload', '_reload_factor', '_reload_duration'):
        if name not in cls.__dict__:
            continue
        try:
            print('\n### ' + cls.__name__ + '.' + name, flush=True)
            print(inspect.getsource(cls.__dict__[name]), flush=True)
        except Exception as exc:
            print('SOURCE_ERROR', cls.__name__, name, repr(exc), flush=True)

# Moris oracle trace. Patch only for observation; production source is untouched.
orig_full = CharState._full_ammo
orig_start = CharState._start_reload
orig_finish = CharState._finish_reload
records = []

def traced_full(self, bm, t):
    value = orig_full(self, bm, t)
    records.append(('full', float(t), self.name, int(self.ammo), int(value), float(self.reloading_until)))
    return value

def traced_start(self, t, bm, label='재장전 시작', from_empty=False):
    before = (int(self.ammo), float(self.reloading_until))
    out = orig_start(self, t, bm, label, from_empty)
    records.append(('start', float(t), self.name, before[0], int(self.ammo), float(self.reloading_until), label, bool(from_empty)))
    return out

def traced_finish(self, t, bm):
    before = (int(self.ammo), float(self.reloading_until))
    out = orig_finish(self, t, bm)
    records.append(('finish', float(t), self.name, before[0], int(self.ammo), before[1], float(self.reloading_until)))
    return out

CharState._full_ammo = traced_full
CharState._start_reload = traced_start
CharState._finish_reload = traced_finish

try:
    for team_name, members in PRIVATY_TEAMS:
        if team_name == '레이드_트리나홍련':
            # Keep the clip roster as a shape audit; no need to run the broad oracle yet.
            continue
        records.clear()
        squad = spec.build_squad(list(members))
        cfg = spec.build_config(squad, {'duration': 16.0, 'first_burst_time': 3.0, 'rng_mode': 'expected'})
        result = simulate(squad, config=cfg, verbose=True, seed=1)
        log = result.log
        ex_events = [ev for ev in log.buff_events if 'EX 매거진 2' in repr(ev)]
        print('\n=== MORIS TRACE', team_name, '===', flush=True)
        print('EX_EVENTS', ex_events[:4], flush=True)
        if not ex_events:
            print('NO_EX_EVENT', flush=True)
            continue
        fb = float(ex_events[0].t)
        print('FIRST_EX_TIME', fb, flush=True)
        print('AMMO_ACTIVATION', [ev for ev in log.ammo_log if fb-0.05 <= float(ev.t) <= fb+0.10], flush=True)
        print('AMMO_EXPIRY', [ev for ev in log.ammo_log if fb+9.90 <= float(ev.t) <= fb+10.20], flush=True)
        print('RELOAD_WINDOW', [ev for ev in log.reload_log if fb-0.05 <= float(ev.t) <= fb+10.20], flush=True)
        around = [r for r in records if (fb-0.05 <= r[1] <= fb+0.10) or (fb+9.90 <= r[1] <= fb+10.20) or (r[0] in {'start','finish'} and fb <= r[1] <= fb+10.20)]
        print('STATE_RECORDS', around, flush=True)
finally:
    CharState._full_ammo = orig_full
    CharState._start_reload = orig_start
    CharState._finish_reload = orig_finish
