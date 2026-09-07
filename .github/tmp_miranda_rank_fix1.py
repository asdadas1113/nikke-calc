from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path); s=p.read_text(encoding='utf-8')
    if old not in s: raise SystemExit(f'anchor missing {path}: {old[:180]!r}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# Preserve the existing generic executable contract. A bare dispatcher may still
# execute a dynamic-target duration_bullets effect and fail atomically after its
# actual target resolves. Lazy mode itself is enabled only after the score runtime
# has registered every possible recipient on a live cadence owner.
replace_once('fast_engine/engine/dispatcher.py',
'''        if (\n            self._lazy_rank_one_bullet_shape_supported(effect)\n            and not self._bullet_lifetime_runtime_safe(effect)\n        ):\n            return False\n''',
'''        if self._lazy_rank_one_bullet_shape_supported(effect):\n            targets = possible_ally_targets(self.squad, effect)\n            if not targets or not all(\n                self.effects.dynamic_bullet_lifetime_supported(actor)\n                for actor in targets\n            ):\n                return False\n''')
replace_once('fast_engine/engine/dispatcher.py',
'''        if self._lazy_rank_one_bullet_shape_supported(effect):\n            targets = possible_ally_targets(self.squad, effect)\n            return bool(targets) and all(\n                self.effects.dynamic_bullet_lifetime_supported(actor)\n                for actor in targets\n            )\n        if not target_scope_is_static(effect.target_spec):\n            return True\n''',
'''        if not target_scope_is_static(effect.target_spec):\n            return True\n''')

# The D checkpoint's global public-certified count is intentionally affected by
# this later Miranda checkpoint. Keep its mechanic-specific assertions intact and
# update only the stale aggregate count.
replace_once('fast_engine/tests/test_damage_full_charge_bullet_lifetime.py',
'''        self.assertEqual(certified, 6)\n        self.assertNotIn(self.BLOCKER, blockers)\n''',
'''        self.assertEqual(certified, 7)\n        self.assertNotIn(self.BLOCKER, blockers)\n''')

print('preserved generic executable contract and updated stale frontier count')
