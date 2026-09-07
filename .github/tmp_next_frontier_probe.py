from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fast_engine.research.public_blocker_frontier import scan_public_blockers

r = scan_public_blockers()
rows = sorted(r['rows'], key=lambda x: (len(x['blockers']) + len(x['unsupported']), x['source_name']))
fam = Counter(b.split(':', 1)[0] for row in r['rows'] for b in row['blockers'])
print('COUNTS', r['team_count'], r['certified_team_count'], r['coverage_gap_count'])
print('FAMILIES', sorted(fam.items()))
for row in rows:
    if not row['blockers'] and not row['unsupported']:
        continue
    print('ROW', row['source_name'], 'N', len(row['blockers']), 'U', len(row['unsupported']))
    for b in row['blockers']:
        print('  B', b)
    for u in row['unsupported']:
        print('  U', u)
