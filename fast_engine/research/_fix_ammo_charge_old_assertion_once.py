from pathlib import Path

p = Path("fast_engine/tests/test_damage_helm_bullet_lifetime.py")
text = p.read_text()
old = '        self.assertIn("cadence:리틀 머메이드:세이렌 송 2:ammo_charge_pct", blockers)\n'
new = '        self.assertNotIn("cadence:리틀 머메이드:세이렌 송 2:ammo_charge_pct", blockers)\n'
if new not in text:
    if text.count(old) != 1:
        raise SystemExit(f"expected one obsolete ammo assertion, found {text.count(old)}")
    p.write_text(text.replace(old, new, 1))
