from pathlib import Path

# Keep live weapon lookup off the ordinary rapid hot path. It is only needed in
# squads whose executable graph actually contains a rapid weapon-change effect.
p = Path("fast_engine/engine/dynamic_weapon.py")
text = p.read_text(encoding="utf-8")
old = """        self._rapid_reload.attach_effective_weapon(self.effective_weapon)\n\n        actors = set(self.actors)\n"""
new = """        if any(\n            effect.effect_type == \"weapon_change\"\n            and effect_filter(effect)\n            and str(squad.members[effect.actor].weapon.get(\"fire_mode\") or \"\")\n            in {\"auto\", \"auto_warmup\"}\n            for effect in squad.effects\n        ):\n            self._rapid_reload.attach_effective_weapon(self.effective_weapon)\n\n        actors = set(self.actors)\n"""
if new not in text:
    if old not in text:
        raise RuntimeError("rapid effective-weapon attach anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

# Volume/Scarlet regression: squad4 now closes completely because Moran no longer
# poisons rapid-recipient cadence proofs.
p = Path("fast_engine/tests/test_damage_charge_reload_cancel_control.py")
text = p.read_text(encoding="utf-8")
old = "        self.assertIn('weapon_change:목단:정정당당 승부다!', blockers)\n"
new = "        self.assertEqual(blockers, ())\n"
if new not in text:
    if old not in text:
        raise RuntimeError("squad4 weapon-change assertion anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

# Older reference-stack checkpoint expected an independent reload blocker. That
# blocker was only independent while Moran's rapid recipient was unsafe.
p = Path("fast_engine/tests/test_damage_reference_stack_capture.py")
text = p.read_text(encoding="utf-8")
old = '''        # Reference capture is owned, and Anchor's third-full-burst generic\n        # harmful-stack decrement now proves the stack-3 remover unreachable in\n        # this roster. Independent cadence and rank-target gaps remain.\n        self.assertIn(\n            "cadence:마스트 : 로망틱 메이드:파이레츠 스피릿 2:reload_speed_pct", blockers\n        )\n'''
new = '''        # Reference capture is owned, Anchor's stack-3 remover is unreachable,\n        # and the Moran rapid lifecycle now makes every reload recipient safe.\n        self.assertEqual(blockers, ())\n'''
if new not in text:
    if old not in text:
        raise RuntimeError("reference-stack frontier assertion anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

for path in (
    "fast_engine/tests/test_damage_full_charge_bullet_lifetime.py",
    "fast_engine/tests/test_damage_full_charge_hit_charge_speed.py",
    "fast_engine/tests/test_damage_stat_applied_charge_speed.py",
):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if "self.assertEqual(certified, 5)" in text:
        text = text.replace("self.assertEqual(certified, 5)", "self.assertEqual(certified, 6)", 1)
    p.write_text(text, encoding="utf-8")

for path in (
    "fast_engine/tests/test_damage_full_charge_hit_charge_speed.py",
    "fast_engine/tests/test_damage_stat_applied_charge_speed.py",
):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if "self.assertEqual(cadence, 57)" in text:
        text = text.replace("self.assertEqual(cadence, 57)", "self.assertEqual(cadence, 55)", 1)
    p.write_text(text, encoding="utf-8")

print("Moran performance hot-path and stale frontier assertions staged")
