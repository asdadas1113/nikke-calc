from pathlib import Path

p = Path("fast_engine/tests/test_damage_dynamic_charge_scoring.py")
text = p.read_text(encoding="utf-8")
old = '''        self.assertFalse(any("레드 후드:글레링 아이즈:charge_speed_pct" in x for x in blockers))\n        self.assertFalse(any("레드 후드:글레링 아이즈 2:charge_speed_overflow_conversion_pct" in x for x in blockers))\n        self.assertTrue(any("민트:다 함께 불러주세요! 2:max_ammo_pct" in x for x in blockers))\n'''
new = '''        self.assertFalse(any("레드 후드:글레링 아이즈:charge_speed_pct" in x for x in blockers))\n        self.assertFalse(any("레드 후드:글레링 아이즈 2:charge_speed_overflow_conversion_pct" in x for x in blockers))\n        self.assertFalse(any("민트:다 함께 불러주세요! 2:max_ammo_pct" in x for x in blockers))\n        self.assertFalse(any(x.startswith("weapon_change:레드 후드:레드 울프 무기변경") for x in blockers))\n'''
if old not in text:
    raise SystemExit("glaring-eyes regression anchor not found")
text = text.replace(old, new, 1)

old = '''    def test_public_red_wolf_weapon_change_is_explicit_fail_closed(self):\n        names=["라피 : 레드 후드","레드 후드","프리카","민트","퀀시 : 이스케이프 퀸"]\n        blockers=static_normal_score_blockers(compile_moris_squad(build_squad(names)))\n        self.assertTrue(any(x.startswith("weapon_change:레드 후드:레드 울프 무기변경") for x in blockers))\n'''
new = '''    def test_public_red_wolf_supported_same_class_transform_is_not_blocked(self):\n        names=["라피 : 레드 후드","레드 후드","프리카","민트","퀀시 : 이스케이프 퀸"]\n        blockers=static_normal_score_blockers(compile_moris_squad(build_squad(names)))\n        self.assertFalse(any(x.startswith("weapon_change:레드 후드:레드 울프 무기변경") for x in blockers))\n'''
if old not in text:
    raise SystemExit("weapon-change fail-closed regression anchor not found")
text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")
