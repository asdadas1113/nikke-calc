from pathlib import Path

p = Path("fast_engine/tests/test_damage_helm_bullet_lifetime.py")
text = p.read_text()
old = '''        self.assertEqual(
            runtime.dispatcher.effects.sum_stat(2, "charge_dmg_mag_pct", now=19.9),
            0.0,
        )
'''
new = '''        lingering = [
            active
            for effect, active in runtime.dispatcher.effects.iter_stat(
                "charge_dmg_mag_pct", now=19.9
            )
            if effect.effect_id == helm.effect_id
        ]
        self.assertEqual(lingering, [])
'''
if new not in text:
    if text.count(old) != 1:
        raise SystemExit(f"expected one generated assertion, found {text.count(old)}")
    p.write_text(text.replace(old, new, 1))
