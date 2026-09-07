from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path); s=p.read_text(encoding='utf-8')
    if old not in s: raise SystemExit(f'anchor missing {path}: {old[:180]!r}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# These are historical checkpoint tests whose mechanic-specific assertions remain
# unchanged. The completed Miranda checkpoint only changes the shared public
# frontier: the target roster is now blocker-free and one additional unique
# membership is certified.
replace_once('fast_engine/tests/test_damage_effect_interval_periodic_grid.py',
'''        self.assertIn('normal_state:미란다:웨이크업! 4:rank_target_timing', blockers)\n''',
'''        self.assertNotIn('normal_state:미란다:웨이크업! 4:rank_target_timing', blockers)\n        self.assertEqual(blockers, ())\n''')
replace_once('fast_engine/tests/test_damage_full_charge_hit_charge_speed.py',
'''        self.assertEqual(certified, 6)\n        self.assertEqual(cadence, 52)\n''',
'''        self.assertEqual(certified, 7)\n        self.assertEqual(cadence, 52)\n''')
replace_once('fast_engine/tests/test_damage_stat_applied_charge_speed.py',
'''        self.assertEqual(certified, 6)\n        self.assertEqual(cadence, 52)\n''',
'''        self.assertEqual(certified, 7)\n        self.assertEqual(cadence, 52)\n''')
print('updated remaining stale shared-frontier expectations')
