from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path); s=p.read_text(encoding='utf-8')
    if old not in s: raise SystemExit(f'anchor missing {path}: {old[:140]!r}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# Existing periodic regressions previously used Ada's interval modifier as a
# convenient known blocker. It is now the exact owned checkpoint, so preserve
# their original intent while reflecting the new frontier.
replace_once(
    'fast_engine/tests/test_damage_periodic_enemy_received.py',
'''        self.assertIn(\n            "periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval",\n            blockers,\n        )\n''',
'''        self.assertNotIn(\n            "periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval",\n            blockers,\n        )\n''')
replace_once(
    'fast_engine/tests/test_damage_periodic_self_crit.py',
'''        self.assertIn(\n            'periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval',\n            blockers,\n        )\n''',
'''        self.assertNotIn(\n            'periodic_grid:에이다:섬광 수류탄 투척 발동 시간 조건:effect_interval',\n            blockers,\n        )\n''')
replace_once(
    'fast_engine/tests/test_damage_periodic_self_crit.py',
'''        self.assertFalse(TriggerDispatcher.is_executable_effect(grid_mutator))\n''',
'''        self.assertTrue(\n            TriggerDispatcher._finite_self_effect_interval_shape_supported(\n                grid_mutator\n            )\n        )\n        self.assertTrue(TriggerDispatcher.is_executable_effect(grid_mutator))\n        from dataclasses import replace\n        malformed = replace(grid_mutator, parameters={})\n        self.assertFalse(\n            TriggerDispatcher._finite_self_effect_interval_shape_supported(\n                malformed\n            )\n        )\n        self.assertFalse(TriggerDispatcher.is_executable_effect(malformed))\n''')

print('updated stale periodic-grid neighboring expectations with exact owned shape')
