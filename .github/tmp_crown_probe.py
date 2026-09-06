from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers


def excerpts(path: str, patterns: tuple[str, ...], radius: int = 14) -> None:
    lines = (ROOT / path).read_text(encoding='utf-8').splitlines()
    hit_lines = []
    for i, line in enumerate(lines, start=1):
        if any(p in line for p in patterns):
            hit_lines.append(i)
    ranges = []
    for line_no in hit_lines:
        start = max(1, line_no - radius)
        end = min(len(lines), line_no + radius)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    print(f'\n### {path} hits={hit_lines}')
    for start, end in ranges:
        print(f'--- {start}:{end} ---')
        for n in range(start, end + 1):
            print(f'{n:04d}: {lines[n-1]}')


for label, row in snapshot.SQUADS.items():
    if str(label).startswith('지그_'):
        continue
    members = tuple(row.get('members') or ())
    if len(members) != 5 or '크라운' not in members:
        continue
    squad = compile_moris_squad(spec.build_squad(list(members)))
    crown_rows = tuple(x for x in static_score_blockers(squad) if ':크라운:' in x)
    print('TEAM', label, 'CROWN_BLOCKERS', crown_rows)
    for i, member in enumerate(squad.members):
        print(' MEMBER', i, member.name, 'weapon=', member.weapon_type, 'burst=', member.burst_stage)

excerpts('fast_engine/engine/score.py', ('normal_delivery:', 'skill_state_delivery:', 'heal_received', 'recipient_score_safe', 'delivery_score_safe'), 20)
excerpts('fast_engine/engine/dispatcher.py', ('heal_received', 'recipient', 'lifetime'), 14)
excerpts('fast_engine/engine/damage_runtime.py', ('heal_received', 'recipient', 'lifetime'), 14)
