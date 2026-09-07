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
    for i, member in enumerate(compiled.members):
        print(' WEAPON', i, member.name, member.weapon, flush=True)
    for effect in compiled.effects:
        if effect.actor == members.index('프리바티') and effect.name and effect.name.startswith('EX 매거진'):
            print(' EFFECT', effect.effect_id, effect.name, effect.effect_type, effect.stat, effect.value, effect.duration, effect.max_stack, effect.polarity, effect.target_spec, effect.parameters, flush=True)
            print('   TRIGGERS', [(r.mode.value, r.event_key, r.threshold, r.trigger_count_reducible) for r in effect.triggers], flush=True)
            print('   CONDITIONS', [(r.mode.value, r.key, r.value) for r in effect.condition_rules], flush=True)

print('=== FAST SCORE GATES ===', flush=True)
for name in [
    '_is_dynamic_reload_score_supported',
    '_is_dynamic_max_ammo_score_supported',
    '_dynamic_reload_actor_indexes',
    '_dynamic_max_ammo_actor_indexes',
    '_actor_has_live_max_ammo_mutation',
    '_rapid_actor_score_safe',
    '_charge_actor_score_safe',
]:
    obj = getattr(score_mod, name, None)
    print('\n###', name, flush=True)
    print(inspect.getsource(obj) if obj else '<missing>', flush=True)

print('=== DYNAMIC RAPID METHODS ===', flush=True)
for name in dir(rapid_mod.DynamicRapidCadenceRuntime):
    if any(key in name for key in ('ammo', 'reload', 'sync')):
        obj = getattr(rapid_mod.DynamicRapidCadenceRuntime, name)
        if callable(obj):
            try:
                src = inspect.getsource(obj)
            except Exception:
                continue
            print('\n### DynamicRapidCadenceRuntime.' + name, flush=True)
            print(src, flush=True)

print('=== CALCULATOR SOURCE HITS ===', flush=True)
for path in sorted(Path('calculator').rglob('*.py')):
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if any(k in line for k in ('max_ammo_pct', 'reload_speed_pct', '_full_ammo', 'full_ammo'))]
    if not hits:
        continue
    print('\nFILE', path, flush=True)
    emitted = set()
    for i in hits:
        lo, hi = max(0, i-6), min(len(lines), i+10)
        key = (lo, hi)
        if key in emitted:
            continue
        emitted.add(key)
        print(f'--- lines {lo+1}-{hi} ---', flush=True)
        for j in range(lo, hi):
            print(f'{j+1}: {lines[j]}', flush=True)
