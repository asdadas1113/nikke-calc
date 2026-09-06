from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def replace(path, old, new):
    p=ROOT/path
    text=p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'anchor not found: {path}: {old!r}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')

for path in (
    'fast_engine/tests/test_damage_full_charge_bullet_lifetime.py',
    'fast_engine/tests/test_damage_full_charge_hit_charge_speed.py',
    'fast_engine/tests/test_damage_stat_applied_charge_speed.py',
):
    replace(path, 'self.assertEqual(certified, 4)', 'self.assertEqual(certified, 5)')

replace(
    'fast_engine/tests/test_damage_dynamic_ammo_charge.py',
    '''        self.assertNotIn("cadence:루드밀라 : 윈터 오너:여왕의 시선 3:ammo_charge_flat", blockers)\n        self.assertIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)''',
    '''        self.assertNotIn("cadence:루드밀라 : 윈터 오너:여왕의 시선 3:ammo_charge_flat", blockers)\n        self.assertNotIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)\n        self.assertNotIn("skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)''',
)

replace(
    'fast_engine/tests/test_damage_shield_runtime.py',
    'def test_public_naga_shield_damage_blockers_are_removed_but_crown_stays(self):',
    'def test_public_naga_shield_and_unreachable_crown_heal_blockers_are_removed(self):',
)
replace(
    'fast_engine/tests/test_damage_shield_runtime.py',
    '''        self.assertIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)\n        self.assertIn("skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)''',
    '''        self.assertNotIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)\n        self.assertNotIn("skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)''',
)

replace(
    'fast_engine/tests/test_stack_heal_received_runtime.py',
    'def test_self_stack_heal_opens_but_external_heal_stays_fail_closed(self):',
    'def test_self_stack_heal_and_unreachable_lowest_hp_heal_open(self):',
)
replace(
    'fast_engine/tests/test_stack_heal_received_runtime.py',
    '''        external = self._royal_blockers(_EXTERNAL_HEAL)\n        self.assertIn(\n            "normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",\n            external,\n        )\n        self.assertIn(\n            "skill_state_delivery:크라운:로얄 에타이어 4:atk_dmg_pct",\n            external,\n        )''',
    '''        # Naga's allies_lowest_hp:2 heal is outside Crown's immutable\n        # full-HP tie cohort in this exact squad, so it is not a reachable\n        # heal_received provider for Crown. Broad external heals remain closed\n        # in test_damage_crown_royal_attire_lifecycle.py.\n        self.assertEqual(self._royal_blockers(_EXTERNAL_HEAL), ())''',
)
